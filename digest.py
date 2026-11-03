"""Daily plain-English summary of how the bot is doing (run by launchd at 8:30).

1. Facts are gathered exactly, without any AI: pots and P&L from the bot's own
   API, trades in the period, hourly checks, restarts, errors and warnings
   (grouped and counted) from logs/app.log, the watchdog's state, free disk.
2. A local model (Ollama, gemma3:4b by default) turns that fact sheet into a
   short summary. It never sees raw logs and never decides anything.
3. The summary and the fact sheet are sent through the bot's alert channels
   (.env BOT_NOTIFY_*) and saved to logs/digest.log.

Only reads. If Ollama is down, the fact sheet is sent alone.

    ./venv/bin/python digest.py            # last 24 hours, send it
    ./venv/bin/python digest.py --hours 6 --print   # just print, don't send
"""

import argparse
import json
import os
import re
import shutil
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ROOT, "logs", "app.log")
DIGEST_LOG = os.path.join(ROOT, "logs", "digest.log")
WATCHDOG_STATE = os.path.join(ROOT, "logs", "watchdog_state.json")
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (\S+) (.*)$")
# Startup banners logged as warnings on every start; counted as restarts instead
BANNER = re.compile(r"^(=+|⚠️  LIVE TRADING MODE ENABLED.*)$")


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass


def _get(path, key=None, timeout=10):
    port = os.environ.get("BOT_DASHBOARD_PORT", "8000")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def _money(v):
    return f"{'-' if v < 0 else ''}${abs(v):,.2f}"


def _shape(msg):
    """Group log messages that differ only in numbers or IDs."""
    msg = re.sub(r"0x[0-9a-f]+|[0-9a-f]{16,}", "#", msg)
    return re.sub(r"\d+(\.\d+)?", "N", msg)[:140]


def read_log(since_local, path=LOG_PATH):
    out = {"checks": 0, "restarts": 0, "problems": Counter(), "examples": {},
           "reconnects": 0, "stops_armed": 0}
    closed, starts = [], []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for raw in fh:
            m = LINE.match(raw.rstrip("\n"))
            if not m:
                continue
            ts, level, _src, msg = m.groups()
            if datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") < since_local:
                continue
            if msg.startswith("Pot trend: signal="):
                out["checks"] += 1
            elif "LIVE TRADING MODE ENABLED" in msg:
                out["restarts"] += 1
                starts.append(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"))
            elif msg.startswith("WebSocket closed"):
                closed.append(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"))
            elif msg.startswith("Exchange protective stop armed"):
                out["stops_armed"] += 1
            if level in ("WARNING", "ERROR", "CRITICAL") and not BANNER.match(msg) \
                    and not msg.startswith("WebSocket closed"):
                key = (level, _shape(msg))
                out["problems"][key] += 1
                out["examples"].setdefault(key, f"{ts[11:16]} {msg[:200]}")
    # Every restart closes the price feed too; only count the other drops
    out["reconnects"] = sum(1 for c in closed
                            if not any(timedelta(0) <= s - c <= timedelta(seconds=60) for s in starts))
    return out


def gather(hours):
    _load_env()
    key = os.environ.get("DASHBOARD_API_KEY", "")
    now = datetime.now()
    since_local = now - timedelta(hours=hours)
    since_utc = datetime.now(timezone.utc) - timedelta(hours=hours)
    facts = {"period": f"last {hours:g} hours, from {since_local:%b %d %H:%M} to now ({now:%b %d %H:%M})"}

    try:
        facts["health"] = _get("/api/health").get("data", {})
    except Exception as exc:
        facts["health"] = {"error": f"bot not answering: {exc}"}
    try:
        facts["pots"] = _get("/api/pots", key)
    except Exception as exc:
        facts["pots"] = {"error": str(exc)}
    try:
        trades = _get("/api/trades?limit=200", key).get("trades", [])
        facts["trades"] = [t for t in trades
                           if datetime.fromisoformat(t["timestamp"]) >= since_utc]
    except Exception as exc:
        facts["trades"] = []
        facts["trades_error"] = str(exc)
    facts["log"] = read_log(since_local)
    try:
        with open(WATCHDOG_STATE) as fh:
            facts["watchdog"] = json.load(fh)
    except Exception:
        facts["watchdog"] = {}
    du = shutil.disk_usage(ROOT)
    facts["disk"] = {"free_gb": du.free / 1e9, "used_pct": 100 * du.used / du.total}
    return facts


WHY = {"signal": "its strategy signalled", "stop_loss": "stop-loss hit",
       "take_profit": "profit target hit", "manual": "by hand"}


def _trade_text(t):
    when = datetime.fromisoformat(t["timestamp"]).astimezone().strftime("%b %d %H:%M")
    verb = "bought" if t["side"] == "buy" else "sold"
    if t.get("pot") == "manual" or t.get("strategy_name") == "Manual":
        why = "by hand"
    elif t["side"] == "buy":
        why = "its strategy signalled"
    else:
        why = WHY.get(t.get("exit_reason"), t.get("exit_reason") or "")
    res = f", result {_money(t['pnl'])}" if t["side"] == "sell" and t.get("pnl") is not None else ""
    return f"{when} {verb} {t['amount']:.8f} BTC at {_money(t['price'])} ({why}){res}"


def fact_sheet(f):
    """The exact numbers, as plain text (sent as-is under the summary)."""
    lines = [f"Period: {f['period']}"]
    h = f["health"]
    if "error" in h:
        lines.append(f"BOT: {h['error']}")
    else:
        lines.append(
            f"Bot: {'trading' if h.get('trading_enabled') else 'TRADING OFF'}"
            f"{', EMERGENCY STOP ON' if h.get('emergency_stop') else ''}; last hourly check "
            f"{h.get('minutes_since_check', 0):.0f} min ago"
            f"{' (LATE)' if h.get('checks_late') else ''}"
            f"{'; POTS DO NOT MATCH THE EXCHANGE' if h.get('pots_mismatch') else ''}")

    p = f["pots"]
    if "error" in p:
        lines.append(f"Pots: unavailable ({p['error']})")
    else:
        price = p.get("price") or 0
        lines.append(f"BTC price: {_money(price)}")
        total = 0.0
        by_pot = {}
        for t in sorted(f["trades"], key=lambda t: t["timestamp"]):
            by_pot.setdefault(t["pot"], []).append(t)
        for pot in p.get("pots", []):
            total += pot["value"]
            what = (f"holding {pot['btc']:.8f} BTC (bought at {_money(pot['entry_price'])})"
                    if pot["holding"] else "in cash")
            extra = []
            if pot.get("stop_loss"):
                extra.append(f"stop {_money(pot['stop_loss'])}")
            if pot.get("needs_check"):
                extra.append(f"NEEDS CHECK: {pot['needs_check']}")
            if pot.get("paused"):
                extra.append("PAUSED")
            lines.append(
                f"- {pot['label']} pot: {_money(pot['value'])}, result since it started "
                f"{_money(pot['pnl'])} ({pot['pnl_pct']:+.2f}%), {what}, ${pot['cash']:.2f} cash"
                + (f"; {', '.join(extra)}" if extra else ""))
            mine = by_pot.get(pot["name"], [])
            lines.append(f"  {pot['label']} pot trades in this period: "
                         + ("; ".join(_trade_text(t) for t in mine) if mine else "none"))
        lines.append(f"Total in pots: {_money(total)}")
        acct = p.get("account") or {}
        if acct:
            lines.append("Pots vs Binance.US: " + ("match" if acct.get("matches") else "DO NOT MATCH"))

    lines.append(f"Trades in this period, all pots: {len(f['trades'])}")
    lg = f["log"]
    lines.append(f"Hourly checks run: {lg['checks']}")
    lines.append(f"Bot restarts: {lg['restarts']} (usually deliberate updates)")
    lines.append(f"Price-feed drops: {lg['reconnects']}")
    if lg["problems"]:
        lines.append("Warnings/errors (count, first example):")
        for (level, _), n in sorted(lg["problems"].items(),
                                    key=lambda kv: (kv[0][0] != "CRITICAL", kv[0][0] != "ERROR", -kv[1]))[:8]:
            lines.append(f"- {level} x{n}: {lg['examples'][(level, _)]}")
    else:
        lines.append("Warnings/errors: none")
    if f["watchdog"].get("down_since"):
        lines.append("Watchdog: currently reporting a problem")
    d = f["disk"]
    lines.append(f"Disk: {d['free_gb']:.1f} GB free ({d['used_pct']:.0f}% used)"
                 + (" - LOW" if d["free_gb"] < 10 else ""))
    return "\n".join(lines)


PROMPT = """You write a short daily status note about a personal crypto trading bot for its owner.
Use ONLY the facts below. Each trade belongs only to the pot it is listed under.
A pot's "result since it started" is not a trade. Do not invent numbers, do not give trading or investment advice,
do not predict prices. Copy any numbers exactly as written, always as digits (write 17, never seventeen or one).

Write 3 to 6 short sentences in plain English:
- First sentence: overall, is everything fine, or does something need the owner's attention?
- Then: what each pot did and its result, and any trades.
- Then: anything unusual (errors, late checks, pots not matching, needs check, low disk, restarts).
If nothing needs attention, say so plainly. No headings, no bullet points, no markdown.

FACTS:
{facts}
"""


def summarize(sheet, model=None, timeout=180):
    url = os.environ.get("BOT_LLM_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = model or os.environ.get("BOT_DIGEST_MODEL", "gemma3:4b")
    body = json.dumps({
        "model": model, "prompt": PROMPT.format(facts=sheet), "stream": False,
        "options": {"temperature": 0.2, "num_predict": 300},
        "keep_alive": 0,  # free the memory right after; the bot shares this Mac
    }).encode()
    req = urllib.request.Request(f"{url}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return (json.loads(resp.read()).get("response") or "").strip()


def numbers_not_in(summary, sheet):
    """Numbers the model wrote that aren't in the fact sheet (a slip)."""
    norm = lambda x: x.replace(",", "").rstrip(".").lstrip("+-$")
    known = {norm(n) for n in re.findall(r"[\d][\d,]*\.?\d*", sheet)}
    return [n for n in re.findall(r"[\d][\d,]*\.?\d*", summary) if norm(n) not in known]


def needs_attention(f):
    h, p = f["health"], f["pots"]
    return bool(
        "error" in h or h.get("checks_late") or h.get("pots_mismatch") or h.get("emergency_stop")
        or not h.get("trading_enabled", True)
        or any(pot.get("needs_check") for pot in p.get("pots", []))
        or any(level in ("ERROR", "CRITICAL") for level, _ in f["log"]["problems"])
        or f["disk"]["free_gb"] < 10)


def build(hours=24, use_ai=True, model=None, label="daily") -> dict:
    """Everything one digest needs: {title, summary, sheet, attention, text}.
    use_ai=False: the exact facts only (instant)."""
    facts = gather(hours)
    sheet = fact_sheet(facts)
    summary = ""
    if use_ai:
        try:
            # The small model miscounts restarts ("one restart" for 17); they're
            # in the exact facts underneath, so it doesn't get that line
            for_ai = "\n".join(l for l in sheet.splitlines() if not l.startswith("Bot restarts:"))
            summary = summarize(for_ai, model)
            slips = numbers_not_in(summary, sheet)
            if slips:
                summary += f"\n(Check against the facts below: {', '.join(slips[:5])} isn't in them.)"
        except Exception as exc:
            summary = f"(No AI summary: Ollama didn't answer: {exc})"
    attention = needs_attention(facts)
    title = f"⚠️ Trading bot {label}: needs a look" if attention else f"📊 Trading bot {label}"
    text = f"{summary}\n\n— Facts —\n{sheet}" if summary else sheet
    return {"title": title, "summary": summary, "sheet": sheet, "attention": attention,
            "text": text, "made_at": datetime.now(timezone.utc).isoformat()}


def save(d) -> None:
    os.makedirs(os.path.dirname(DIGEST_LOG), exist_ok=True)
    with open(DIGEST_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M} {d['title']}\n{d['text']}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--print", action="store_true", help="print only, don't send")
    ap.add_argument("--json", action="store_true", help="print as JSON (for the dashboard)")
    ap.add_argument("--facts-only", action="store_true", help="no AI summary")
    ap.add_argument("--label", default="daily")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    d = build(args.hours, use_ai=not args.facts_only, model=args.model, label=args.label)
    save(d)
    print(json.dumps(d) if args.json else f"{d['title']}\n\n{d['text']}")
    if not (args.print or args.json):
        sys.path.insert(0, ROOT)
        from notify import send_notification_and_wait
        send_notification_and_wait(d["title"], d["text"],
                                   severity="warning" if d["attention"] else "info", timeout=60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
