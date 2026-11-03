"""Leftover BTC no longer piles up in a pot (audit, 2026-11-02).

Each buy's fee is taken in BTC and sells round down to 0.00001 BTC, so every
round trip left a sliver (~$0.77) that no sell included. Replaying the live
rules, the $15 intraday pot stopped trading after about 15 trades.
"""

from pots import POT_INTRADAY
from tests.test_exchange_stop_fill import stop_fills
from tests.test_pots import candle, live_pots

STEP = 1e-05


def test_many_round_trips_keep_the_leftover_below_one_step():
    pots, _, intraday, sm, exchange = live_pots()
    pot = pots.get(POT_INTRADAY)
    pot.max_buys_per_day = 0  # no daily cap for this test
    for _ in range(6):
        pot.trader.daily_trades = 0  # not testing the daily trade limit here
        intraday.direction = "bullish"
        candle(pots, sm)
        assert pot.holding
        intraday.direction = "bearish"
        candle(pots, sm)
        assert not pot.holding
        assert pot.balances()["BASE"] < STEP              # never more than one step
        assert pots.reconcile() == [] and pots.mismatch is None
    # Old behaviour: 6 slivers of ~0.00000982 = ~0.00006 BTC stranded
    assert exchange.btc < STEP


def test_the_exchange_stop_covers_the_leftover_too():
    pots, _, intraday, sm, exchange = live_pots()
    pot = pots.get(POT_INTRADAY)
    pot.max_buys_per_day = 0
    for _ in range(2):  # two buys: the second one's stop includes the first's sliver
        intraday.direction = "bullish"
        candle(pots, sm)
        intraday.direction = "bearish"
        candle(pots, sm)
    intraday.direction = "bullish"
    candle(pots, sm)
    qty = exchange.create_order.call_args.args[3]
    assert qty == pot.trader.round_amount(pot.balances()["BASE"])
    stop_fills(exchange)
    intraday.direction = "neutral"
    candle(pots, sm)
    assert not pot.holding and pot.balances()["BASE"] < STEP
    assert pots.reconcile() == []
