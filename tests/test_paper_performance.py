"""Paper test so far: the bot's account vs. holding BTC."""

from app.services.paper_performance import compute_paper_performance


def candle(hour, close):
    return {"timestamp": f"2026-10-20T{hour:02d}:00:00+00:00", "close": close}


def test_no_trades_means_not_started():
    assert compute_paper_performance([], [candle(10, 100)]) == {"started": False}


def test_buy_then_sell_tracks_cash_btc_and_holding():
    candles = [candle(h, p) for h, p in [(9, 100.0), (10, 100.0), (11, 110.0), (12, 120.0), (13, 90.0)]]
    trades = [
        # Bought at the 11:00 close (candle 10:00), $100 cash -> 1 BTC minus a $1 fee
        {"timestamp": "2026-10-20T11:00:01+00:00", "side": "buy", "price": 99.0, "amount": 1.0,
         "notional": 99.0, "fee": 1.0, "usdt_balance": 0.0, "base_balance": 1.0},
        # Sold at the 13:00 close (candle 12:00) for $120, $1 fee
        {"timestamp": "2026-10-20T13:00:02+00:00", "side": "sell", "price": 120.0, "amount": 1.0,
         "notional": 120.0, "fee": 1.0, "usdt_balance": 119.0, "base_balance": 0.0},
    ]
    out = compute_paper_performance(trades, candles)

    assert out["started"] and out["start_value"] == 100.0 and out["start_price"] == 100.0
    pts = out["points"]
    assert [p["time"][11:16] for p in pts] == ["11:00", "12:00", "13:00", "14:00"]
    # 11:00: holds 1 BTC worth $100 -> 0%; holding also 0%
    assert pts[0]["bot_pct"] == 0.0 and pts[0]["hold_pct"] == 0.0 and pts[0]["holding_btc"]
    # 12:00: BTC $110 -> both +10%
    assert pts[1]["bot_pct"] == 10.0 and pts[1]["hold_pct"] == 10.0
    # 13:00: sold, $119 cash -> +19%; holding +20%
    assert pts[2]["bot_pct"] == 19.0 and pts[2]["hold_pct"] == 20.0 and not pts[2]["holding_btc"]
    # 14:00: BTC drops to $90; the bot is in cash and keeps +19%
    assert pts[3]["bot_pct"] == 19.0 and pts[3]["hold_pct"] == -10.0
    assert out["latest"]["bot_pct"] == 19.0 and out["trade_count"] == 2
