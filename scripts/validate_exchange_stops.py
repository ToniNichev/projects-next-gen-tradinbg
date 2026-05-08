#!/usr/bin/env python3
"""
Preflight checks for Binance.US spot STOP_LOSS_LIMIT (exchange protective stops).

Steps 1–2 readiness:
  • Read-only: confirms the symbol lists STOP_LOSS_LIMIT and prints limits/precision.
  • With API keys (--auth): fetches ticker + balances and shows the rounded trigger/limit
    the bot would use for the current tracked levels (dry math only).
  • Optional --place-cancel-test: submits a microscopic STOP_LOSS_LIMIT then immediately
    cancels (locks base balance briefly; gated by BOT_VALIDATE_STOP_ACK).

Run from repo root:

  python scripts/validate_exchange_stops.py
  python scripts/validate_exchange_stops.py --auth
  python scripts/validate_exchange_stops.py --auth --place-cancel-test   # risky

requires .env BINANCE_US_KEY / BINANCE_US_SECRET for --auth
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _force_ipv4() -> None:
    import urllib3.util.connection as urllib3_cn

    def allowed_gai_family():
        return socket.AF_INET

    urllib3_cn.allowed_gai_family = allowed_gai_family  # type: ignore[assignment]


def _build_exchange(config) -> object:
    import ccxt

    _force_ipv4()
    exchange = ccxt.binanceus(
        {
            "apiKey": config.binance_api_key,
            "secret": config.binance_api_secret,
            "enableRateLimit": True,
        }
    )
    exchange.options["defaultType"] = (
        "future" if config.exchange_type == "future" else "spot"
    )
    return exchange


def _public_checks(symbol: str) -> int:
    import ccxt

    print("=== Public (no API keys): load markets ===")
    _force_ipv4()
    ex = ccxt.binanceus({"enableRateLimit": True})
    ex.load_markets()
    if symbol not in ex.markets:
        print(f"ERROR: symbol {symbol!r} not found on Binance.US", file=sys.stderr)
        return 1
    m = ex.markets[symbol]
    info = m.get("info") or {}
    types = info.get("orderTypes") or []
    print(f"symbol: {symbol}")
    print(f"active: {m.get('active')} spot={m.get('spot')} type={m.get('type')}")
    print(f"orderTypes: {types}")
    if "STOP_LOSS_LIMIT" not in types:
        print(
            "\nWARN: STOP_LOSS_LIMIT not listed — live_trader protective stops "
            "will fail until the venue supports them for this pair.",
            file=sys.stderr,
        )
    print(f"limits: {m.get('limits')}")
    print(f"precision: {m.get('precision')}")
    return 0


def _authenticated_checks(place_cancel: bool, symbol: str) -> int:
    from decimal import ROUND_DOWN, Decimal

    os.chdir(ROOT)

    try:
        from database import initialize_database
    except ImportError:
        initialize_database = None  # type: ignore[assignment]

    from config import BotConfig
    from live_trader import LiveTrader, TradingMode

    if initialize_database:
        try:
            initialize_database("sqlite:///data/trading.db")
        except Exception as exc:
            print(f"(db init skipped: {exc})")

    cfg = BotConfig.load()
    if not cfg.binance_api_key or not cfg.binance_api_secret:
        print(
            "ERROR: BINANCE_US_KEY / BINANCE_US_SECRET missing; cannot run --auth",
            file=sys.stderr,
        )
        return 1

    ex = _build_exchange(cfg)
    ex.load_markets()
    ticker = ex.fetch_ticker(symbol)
    bid = float(ticker["bid"])
    balance = ex.fetch_balance()
    base_currency = symbol.split("/")[0]
    base_free = float((balance.get(base_currency) or {}).get("free", 0.0))

    trader = LiveTrader(ex, cfg, TradingMode.LIVE, db_manager=None)

    trigger = bid * (1.0 - cfg.stop_loss_pct)
    trail_lvl = bid * (1.0 - cfg.trailing_stop_pct)
    eff_trigger = max(trigger, trail_lvl)
    trig_r = trader.round_price(eff_trigger)
    lim_r = trader.round_price(trig_r * 0.998)
    if lim_r >= trig_r:
        lim_r = trader.round_price(trig_r * 0.995)
    amt = trader.round_amount(base_free)

    print("\n=== Authenticated sanity ===")
    print(f"ticker bid: {bid}")
    print(f"{base_currency} free: {base_free}")
    print(f"effective trigger (software SL/trailing envelope @ bid): raw ~{eff_trigger:.2f} rounded {trig_r}")
    print(f"suggested STOP_LOSS_LIMIT price (limit): {lim_r}")
    print(f"rounded amount from full balance: {amt}")

    mn = trader.get_min_order_size()
    cost_min = trader.get_min_notional()
    if amt + 1e-12 < mn:
        print(
            f"\nWARN: free balance rounds below min amount ({mn}). Cannot place bracket "
            "without opening a larger spot position first.",
            file=sys.stderr,
        )
    if amt * trig_r + 1e-12 < cost_min:
        print(
            f"\nWARN: notional amt*trigger (~{amt * trig_r:.2f}) below min cost {cost_min}.",
            file=sys.stderr,
        )

    ack = os.environ.get("BOT_VALIDATE_STOP_ACK", "").strip()
    if place_cancel:
        expected = "I_ACCEPT_SPOT_STOP_TEST"
        if ack != expected:
            print(
                f"\nRefusing --place-cancel-test without env BOT_VALIDATE_STOP_ACK={expected}",
                file=sys.stderr,
            )
            return 2

        amt_use = trader.round_amount(base_free)
        if amt_use + 1e-12 < mn:
            amt_use = trader.round_amount(mn)
        if amt_use <= 0 or base_free + 1e-12 < amt_use:
            print(
                "\nCannot run place/cancel test: insufficient free base.",
                file=sys.stderr,
            )
            return 1

        print("\n>>> Placing STOP_LOSS_LIMIT sell (REAL order) <<<")
        try:
            order = ex.create_order(
                symbol,
                "STOP_LOSS_LIMIT",
                "sell",
                amt_use,
                lim_r,
                {"stopPrice": trig_r, "timeInForce": "GTC"},
            )
            oid = str(order.get("id") or "")
            print(f"placed order id={oid}")
            time.sleep(0.4)
            ex.cancel_order(oid, symbol)
            print(f"cancelled order id={oid}")
        except Exception as exc:
            print(f"FAIL: exchange rejected stop test: {exc}", file=sys.stderr)
            return 3

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[2])
    parser.add_argument(
        "--symbol",
        default=None,
        help="Override BOT_SYMBOL (default loaded from env via BotConfig)",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Use API keys — balance, ticker, and bot-style rounded stop prices",
    )
    parser.add_argument(
        "--place-cancel-test",
        action="store_true",
        help=(
            "After --auth: place STOP_LOSS_LIMIT then cancel immediately. "
            "Requires BOT_VALIDATE_STOP_ACK=I_ACCEPT_SPOT_STOP_TEST and free base balance."
        ),
    )
    args = parser.parse_args()

    if args.place_cancel_test and not args.auth:
        print("--place-cancel-test requires --auth", file=sys.stderr)
        return 2

    from config import BotConfig

    sym = args.symbol or BotConfig.load().symbol

    rc = _public_checks(sym)
    if rc != 0:
        return rc

    if args.auth:
        return _authenticated_checks(args.place_cancel_test, sym)
    print("\n(Pass --auth with API keys for balance + simulated stop rounding.)")

    def _marked(s: str) -> str:
        return "(set)" if s.strip() else "(empty)"

    print("\n.notify env (sanity)")
    webhook = os.environ.get("BOT_NOTIFY_WEBHOOK_URL", "").strip()
    print(f"  BOT_NOTIFY_WEBHOOK_URL: {_marked(webhook)}")
    print(f"  BOT_NOTIFY_NTFY_TOPIC: {_marked(os.environ.get('BOT_NOTIFY_NTFY_TOPIC', ''))}")
    print(f"  BOT_NOTIFY_TELEGRAM_BOT_TOKEN: {_marked(os.environ.get('BOT_NOTIFY_TELEGRAM_BOT_TOKEN', ''))}")
    print(f"  BOT_NOTIFY_PUSHOVER_USER_KEY: {_marked(os.environ.get('BOT_NOTIFY_PUSHOVER_USER_KEY', ''))}")
    parsed = urlparse(webhook or "")
    if parsed.username or parsed.password:
        print(
            "WARN: BOT_NOTIFY_WEBHOOK_URL embeds credentials; prefer header-based auth.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
