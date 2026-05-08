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


def send_notification(
    title: str,
    body: str,
    *,
    severity: str = "warning",
) -> None:
    """
    Dispatch a notification asynchronously so the trading loop never blocks
    on network I/O.
    """
    t = threading.Thread(
        target=_send_all_sync,
        args=(title, body, severity),
        daemon=True,
        name="notify",
    )
    t.start()


def _send_all_sync(title: str, body: str, severity: str) -> None:
    full = f"{title}\n{body}" if body else title

    webhook = os.environ.get("BOT_NOTIFY_WEBHOOK_URL", "").strip()
    if webhook:
        _post_json(
            webhook,
            {"title": title, "body": body, "severity": severity},
            timeout=8.0,
        )

    ntfy_topic = os.environ.get("BOT_NOTIFY_NTFY_TOPIC", "").strip()
    if ntfy_topic:
        _ntfy_push(ntfy_topic, full, severity, timeout=8.0)

    tg_token = os.environ.get("BOT_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("BOT_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat:
        url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        payload = {"chat_id": tg_chat, "text": full[:4096]}
        _post_json(url, payload, timeout=8.0)

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
        _post_form("https://api.pushover.net/1/messages.json", data, timeout=8.0)


def _post_json(url: str, payload: dict, *, timeout: float) -> None:
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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify webhook failed: %s", exc)


def _post_form(url: str, fields: dict, *, timeout: float) -> None:
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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify form post failed: %s", exc)


def _ntfy_push(topic: str, message: str, severity: str, *, timeout: float) -> None:
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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("notify ntfy failed: %s", exc)
