"""
Fire-and-forget alerts for trading bot events.

Configure one or more backends via environment variables (all optional).
Failures are logged but never raise — alerting must never crash the bot.

Supported:
  * Generic webhook — POST JSON {"text": "...", "title": "..."}
  * ntfy.sh — https://ntfy.sh/<topic> with plain body
  * Telegram — BOT_NOTIFY_TELEGRAM_BOT_TOKEN + BOT_NOTIFY_TELEGRAM_CHAT_ID
  * Pushover — BOT_NOTIFY_PUSHOVER_USER_KEY + BOT_NOTIFY_PUSHOVER_APP_TOKEN
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# Severity maps to ntfy priority header (max 5) and Pushover priority
_SEVERITY_PRIORITY = {
    "info": 2,
    "warning": 3,
    "critical": 5,
}


# A failed alert is tried again after these waits (seconds). Two alerts were
# lost to brief DNS outages in Oct 2026 when each was sent only once.
RETRY_DELAYS = (15, 60, 300, 900)


def send_notification(
    title: str,
    body: str,
    *,
    severity: str = "warning",
) -> None:
    """
    Dispatch a notification asynchronously so the trading loop never blocks
    on network I/O. Backends that fail are retried for about 20 minutes.
    """
    t = threading.Thread(
        target=_send_all_sync,
        args=(title, body, severity),
        daemon=True,
        name="notify",
    )
    t.start()


def send_notification_and_wait(title: str, body: str, *, severity: str = "critical",
                               timeout: float = 30.0) -> None:
    """Send and wait (up to timeout) - for alerts sent just before the bot
    exits, when a background thread would be killed before it delivers."""
    t = threading.Thread(
        target=_send_all_sync,
        args=(title, body, severity),
        kwargs={"delays": (5, 15)},
        daemon=True,
        name="notify-wait",
    )
    t.start()
    t.join(timeout)


def _backends(title: str, body: str, severity: str):
    """[(name, send)] for every configured backend; send() -> True if delivered."""
    full = f"{title}\n{body}" if body else title
    out = []

    webhook = os.environ.get("BOT_NOTIFY_WEBHOOK_URL", "").strip()
    if webhook:
        out.append(("webhook", lambda: _post_json(
            webhook, {"title": title, "body": body, "severity": severity}, timeout=8.0)))

    ntfy_topic = os.environ.get("BOT_NOTIFY_NTFY_TOPIC", "").strip()
    if ntfy_topic:
        out.append(("ntfy", lambda: _ntfy_push(ntfy_topic, full, severity, timeout=8.0)))

    tg_token = os.environ.get("BOT_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("BOT_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat:
        url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        payload = {"chat_id": tg_chat, "text": full[:4096]}
        out.append(("telegram", lambda: _post_json(url, payload, timeout=8.0)))

    po_user = os.environ.get("BOT_NOTIFY_PUSHOVER_USER_KEY", "").strip()
    po_app = os.environ.get("BOT_NOTIFY_PUSHOVER_APP_TOKEN", "").strip()
    if po_user and po_app:
        pri = 2 if severity == "critical" else (1 if severity == "warning" else 0)
        data = {
            "token": po_app,
            "user": po_user,
            "title": title[:250],
            "message": body[:1024],
            "priority": pri,
        }
        out.append(("pushover", lambda: _post_form(
            "https://api.pushover.net/1/messages.json", data, timeout=8.0)))
    return out


def _send_all_sync(title: str, body: str, severity: str, delays=None) -> None:
    pending = _backends(title, body, severity)
    waits = (0,) + tuple(RETRY_DELAYS if delays is None else delays)
    for attempt, wait in enumerate(waits):
        if not pending:
            return
        if wait:
            time.sleep(wait)
        pending = [(name, send) for name, send in pending if not send()]
        if pending and attempt + 1 < len(waits):
            logger.warning("Alert '%s' not delivered via %s yet; trying again in %ss",
                           title, ", ".join(n for n, _ in pending), waits[attempt + 1])
    if pending:
        logger.error("Alert '%s' could not be delivered via %s", title, ", ".join(n for n, _ in pending))


def _post_json(url: str, payload: dict, *, timeout: float) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify webhook failed: %s", exc)
        return False


def _post_form(url: str, fields: dict, *, timeout: float) -> bool:
    try:
        body = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify form post failed: %s", exc)
        return False


def _ntfy_push(topic: str, message: str, severity: str, *, timeout: float) -> bool:
    base = os.environ.get("BOT_NOTIFY_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    url = f"{base}/{urllib.parse.quote(topic, safe='')}"
    try:
        prio = str(_SEVERITY_PRIORITY.get(severity, 3))
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            method="POST",
            headers={"Priority": prio, "Title": "Trading bot"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify ntfy failed: %s", exc)
        return False
