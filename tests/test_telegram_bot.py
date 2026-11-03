"""Telegram /status and /summary: only the owner's chat, read-only, rate-limited."""

import telegram_bot


def make(now=1000.0):
    calls, sent = [], []

    def build(hours, use_ai, label):
        calls.append((hours, use_ai))
        return {"title": f"T {label}", "text": "facts"}
    clock = {"t": now}
    bot = telegram_bot.TelegramBot("tok", "42", digest_build=build, now=lambda: clock["t"])
    bot.send = sent.append
    return bot, calls, sent, clock


def msg(text, chat=42):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "text": text}}


def test_other_chats_are_ignored():
    bot, calls, sent, _ = make()
    assert bot.handle(msg("/status", chat=999)) is None
    assert calls == [] and sent == []


def test_status_is_facts_only():
    bot, calls, sent, _ = make()
    bot.handle(msg("/status"))
    assert calls == [(24, False)] and "facts" in sent[-1]


def test_summary_uses_ai_and_is_rate_limited():
    bot, calls, sent, clock = make()
    bot.handle(msg("/summary 6"))
    assert calls == [(6.0, True)]
    bot.handle(msg("/summary"))
    assert len(calls) == 1 and "try again" in sent[-1]
    clock["t"] += 61
    bot.handle(msg("/summary@MyBot"))
    assert calls[-1] == (24.0, True)


def test_unknown_commands_get_help_and_nothing_runs():
    bot, calls, sent, _ = make()
    for text in ("/sell", "/buy 100", "/stop", "hello"):
        bot.handle(msg(text))
    assert calls == [] and all("/status" in s for s in sent)


def test_long_answers_are_split():
    bot = telegram_bot.TelegramBot("tok", "42", digest_build=lambda **k: None)
    parts = []
    bot.api = lambda method, params=None, timeout=15: parts.append(params["text"])
    bot.send("x" * 9000)
    assert [len(p) for p in parts] == [4000, 4000, 1000]
