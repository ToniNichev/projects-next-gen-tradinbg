#!/usr/bin/env python3
"""
Status report for the pre-live dry_run soak test.

Reports on the window since the bot's last (re)start (or an explicit --since
timestamp): how many simulated trades were recorded, their signal quality,
and whether anything crashed or the websocket dropped. Run this periodically
over the soak test period rather than only checking logs by hand.

Usage:
  python scripts/soak_test_report.py
  python scripts/soak_test_report.py --since 2026-07-13T16:53:10
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import initialize_database, get_database  # noqa: E402

APP_LOG = ROOT / "logs" / "app.log"
ERROR_LOG = ROOT / "logs" / "bot_error.log"

# Minimum bar before this soak test should be considered informative enough
# to weigh in a go/no-go decision on BOT_LIVE_TRADING_ENABLED.
MIN_DAYS = 14
MIN_TRADES = 5


def _find_last_restart() -> datetime:
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+.*DRY RUN MODE")
    last = None
    if APP_LOG.exists():
        for line in APP_LOG.read_text(errors="ignore").splitlines():
            m = pattern.match(line)
            if m:
                last = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    if last is None:
        raise SystemExit("Could not find a 'DRY RUN MODE' line in logs/app.log — pass --since explicitly.")
    return last.replace(tzinfo=timezone.utc)


def _count_log_issues(path: Path, since: datetime) -> dict:
    counts = {"errors": 0, "criticals": 0, "ws_disconnects": 0, "ws_reconnects": 0}
    if not path.exists():
        return counts
    ts_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
    for line in path.read_text(errors="ignore").splitlines():
        m = ts_pattern.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts < since:
            continue
        if " ERROR " in line:
            counts["errors"] += 1
        if " CRITICAL " in line or "🚨" in line:
            counts["criticals"] += 1
        if "WebSocket closed" in line or "WebSocket error" in line:
            counts["ws_disconnects"] += 1
        if "reconnect attempt" in line:
            counts["ws_reconnects"] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=str, default=None,
                         help="ISO timestamp (UTC) to report from. Defaults to the last DRY RUN MODE restart.")
    args = parser.parse_args()

    since = (
        datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        if args.since else _find_last_restart()
    )

    initialize_database("sqlite:///data/trading.db")
    db = get_database()
    with db.get_session() as session:
        from database import Trade
        trades = (
            session.query(Trade)
            .filter(Trade.timestamp >= since.replace(tzinfo=None))
            .order_by(Trade.timestamp)
            .all()
        )
        trade_rows = [
            {
                "timestamp": t.timestamp.isoformat(),
                "side": t.side,
                "price": t.price,
                "confidence": t.signal_confidence,
                "exit_reason": t.exit_reason,
                "pnl": t.pnl,
            }
            for t in trades
        ]

    now = datetime.now(timezone.utc)
    elapsed = now - since
    app_issues = _count_log_issues(APP_LOG, since)
    err_issues = _count_log_issues(ERROR_LOG, since)

    print("=" * 80)
    print("DRY-RUN SOAK TEST STATUS")
    print("=" * 80)
    print(f"Window since:      {since.isoformat()}")
    print(f"Elapsed:           {elapsed.days}d {elapsed.seconds // 3600}h "
          f"(target: {MIN_DAYS}d minimum)")
    print(f"Simulated trades:  {len(trade_rows)} (target: {MIN_TRADES}+ before this is informative)")
    for row in trade_rows:
        print(f"  {row['timestamp']}  {row['side']:<4} @ {row['price']:.2f}  "
              f"conf={row['confidence']}  exit={row['exit_reason']}  pnl={row['pnl']}")
    print("-" * 80)
    print(f"Errors logged:     {app_issues['errors'] + err_issues['errors']}")
    print(f"Criticals logged:  {app_issues['criticals'] + err_issues['criticals']}")
    print(f"WS disconnects:    {app_issues['ws_disconnects'] + err_issues['ws_disconnects']}")
    print(f"WS reconnects:     {app_issues['ws_reconnects'] + err_issues['ws_reconnects']}")
    print("=" * 80)

    ready = elapsed.days >= MIN_DAYS and len(trade_rows) >= MIN_TRADES
    crit = app_issues["criticals"] + err_issues["criticals"]
    print(f"Verdict: {'ENOUGH DATA TO EVALUATE' if ready else 'STILL COLLECTING'}"
          f"{' — but ' + str(crit) + ' unhandled critical(s) logged, investigate before going live' if crit else ''}")


if __name__ == "__main__":
    main()
