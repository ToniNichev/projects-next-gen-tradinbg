#!/usr/bin/env python3
"""
Run the bot in dry_run mode in the foreground (signals only, no real orders).

Loads your normal .env; forces BOT_TRADING_MODE=dry_run unless already set higher.

Usage:

  python scripts/run_dry_run_foreground.py

Recommended before live trading: leave this running for multiple sessions / days while
monitoring dashboard and logs/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    # dry_run executes the live stack without sending orders — force if user left "paper".
    os.environ.setdefault("BOT_TRADING_MODE", "dry_run")
    os.environ.setdefault("BOT_LIVE_TRADING_ENABLED", "false")

    import main as main_module  # noqa: E402

    main_module.main()


if __name__ == "__main__":
    main()
