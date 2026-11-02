"""A real order the exchange refuses: no pointless retries, and an alert.

On 2026-11-01 the first live buy failed with Binance error -2015 ("Invalid
API-key, IP, or permissions for action": the key couldn't trade). ccxt
reported it as DDoSProtection (a transient error), so the bot retried it
three times, and nobody was told.
"""

from unittest.mock import MagicMock

import ccxt
import pytest

from live_trader import _retry_call
from tests.test_live_sell_dust import BinanceUSLike, make_trader, signal

REJECTED = 'binanceus {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'


def test_key_without_trading_permission_is_not_retried():
    call = MagicMock(side_effect=ccxt.DDoSProtection(REJECTED))  # what ccxt really raises
    with pytest.raises(ccxt.PermissionDenied):
        _retry_call(call, attempts=3, delay=0.0, description="buy")
    assert call.call_count == 1


def test_real_rate_limit_is_still_retried():
    call = MagicMock(side_effect=[ccxt.DDoSProtection("binanceus 429 Too Many Requests"), "ok"])
    assert _retry_call(call, attempts=3, delay=0.0, description="buy") == "ok"
    assert call.call_count == 2


def test_rejected_buy_alerts_once_and_explains_the_fix(no_real_notifications):
    exchange = BinanceUSLike()
    exchange.create_market_buy_order = MagicMock(side_effect=ccxt.DDoSProtection(REJECTED))
    trader = make_trader(exchange)

    assert trader.handle_signal(signal("bullish")) is None
    assert exchange.create_market_buy_order.call_count == 1
    assert trader.open_position is None
    alerts = [n for n in no_real_notifications if "order failed" in n[0]]
    assert len(alerts) == 1
    title, body, severity = alerts[0]
    assert severity == "critical" and "enable Spot Trading" in body

    # The next hourly check fails the same way: no second alert yet
    assert trader.handle_signal(signal("bullish")) is None
    assert len([n for n in no_real_notifications if "order failed" in n[0]]) == 1


def test_buy_that_keeps_failing_on_the_network_alerts_too(no_real_notifications):
    exchange = BinanceUSLike()
    exchange.create_market_buy_order = MagicMock(side_effect=ccxt.NetworkError("timed out"))
    trader = make_trader(exchange)
    trader.retry_delay = 0.0
    with pytest.raises(ccxt.NetworkError):
        trader.handle_signal(signal("bullish"))
    assert exchange.create_market_buy_order.call_count == 3
    alerts = [n for n in no_real_notifications if "order failed" in n[0]]
    assert len(alerts) == 1 and "try again" in alerts[0][1]
