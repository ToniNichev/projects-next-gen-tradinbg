"""Ask the trading bot how it's doing from Telegram (read-only).

Runs as its own process (launchd: deploy/com.trading.bot.telegram.plist),
next to the bot, and listens to the same Telegram bot the alerts come from.

  /status            the exact numbers right now (instant, no AI)
  /summary [hours]   a short AI summary (local Ollama) plus the numbers
  /help

Safety:
- Answers only BOT_NOTIFY_TELEGRAM_CHAT_ID. Messages from any other chat
  are ignored.
- Read-only: there is no command that trades, sells, stops or changes
  anything, and none should ever be added here.
"""

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OFFSET_PATH = os.path.join(ROOT, "logs", "telegram_offset.json")
MAX_LEN = 4000          # Telegram's limit is 4096 per message
SUMMARY_EVERY = 60      # seconds between AI summaries (it loads a model into RAM)

log = logging.getLogger("telegram_bot")

HELP = ("I can tell you how the trading bot is doing (I only read, I never trade).\n\n"
        "/status - the exact numbers right now\n"
        "/summary - a short summary of the last 24 hours\n"
        "/summary 6 - the same for the last 6 hours")


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass


class TelegramBot:
    def __init__(self, token, chat_id, digest_build=None, now=time.time):
        self.token = token
        self.chat_id = str(chat_id).strip()
        self.now = now
        self.last_summary = 0.0
        if digest_build is None:
            sys.path.insert(0, ROOT)
            from digest import build as digest_build
        self.digest_build = digest_build

    # ------------------------------------------------------------ Telegram API
    def api(self, method, params=None, timeout=15):
        data = urllib.parse.urlencode(params or {}).encode()
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        with urllib.request.urlopen(url, data=data, timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram error"))
        return body.get("result")

    def send(self, text):
        text = text or "(empty)"
        for i in range(0, len(text), MAX_LEN):
            self.api("sendMessage", {"chat_id": self.chat_id, "text": text[i:i + MAX_LEN],
                                     "disable_web_page_preview": "true"})

    # ---------------------------------------------------------------- commands
    def handle(self, update):
        """One incoming update. Returns the command handled, or None."""
        msg = update.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text:
            return None
        if chat != self.chat_id:
            log.warning("Ignored a message from another chat (%s)", chat)
            return None
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        if cmd == "/status":
            d = self.digest_build(hours=24, use_ai=False, label="status")
            self.send(f"{d['title']}\n\n{d['text']}")
        elif cmd == "/summary":
            hours = 24.0
            if len(parts) > 1:
                try:
                    hours = min(max(float(parts[1]), 1), 24 * 7)
                except ValueError:
                    self.send("Usage: /summary or /summary 6 (hours)")
                    return cmd
            wait = SUMMARY_EVERY - (self.now() - self.last_summary)
            if wait > 0:
                self.send(f"Just made one; try again in {int(wait) + 1} seconds, or use /status.")
                return cmd
            self.last_summary = self.now()
            self.send("Writing a summary… (about 20 seconds)")
            d = self.digest_build(hours=hours, use_ai=True, label="summary")
            self.send(f"{d['title']}\n\n{d['text']}")
        elif cmd in ("/help", "/start"):
            self.send(HELP)
        else:
            self.send("I don't know that one.\n\n" + HELP)
        return cmd

    # -------------------------------------------------------------------- loop
    def _read_offset(self):
        try:
            with open(OFFSET_PATH) as fh:
                return int(json.load(fh)["offset"])
        except Exception:
            return None

    def _save_offset(self, offset):
        os.makedirs(os.path.dirname(OFFSET_PATH), exist_ok=True)
        with open(OFFSET_PATH, "w") as fh:
            json.dump({"offset": offset}, fh)

    def run(self):
        try:
            self.api("setMyCommands", {"commands": json.dumps([
                {"command": "status", "description": "The exact numbers right now"},
                {"command": "summary", "description": "Short summary of the last 24 hours"},
                {"command": "help", "description": "What I can do"},
            ])})
        except Exception as exc:
            log.warning("Could not set the command menu: %s", exc)
        offset = self._read_offset()
        if offset is None:
            # First start: skip old messages, answer only new ones
            try:
                old = self.api("getUpdates", {"offset": -1, "timeout": 0})
                offset = old[-1]["update_id"] + 1 if old else 0
            except Exception:
                offset = 0
        backoff = 5
        log.info("Listening for /status and /summary")
        while True:
            try:
                updates = self.api("getUpdates", {"offset": offset, "timeout": 50,
                                                  "allowed_updates": json.dumps(["message"])},
                                   timeout=65)
                backoff = 5
            except Exception as exc:
                log.warning("Telegram unreachable (%s); retrying in %ss", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                self._save_offset(offset)  # never answer the same message twice
                try:
                    self.handle(u)
                except Exception as exc:
                    log.error("Could not answer: %s", exc)
                    try:
                        self.send(f"Sorry, that failed: {exc}")
                    except Exception:
                        pass


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_env()
    token = os.environ.get("BOT_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("BOT_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        log.error("BOT_NOTIFY_TELEGRAM_BOT_TOKEN and BOT_NOTIFY_TELEGRAM_CHAT_ID must be set in .env")
        time.sleep(600)  # don't let launchd restart this in a tight loop
        return 1
    TelegramBot(token, chat).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
