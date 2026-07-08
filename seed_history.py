"""
Seed historical candle data from Binance into the local SQLite database.
Safe to call on every startup — duplicate timestamps are upserted, not duplicated.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def seed_candle_history(exchange, db_manager, symbol: str, timeframe: str, days_back: int = 30) -> int:
    """
    Fetch `days_back` days of OHLCV candles from Binance and store in the database.
    Returns the number of candles stored (new + updated).
    """
    logger.info("Seeding candle history: %d days of %s %s", days_back, symbol, timeframe)

    since_ms = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)
    target_end = exchange.milliseconds()
    batch_size = 1000
    current_since = since_ms
    all_candles = []
    batch_count = 0

    while current_since < target_end:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=batch_size)
        except Exception as exc:
            logger.warning("Candle seed batch %d error: %s", batch_count + 1, exc)
            break

        if not batch:
            break

        # Strip overlap from previous batch
        if all_candles and batch[0][0] <= all_candles[-1][0]:
            batch = [c for c in batch if c[0] > all_candles[-1][0]]

        all_candles.extend(batch)
        batch_count += 1
        current_since = batch[-1][0] + 1

        logger.info("  Batch %d: %d candles fetched (total: %d)", batch_count, len(batch), len(all_candles))

        if len(batch) < batch_size:
            break  # Reached the present

        if batch_count % 3 == 0:
            time.sleep(0.3)  # Be polite to the exchange

    logger.info("Fetched %d candles in %d batches, storing in DB...", len(all_candles), batch_count)

    stored = 0
    for c in all_candles:
        ts = datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).replace(tzinfo=None)
        try:
            db_manager.add_candle({
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": ts,
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            })
            stored += 1
        except Exception as exc:
            logger.debug("Candle insert error (likely duplicate): %s", exc)

    logger.info("Candle history seed complete: %d candles stored", stored)
    return stored
