#!/usr/bin/env python3
"""
Send a single test notification using the same backends as notify.py.

Run from repo root (with .env loaded via python-dotenv from config):

  python scripts/test_notify.py

Set at least one of BOT_NOTIFY_WEBHOOK_URL, BOT_NOTIFY_NTFY_TOPIC,
BOT_NOTIFY_TELEGRAM_*, BOT_NOTIFY_PUSHOVER_* — same as production.

Optional arguments:
  --severity critical|warning|info
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402 — loads dotenv via config.load indirectly
from notify import send_notification  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Test BOT_NOTIFY_* delivery.")
    parser.add_argument(
        "--severity",
        default="warning",
        choices=("info", "warning", "critical"),
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=4.0,
        help="Seconds to wait for the background notifier thread.",
    )
    args = parser.parse_args()

    _ = config.BotConfig  # noqa: F841 — ensure package init side effects complete

    title = "Trading bot — notify test"
    body = (
        "If you see this, alerting is wired. "
        f"severity={args.severity} "
        "(from scripts/test_notify.py)"
    )
    send_notification(title, body, severity=args.severity)
    time.sleep(max(args.wait, 0.5))
    print("Dispatched notification (async). Check your phone/channel.", file=sys.stderr)
    print(
        "If nothing arrived, verify BOT_NOTIFY_* entries in .env.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
