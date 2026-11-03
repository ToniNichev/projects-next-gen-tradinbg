"""Outside check that the bot is alive (run by launchd every 10 minutes).

The bot sends its own alerts, so when it hangs, crashes or can't start, it
can't tell you. This small script runs separately, asks the bot's /api/health
whether its hourly checks are still happening, and alerts through the same
channels (.env BOT_NOTIFY_*) when they aren't, then once more when it's back.

It only reads /api/health. It never trades or changes anything.
Install: see deploy/com.trading.bot.watchdog.plist.
"""

import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "logs", "watchdog_state.json")
LATE_MINUTES = 75          # one hourly check missed, plus a margin
REPEAT_SECONDS = 3 * 3600  # remind every 3 hours while it stays broken


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass


def check(port: int, timeout: float = 10.0):
    """(ok, problem text)."""
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = (json.loads(resp.read() or b"{}") or {}).get("data") or {}
    except Exception as exc:
        return False, f"the bot isn't answering ({exc}). It may have crashed or be unable to start."
    minutes = data.get("minutes_since_check")
    if minutes is None:
        return True, ""  # an older bot without the check fields
    if float(minutes) > LATE_MINUTES:
        last = data.get("last_check_at") or "since it started"
        return False, (f"the bot hasn't done its hourly check for {round(float(minutes))} minutes "
                       f"(last: {last}). It's running but stuck, or can't get prices.")
    return True, ""


def _read_state():
    try:
        with open(STATE_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh)


def main() -> int:
    _load_env()
    sys.path.insert(0, ROOT)
    from notify import send_notification_and_wait

    port = int(os.environ.get("BOT_DASHBOARD_PORT", "8000"))
    ok, problem = check(port)
    state = _read_state()
    now = time.time()
    if ok:
        if state.get("down_since"):
            mins = round((now - state["down_since"]) / 60)
            send_notification_and_wait("✅ Trading bot is back",
                                       f"Its hourly checks are running again (it was out for about {mins} minutes).",
                                       severity="info")
        _write_state({})
        return 0
    if not state.get("down_since"):
        state["down_since"] = now
    if now - state.get("alerted_at", 0) >= REPEAT_SECONDS:
        send_notification_and_wait("🚨 Trading bot needs attention",
                                   problem[0].upper() + problem[1:] + " Stop orders on Binance.US stay in "
                                   "place; nothing else watches the pots until the bot is back.",
                                   severity="critical")
        state["alerted_at"] = now
    _write_state(state)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
