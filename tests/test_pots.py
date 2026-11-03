"""Money pots: each keeps its own cash and BTC, the intraday pot is capped
per day, restarts restore each pot, and live pots book real fills into
their own ledger without spending more than the exchange has."""

import os

os.environ.setdefault("DASHBOARD_AUTH_ENABLED", "false")

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from config import BotConfig
from database import initialize_database
from live_trader import TradingMode
from pots import (
    POT_INTRADAY, POT_MANUAL, POT_TREND, PotLiveTrader, build_pots, pot_tag,
)
from strategies.base_strategy import StrategySignal
from strategies.constants import StrategyNames
from strategies.strategy_manager import StrategyManager
from tests.test_live_sell_dust import BinanceUSLike

PRICE = 77_000.0


class ScriptedStrategy:
    """Stands in for a real strategy: returns whatever `direction` is set to."""

    def __init__(self, name, position_size, stop=None, take=None):
        self.name = name
        self.direction = "neutral"
        self.position_size = position_size
        self.stop = stop
        self.take = take
        self.enabled = False  # pots must run it anyway

    def is_enabled(self):
        return self.enabled

    def get_weight(self):
        return 1.0

    def compute_signal(self, exchange, symbol, timeframe, candle_data=None):
        return StrategySignal(
            direction=self.direction, price=PRICE, confidence=1.0,
            timestamp=datetime.now(timezone.utc), strategy_name=self.name,
            stop_loss=self.stop or PRICE * 1e-6, take_profit=self.take or PRICE * 100,
            position_size=self.position_size if self.direction != "neutral" else 0.0,
        )


def make_config(**over):
    cfg = BotConfig(
        binance_api_key="", binance_api_secret="", symbol="BTC/USD", timeframe="1h",
        initial_usdt=100.0, fee_rate=0.001, slippage=0.0, use_trailing_stop=False,
        min_position_size=0.10, max_position_size=0.99, max_single_trade_usd=0.0,
        require_trade_confirmation=False, enable_csv_logging=False,
        api_retry_delay_seconds=0.0, order_poll_interval_seconds=0.0,
        pots_enabled=True, pot_trend_usd=75.0, pot_intraday_usd=15.0, pot_manual_usd=6.0,
        pot_intraday_max_buys_per_day=3, pot_intraday_order_pct=0.95,
    )
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


def make_strategies():
    trend = ScriptedStrategy(StrategyNames.TREND_HOLD, 0.99)
    intraday = ScriptedStrategy(StrategyNames.RSI_BB_MEAN_REVERSION, 0.15,
                                stop=PRICE * 0.97, take=PRICE * 1.02)
    return trend, intraday, StrategyManager([trend, intraday])


def build(db, mode="paper", exchange=None, config=None, notify=None):
    trend, intraday, sm = make_strategies()
    pots = build_pots(config or make_config(), exchange=exchange, db_manager=db,
                      strategy_manager=sm, trading_mode=mode, notify=notify)
    return pots, trend, intraday, sm


def candle(pots, sm, price=PRICE):
    return pots.on_candle(price, sm, None, "BTC/USD", "1h", [])


# ------------------------------------------------------------------ paper

def test_paper_trend_pot_carries_on_the_existing_account():
    db = initialize_database("sqlite:///:memory:")
    # A pre-pots trade (no pot tag): $100 -> bought BTC, $0.92 left
    db.add_trade({"timestamp": datetime(2026, 10, 22, 19), "side": "buy", "price": PRICE,
                  "amount": 0.0013, "notional": 99.0, "fee": 0.08, "slippage": 0.0,
                  "usdt_balance": 0.92, "base_balance": 0.0013})
    db.add_position({"side": "long", "entry_price": PRICE, "entry_time": datetime(2026, 10, 22, 19),
                     "amount": 0.0013, "stop_loss": 0.08, "take_profit": PRICE * 100,
                     "is_open": True, "strategy_name": "Aggregated"})

    pots, *_ = build(db)
    trend, intraday, manual = (pots.get(n) for n in (POT_TREND, POT_INTRADAY, POT_MANUAL))
    assert trend.balances() == {"USDT": 0.92, "BASE": 0.0013} and trend.holding
    assert trend.start_value == pytest.approx(100.0)
    assert intraday.balances() == {"USDT": 15.0, "BASE": 0.0} and not intraday.holding
    assert manual.balances() == {"USDT": 6.0, "BASE": 0.0}


def test_pots_never_touch_each_others_coins():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)

    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    t, i = pots.get(POT_TREND), pots.get(POT_INTRADAY)
    assert t.holding and i.holding
    assert t.balances()["USDT"] < 1.0          # ~99% of $75 in BTC
    assert i.balances()["USDT"] == pytest.approx(15 * 0.05, abs=0.05)  # 95% of $15

    # Trend Hold turns bearish: only its own BTC is sold
    i_btc = i.balances()["BASE"]
    trend.direction, intraday.direction = "bearish", "neutral"
    candle(pots, sm)
    assert not t.holding and t.balances()["BASE"] == 0
    assert i.holding and i.balances()["BASE"] == i_btc
    assert t.balances()["USDT"] == pytest.approx(75 * (1 - 0.002), rel=0.003)


def test_intraday_pot_stops_buying_after_three_buys_a_day():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)
    pot = pots.get(POT_INTRADAY)

    for _ in range(3):
        intraday.direction = "bullish"
        candle(pots, sm)
        assert pot.holding
        intraday.direction = "bearish"
        candle(pots, sm)  # sells are never capped
        assert not pot.holding

    intraday.direction = "bullish"
    results = candle(pots, sm)
    assert not pot.holding
    assert "3 buys today" in results[POT_INTRADAY]["note"]
    assert pots.buys_today(pot) == 3

    # Yesterday's buys don't count
    with patch("pots._utc_day_start",
               return_value=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)):
        assert pots.buys_today(pot) == 0


def test_intraday_stop_loss_exits_on_its_own():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)
    intraday.direction = "bullish"
    candle(pots, sm)
    intraday.direction = "neutral"
    results = candle(pots, sm, price=PRICE * 0.96)  # below its 3% stop
    assert results[POT_INTRADAY]["exit"].exit_reason == "stop_loss"
    assert not pots.get(POT_INTRADAY).holding


def test_restart_restores_every_pot_from_the_database():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)
    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    before = {n: p.balances() for n, p in pots.pots.items()}

    again, *_ = build(db)  # a restart
    for name, pot in again.pots.items():
        assert pot.balances() == pytest.approx(before[name])
    assert again.get(POT_TREND).holding and again.get(POT_INTRADAY).holding
    assert not again.get(POT_MANUAL).holding


def test_trade_alert_names_the_pot():
    db = initialize_database("sqlite:///:memory:")
    sent = []
    pots, trend, intraday, sm = build(db, notify=lambda t, b, severity: sent.append((t, b)))
    intraday.direction = "bullish"
    candle(pots, sm)
    assert len(sent) == 1
    assert sent[0][0].startswith("RSI + Bollinger Bands pot (paper): bought")
    assert "Pot now:" in sent[0][1]


def test_summary_totals():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = build(db)
    s = pots.summary(PRICE)
    assert [p["name"] for p in s["pots"]] == [POT_TREND, POT_INTRADAY, POT_MANUAL]
    assert s["total"]["value"] == pytest.approx(96.0)
    assert s["pots"][1]["max_buys_per_day"] == 3


# ------------------------------------------------------------------- live

def live_pots(db=None, usd=96.0, config=None):
    exchange = BinanceUSLike(usd=usd)
    pots, trend, intraday, sm = build(db, mode="live", exchange=exchange, config=config)
    for t in pots.traders():
        t.sync_balances()
    return pots, trend, intraday, sm, exchange


def test_live_pots_book_real_fills_into_their_own_ledger():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db)
    assert all(isinstance(t, PotLiveTrader) for t in pots.traders())
    assert [p.tag for p in pots.pots.values()] == ["live-trend", "live-intraday", "live-manual"]

    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    t, i = pots.get(POT_TREND), pots.get(POT_INTRADAY)
    assert t.holding and i.holding
    # Each pot spent only its own cash; together they match the exchange
    assert t.balances()["USDT"] < 2 and i.balances()["USDT"] < 1.5
    assert t.balances()["USDT"] + i.balances()["USDT"] + 6.0 == pytest.approx(exchange.usd, abs=0.01)
    assert t.balances()["BASE"] + i.balances()["BASE"] == pytest.approx(exchange.btc, abs=1e-9)
    assert pots.reconcile() == []

    # Trend sells only its own coins; the intraday pot keeps its BTC
    i_btc = i.balances()["BASE"]
    trend.direction, intraday.direction = "bearish", "neutral"
    candle(pots, sm)
    assert not t.holding
    assert exchange.btc == pytest.approx(i_btc + t.balances()["BASE"], abs=1e-9)  # + trend's dust
    assert t.balances()["USDT"] == pytest.approx(75 * 0.997, rel=0.01)


def test_live_pots_start_fresh_not_from_paper_rows():
    db = initialize_database("sqlite:///:memory:")
    paper, trend, *_rest = build(db)
    sm = _rest[-1]
    trend.direction = "bullish"
    candle(paper, sm)  # paper trend pot is now in BTC

    pots, *_ = live_pots(db)
    assert pots.get(POT_TREND).balances() == {"USDT": 75.0, "BASE": 0.0}
    assert not pots.get(POT_TREND).holding


def test_live_pot_never_spends_more_than_the_exchange_has_free():
    pots, trend, intraday, sm, exchange = live_pots(usd=50.0)  # less than the pots' $96
    trend.direction = "bullish"
    candle(pots, sm)
    assert exchange.usd >= 0
    assert pots.get(POT_TREND).balances()["USDT"] > 20  # couldn't spend its full $75


def test_reconcile_alerts_once_when_pots_claim_more_than_the_exchange():
    sent = []
    exchange = BinanceUSLike(usd=96.0)
    pots, *_ = build(None, mode="live", exchange=exchange,
                     notify=lambda t, b, severity: sent.append((t, severity)))
    exchange.usd = 50.0  # money left the account outside the bot
    assert pots.reconcile()
    pots.reconcile()
    assert sent == [("🚨 Pots don't match the exchange", "critical")]
    exchange.usd = 96.0
    assert pots.reconcile() == []


def test_dry_run_pots_touch_nothing_real():
    exchange = BinanceUSLike()
    exchange.fetch_balance = lambda: pytest.fail("dry run must not read the real balance")
    pots, trend, intraday, sm = build(None, mode="dry_run", exchange=exchange)
    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_TREND).holding and pots.get(POT_INTRADAY).holding
    exchange.create_market_buy_order.assert_not_called()
    assert pots.reconcile() == []


def test_pot_tags():
    assert pot_tag("trend", live=False) == "trend"
    assert pot_tag("trend", live=True) == "live-trend"


def test_unknown_intraday_strategy_is_refused():
    with pytest.raises(ValueError, match="BOT_POT_INTRADAY_STRATEGY"):
        build(None, config=make_config(pot_intraday_strategy="nope"))


# ------------------------------------------------------- dashboard trades

def test_manual_api_trades_in_the_manual_pot_only():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False,
                         use_atr_stops=False)
    pots, trend, intraday, sm = build(db, config=config)
    trend.direction = "bullish"
    candle(pots, sm)  # Trend Hold holds BTC

    class Ex:
        def fetch_ticker(self, _s):
            return {"last": PRICE, "bid": PRICE, "ask": PRICE}

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), Ex(), sm, config)
    state.set_pot_manager(pots)
    client = app.test_client()
    try:
        with patch("config.BotConfig.load", return_value=config):
            status = client.get("/api/manual/status").get_json()
            assert status["pot"] == "manual" and status["balances"]["USDT"] == 6.0
            assert status["position"] is None  # not Trend Hold's position

            r = client.post("/api/manual/buy", json={"position_size": 0.5})
            assert r.status_code == 200, r.get_json()
            assert pots.get(POT_MANUAL).holding
            assert pots.get(POT_MANUAL).balances()["USDT"] == pytest.approx(3.0, abs=0.01)

            # The position shows the estimated fee for selling it now
            pos = client.get("/api/manual/status").get_json()["position"]
            assert pos["sell_fee"] == pytest.approx(PRICE * pos["amount"] * config.fee_rate)
            assert pos["sell_fee"] > 0

            r = client.post("/api/manual/sell")
            assert r.status_code == 200, r.get_json()
            assert not pots.get(POT_MANUAL).holding
            assert pots.get(POT_TREND).holding  # untouched

            data = client.get("/api/pots").get_json()
            assert data["enabled"] and len(data["pots"]) == 3

            trades = client.get("/api/trades").get_json()["trades"]
            assert {t["pot"] for t in trades} == {"trend", "manual"}
    finally:
        state.set_pot_manager(None)


# ------------------------------------------------------------- cash moves

from pots import TransferError, UNASSIGNED  # noqa: E402


def test_move_cash_between_pots_keeps_profit_and_loss_honest():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = build(db)
    pots.transfer(POT_TREND, POT_MANUAL, 5)
    assert pots.get(POT_TREND).balances()["USDT"] == 70.0
    assert pots.get(POT_MANUAL).balances()["USDT"] == 11.0
    s = {p["name"]: p for p in pots.summary(PRICE)["pots"]}
    assert s["manual"]["invested"] == 11.0 and s["manual"]["pnl"] == 0.0
    assert s["trend"]["invested"] == 70.0 and s["trend"]["pnl"] == 0.0
    assert pots.summary(PRICE)["total"]["invested"] == 96.0


def test_only_uninvested_cash_can_move():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)
    trend.direction = "bullish"
    candle(pots, sm)  # Trend Hold's $75 is now BTC
    with pytest.raises(TransferError, match="only \\$0.\\d\\d in cash"):
        pots.transfer(POT_TREND, POT_MANUAL, 5)
    for bad in (0, -1, "abc", float("nan")):
        with pytest.raises(TransferError):
            pots.transfer(POT_MANUAL, POT_INTRADAY, bad)
    with pytest.raises(TransferError):
        pots.transfer(POT_MANUAL, POT_MANUAL, 1)
    with pytest.raises(TransferError):
        pots.transfer(POT_MANUAL, "nope", 1)
    assert pots.get(POT_MANUAL).balances()["USDT"] == 6.0  # nothing changed


def test_moves_survive_a_restart_without_double_counting():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm = build(db)
    pots.transfer(POT_TREND, POT_INTRADAY, 5)       # before the intraday trade
    intraday.direction = "bullish"
    candle(pots, sm)                                # the trade row includes the $5
    pots.transfer(POT_MANUAL, POT_INTRADAY, 2)      # after it
    before = {n: p.balances() for n, p in pots.pots.items()}

    again, *_ = build(db)
    for name, pot in again.pots.items():
        assert pot.balances() == pytest.approx(before[name]), name
    assert again.net_in(again.get(POT_INTRADAY)) == 7.0


def test_paper_new_money_adds_to_a_pot():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = build(db)
    assert pots.unassigned_cash() is None  # paper: no exchange to check
    pots.transfer(UNASSIGNED, POT_MANUAL, 10)
    assert pots.get(POT_MANUAL).balances()["USDT"] == 16.0
    s = pots.summary(PRICE)
    assert s["total"]["invested"] == 106.0 and s["total"]["pnl"] == 0.0
    assert pots.recent_transfers()[0]["from"] == UNASSIGNED


def test_live_deposits_only_up_to_unassigned_exchange_cash():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db)
    assert pots.unassigned_cash() == pytest.approx(0.0)
    with pytest.raises(TransferError, match="isn't in a pot"):
        pots.transfer(UNASSIGNED, POT_MANUAL, 1)

    exchange.usd += 10  # a deposit
    assert pots.unassigned_cash() == pytest.approx(10.0)
    pots.transfer(UNASSIGNED, POT_INTRADAY, 10)
    assert pots.get(POT_INTRADAY).balances()["USDT"] == 25.0
    assert pots.unassigned_cash() == pytest.approx(0.0)
    assert pots.reconcile() == []

    # Taking money out of a pot leaves it unassigned on the exchange
    pots.transfer(POT_MANUAL, UNASSIGNED, 6)
    assert pots.unassigned_cash() == pytest.approx(6.0)
    intraday.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_INTRADAY).balances()["USDT"] < 2  # spent its $25


def test_dry_run_moves_are_not_saved():
    exchange = BinanceUSLike()
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = build(db, mode="dry_run", exchange=exchange)
    pots.transfer(POT_TREND, POT_MANUAL, 5)
    assert db.get_pot_transfers() == []
    assert pots.net_in(pots.get(POT_MANUAL)) == 5.0


def test_transfer_api():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, trend, intraday, sm = build(db, config=config)

    class Ex:
        def fetch_ticker(self, _s):
            return {"last": PRICE, "bid": PRICE, "ask": PRICE}

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), Ex(), sm, config)
    state.set_pot_manager(pots)
    client = app.test_client()
    try:
        r = client.post("/api/pots/transfer", json={"from": "trend", "to": "manual", "amount": 4})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["balances"]["manual"]["USDT"] == 10.0

        r = client.post("/api/pots/transfer", json={"from": "manual", "to": "trend", "amount": 500})
        assert r.status_code == 400 and "only $10.00 in cash" in r.get_json()["error"]

        data = client.get("/api/pots").get_json()
        assert data["transfers"][0]["amount"] == 4.0 and data["unassigned"] is None
    finally:
        state.set_pot_manager(None)


# ------------------------------------------------------- results over time

from app.services.pot_performance import compute_pot_performance  # noqa: E402


def _hours(start, closes):
    return [{"timestamp": start + timedelta(hours=i), "close": c} for i, c in enumerate(closes)]


def test_pot_line_follows_its_trades_and_ignores_money_moves():
    t0 = datetime(2026, 11, 1, 0, tzinfo=timezone.utc)
    candles = _hours(t0, [100, 100, 110, 110, 121])
    pots = [{
        "name": "intraday", "label": "RSI", "start_time": t0, "start_cash": 15.0,
        # Bought all-in at the close of hour 1 (price 100): 0.15 BTC
        "trades": [{"timestamp": t0 + timedelta(hours=2, seconds=5), "usdt_balance": 0.0, "base_balance": 0.15}],
        # $10 more cash moved in during hour 3
        "moves": [{"timestamp": t0 + timedelta(hours=3, minutes=30), "amount": 10.0}],
    }]
    data = compute_pot_performance(pots, candles)
    pts = data["pots"][0]["points"]
    assert [p["pct"] for p in pts[:3]] == [0.0, 0.0, 10.0]   # BTC up 10% after the buy
    assert pts[3]["value"] == pytest.approx(26.5) and pts[3]["invested"] == 25.0
    assert pts[3]["pct"] == pytest.approx(6.0)              # $1.50 gain on $25 put in, not +$10
    assert pts[4]["value"] == pytest.approx(28.15)
    assert [p["holding"] for p in pts] == [False, True, True, True, True]
    assert data["hold"][-1]["pct"] == pytest.approx(21.0)


def test_each_pot_line_starts_when_the_pot_began():
    t0 = datetime(2026, 11, 1, 0, tzinfo=timezone.utc)
    candles = _hours(t0, [100] * 6)
    pots = [
        {"name": "trend", "label": "T", "start_time": t0, "start_cash": 100.0, "trades": [], "moves": []},
        {"name": "manual", "label": "M", "start_time": t0 + timedelta(hours=3), "start_cash": 6.0,
         "trades": [], "moves": []},
    ]
    data = compute_pot_performance(pots, candles)
    assert len(data["pots"][0]["points"]) == 6
    assert len(data["pots"][1]["points"]) == 4  # its start (3:00 close) + 3 more
    assert len(data["hold"]) == 6


def test_start_times_are_saved_once():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = build(db)
    first = {n: p.start_time for n, p in pots.pots.items()}
    assert all(first.values())
    again, *_ = build(db)
    assert {n: p.start_time for n, p in again.pots.items()} == first


def test_paper_trend_pot_starts_at_its_first_old_trade():
    db = initialize_database("sqlite:///:memory:")
    when = datetime(2026, 10, 20, 15)
    db.add_trade({"timestamp": when, "side": "buy", "price": PRICE, "amount": 0.0001,
                  "notional": 10.0, "fee": 0.0, "slippage": 0.0,
                  "usdt_balance": 90.0, "base_balance": 0.0001})
    pots, *_ = build(db)
    assert pots.get(POT_TREND).start_time == when


def test_performance_api():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    for i in range(6, 0, -1):
        db.add_candle({"symbol": "BTC/USD", "timeframe": "1h", "timestamp": now - timedelta(hours=i),
                       "open": PRICE, "high": PRICE, "low": PRICE, "close": PRICE, "volume": 1.0})
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, *_ = build(db, config=config)
    for p in pots.pots.values():
        p.start_time = now - timedelta(hours=4)

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), None, None, config)
    state.set_pot_manager(pots)
    try:
        with patch("config.BotConfig.load", return_value=config):
            data = app.test_client().get("/api/pots/performance").get_json()
        assert data["success"] and data["enabled"]
        assert [p["name"] for p in data["pots"]] == [POT_TREND, POT_INTRADAY, POT_MANUAL]
        assert data["pots"][0]["points"] and data["hold"]
    finally:
        state.set_pot_manager(None)


def test_candle_still_forming_is_left_out():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    candles = _hours(now - timedelta(hours=3), [100, 100, 100, 100])  # last one closes in the future
    pots = [{"name": "trend", "label": "T", "start_time": now - timedelta(hours=3),
             "start_cash": 10.0, "trades": [], "moves": []}]
    data = compute_pot_performance(pots, candles)
    assert len(data["hold"]) == 3
    assert all(datetime.fromisoformat(p["time"]) <= datetime.now(timezone.utc) for p in data["hold"])
