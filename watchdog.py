"""Outside check that the bot is alive (run by launchd every 10 minutes).

The bot sends its own alerts, so when it hangs, crashes or can't start, it
can't tell you. This small script runs separately, asks the bot's /api/health
whether its hourly checks are still happening, and alerts through the same
channels (.env BOT_NOTIFY_*) when they aren't, then once more when it's back.

It only reads /api/health. It never trades or changes anything.
Two more daily chores ride along, so they need no job of their own:
- a backup of the trade database (backup_db.py, once a day);
- a warning when the disk gets low (BOT_DISK_WARN_GB, default 5 GB free):
  if it fills up, the bot can't record the trades it makes.
Install: see deploy/com.trading.bot.watchdog.plist.
"""

import json
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "logs", "watchdog_state.json")
LATE_MINUTES = 75          # one hourly check missed, plus a margin
REPEAT_SECONDS = 3 * 3600  # remind every 3 hours while it stays broken
DAILY = 24 * 3600


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
    failing = data.get("pots_failing") or []
    if failing:
        return False, (f"the hourly check keeps failing for: {', '.join(failing)}. "
                       "Those pots can't trade until it works again (see the bot log).")
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


def check_disk(path=ROOT):
    """(ok, free GB)."""
    free_gb = shutil.disk_usage(path).free / 1e9
    warn_gb = float(os.environ.get("BOT_DISK_WARN_GB", "5"))
    return free_gb >= warn_gb, free_gb


def chores(state, now, send, backup=None, disk=None):
    """Daily backup and disk check. Updates state; alerts at most daily."""
    if backup is None:
        from backup_db import maybe_backup as backup
    path, err = backup()
    if err:
        if "backup_alerted_at" not in state or now - state["backup_alerted_at"] >= DAILY:
            send("⚠️ Trading bot backup failed",
                 f"The daily copy of the trade database didn't work: {err}", "warning")
            state["backup_alerted_at"] = now
    elif path:
        state.pop("backup_alerted_at", None)
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "backup:", path)

    ok, free_gb = (disk or check_disk)()
    if not ok:
        if "disk_alerted_at" not in state or now - state["disk_alerted_at"] >= DAILY:
            send("⚠️ Disk almost full",
                 f"Only {free_gb:.1f} GB free on the Mac running the trading bot. If it fills "
                 "up, the bot can't record the trades it makes. Free some space.", "warning")
            state["disk_alerted_at"] = now
    elif state.pop("disk_alerted_at", None):
        send("✅ Disk space OK again", f"{free_gb:.1f} GB free now.", "info")


def main() -> int:
    _load_env()
    sys.path.insert(0, ROOT)
    from notify import send_notification_and_wait

    def send(title, body, severity):
        send_notification_and_wait(title, body, severity=severity)

    port = int(os.environ.get("BOT_DASHBOARD_PORT", "8000"))
    ok, problem = check(port)
    state = _read_state()
    now = time.time()
    try:
        chores(state, now, send)
    except Exception as exc:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "chores failed:", exc)
    if ok:
        if state.get("down_since"):
            mins = round((now - state["down_since"]) / 60)
            send("✅ Trading bot is back",
                 f"Its hourly checks are running again (it was out for about {mins} minutes).", "info")
        for k in ("down_since", "alerted_at"):
            state.pop(k, None)
        _write_state(state)
        return 0
    if not state.get("down_since"):
        state["down_since"] = now
    if now - state.get("alerted_at", 0) >= REPEAT_SECONDS:
        send("🚨 Trading bot needs attention",
             problem[0].upper() + problem[1:] + " Stop orders on Binance.US stay in "
             "place; nothing else watches the pots until the bot is back.", "critical")
        state["alerted_at"] = now
    _write_state(state)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
