"""Login lockout (2026-11-06): one typo locked the owner out, because the
dashboard sends ~10 requests at a time and each counted as a failure. And the
address came from the left of X-Forwarded-For, which a visitor can fake."""

from flask import Flask

import auth
from app.extensions import client_ip_from

CF = "172.70.1.2"  # a Cloudflare edge


def setup(monkeypatch):
    cfg = auth.get_auth_config()
    monkeypatch.setattr(cfg, "enabled", True)
    monkeypatch.setattr(cfg, "username", "admin")
    monkeypatch.setattr(cfg, "password", "right")
    auth._failed_logins.clear()
    return Flask(__name__)


def test_the_same_typo_many_times_counts_once(monkeypatch):
    app = setup(monkeypatch)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        for _ in range(30):
            assert auth.verify_password("admin", "rigth") is False
        assert auth.verify_password("admin", "right") is True
    auth._failed_logins.clear()


def test_different_guesses_still_lock_out(monkeypatch):
    app = setup(monkeypatch)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        for i in range(auth.LOCKOUT_MAX_FAILURES):
            assert auth.verify_password("admin", f"guess{i}") is False
        assert auth.verify_password("admin", "right") is False
    auth._failed_logins.clear()


def test_passwords_are_not_kept(monkeypatch):
    app = setup(monkeypatch)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        auth.verify_password("admin", "my-secret-typo")
    assert "my-secret-typo" not in repr(auth._failed_logins)
    auth._failed_logins.clear()


def test_faked_forwarded_for_cannot_dodge_the_lockout(monkeypatch):
    app = setup(monkeypatch)
    for i in range(auth.LOCKOUT_MAX_FAILURES):
        with app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"},
                                      headers={"X-Forwarded-For": f"10.0.0.{i}, 198.51.100.5, {CF}"}):
            auth.verify_password("admin", f"guess{i}")
    with app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"},
                                  headers={"X-Forwarded-For": f"1.2.3.4, 198.51.100.5, {CF}"}):
        assert auth.verify_password("admin", "right") is False
    auth._failed_logins.clear()


def test_client_ip_reading():
    # Cloudflare -> Apache: the entry Cloudflare added is the visitor
    assert client_ip_from("127.0.0.1", f"216.39.34.8, {CF}") == "216.39.34.8"
    assert client_ip_from("127.0.0.1", f"6.6.6.6, 216.39.34.8, {CF}") == "216.39.34.8"
    # Straight to Apache (not through Cloudflare): the address Apache saw
    assert client_ip_from("127.0.0.1", "6.6.6.6, 203.0.113.50") == "203.0.113.50"
    # Straight to the bot, or no header
    assert client_ip_from("203.0.113.7", "6.6.6.6") == "203.0.113.7"
    assert client_ip_from("127.0.0.1", "") == "127.0.0.1"
    assert client_ip_from("::1", f"2001:db8::1, 2606:4700::1") == "2001:db8::1"
