"""Only one copy of the bot may run (a second would place every trade twice)."""

import os

import main


def test_second_copy_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setattr(main, "_INSTANCE_LOCK", None)
    assert main._take_single_instance_lock() is True
    held = main._INSTANCE_LOCK
    assert open(tmp_path / "bot.lock").read().strip() == str(os.getpid())
    try:
        monkeypatch.setattr(main, "_INSTANCE_LOCK", None)
        assert main._take_single_instance_lock() is False   # still held by the first
    finally:
        held.close()
    assert main._take_single_instance_lock() is True        # free once the first is gone
    main._INSTANCE_LOCK.close()


def test_failed_start_exits_non_zero_and_alerts_once_an_hour(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(main, "LOCK_PATH", str(tmp_path / "bot.lock"))
    assert main._fail_start("couldn't reach the exchange (DNS).") == 1
    assert main._fail_start("couldn't reach the exchange (DNS).") == 1
    alerts = [n for n in no_real_notifications if "can't start" in n[0]]
    assert len(alerts) == 1
