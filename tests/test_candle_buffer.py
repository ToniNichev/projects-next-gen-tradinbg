"""Closed candles only, one per hour (audit, 2026-11-02)."""

from candle_buffer import add_closed, closed_only

H = 3_600_000


def c(i, close=100.0):
    return [i * H, close, close, close, close, 1.0]


def test_the_forming_candle_is_dropped():
    now = 10 * H + 5 * 60_000          # 5 minutes into the 10th hour
    got = closed_only([c(8), c(9), c(10)], H, now)
    assert [x[0] for x in got] == [8 * H, 9 * H]


def test_the_closed_version_replaces_a_copy_instead_of_doubling_it():
    buf = [c(8), c(9, close=101.0)]
    assert add_closed(buf, c(9, close=99.5)) is False
    assert [x[0] for x in buf] == [8 * H, 9 * H] and buf[-1][4] == 99.5


def test_new_candles_append_in_order_and_the_buffer_stays_capped():
    buf = [c(1), c(2)]
    assert add_closed(buf, c(3), max_size=3) is True
    assert add_closed(buf, c(4), max_size=3) is True
    assert [x[0] // H for x in buf] == [2, 3, 4]
    # An older candle that was missing goes in its place
    buf = [c(1), c(3)]
    add_closed(buf, c(2))
    assert [x[0] // H for x in buf] == [1, 2, 3]
