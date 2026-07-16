# Multi-Strategy Trading System Guide

## 🎯 Overview

The bot supports **four concurrent trading strategies** that can run together, each producing an independent signal that gets combined by an aggregation mode:

- Run multiple strategies simultaneously
- Aggregate signals intelligently (5 aggregation modes)
- Track individual strategy performance (signals generated/used, confidence, acceptance rate)
- Enable/disable strategies dynamically via API, no restart needed
- Configure strategy weights for voting

## 🚀 Quick Start

Edit your `.env` file (or set the equivalent keys via the Configuration page / `strategy_config` database table):

```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_MIN_SIGNAL_CONFIDENCE=0.3

BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0

BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0

BOT_STRATEGY_MACD_ENABLED=true
BOT_STRATEGY_MACD_WEIGHT=1.0

BOT_STRATEGY_LLM_ENABLED=false   # off by default — see LLM_SETUP.md before enabling
BOT_STRATEGY_LLM_WEIGHT=1.0
```

Then restart the bot (`./restart.sh`), or apply via the Configuration page's "Apply Configuration" button for a hot reload without restart.

## 📊 Available Strategies

### 1. EMA Crossover (Trend Following)

**Best for:** trending markets, capturing momentum moves.

- 12/26 EMA crossover to detect trend changes
- RSI filter (avoids extremes), optional MACD confirmation, optional volume confirmation
- ATR-based, volatility-adjusted stop losses

```bash
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_SHORT_WINDOW=12
BOT_LONG_WINDOW=26
```

**Strengths:** reliable, catches sustained moves early. **Weaknesses:** false signals in ranging markets, lags on rapid reversals.

### 2. RSI + Bollinger Bands (Mean Reversion)

**Best for:** ranging markets, oversold/overbought reversals.

- Oversold: RSI < threshold + price at lower BB. Overbought: RSI > threshold + price at upper BB
- Looks for price/RSI divergence, targets mean reversion to the BB middle band
- Tighter stops than trend-following, since the thesis is a smaller reversion move

```bash
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_RSI_OVERSOLD=30
BOT_STRATEGY_RSI_BB_RSI_OVERBOUGHT=70
BOT_STRATEGY_RSI_BB_BB_PERIOD=20
BOT_STRATEGY_RSI_BB_BB_STD_DEV=2.0
```

**Strengths:** high win rate on genuine reversals. **Weaknesses:** repeated false signals in a strong trend.

### 3. MACD + Volume (Momentum Breakout)

**Best for:** breakouts and momentum moves confirmed by volume.

- MACD line/signal crossover for momentum direction
- Volume multiplier filter — requires current volume above `strategy_macd_volume_multiplier` × average to confirm a breakout isn't a low-liquidity fakeout
- `strategy_macd_histogram_threshold` filters out the noisy near-zero histogram right at a fresh crossover
- Optional zero-line-cross requirement for stricter entries

```bash
BOT_STRATEGY_MACD_ENABLED=true
BOT_STRATEGY_MACD_WEIGHT=1.0
BOT_STRATEGY_MACD_FAST_PERIOD=12
BOT_STRATEGY_MACD_SLOW_PERIOD=26
BOT_STRATEGY_MACD_SIGNAL_PERIOD=9
BOT_STRATEGY_MACD_VOLUME_MULTIPLIER=1.3
BOT_STRATEGY_MACD_REQUIRE_ZERO_CROSS=false
BOT_STRATEGY_MACD_HISTOGRAM_THRESHOLD=0.0003
```

**Strengths:** catches explosive volume-confirmed moves. **Weaknesses:** whipsaws in choppy, low-volume conditions.

### 4. LLM Pattern Analysis

**Best for:** an additional, reasoning-based signal layered on top of the technical strategies above. **Disabled by default** (`strategy_llm_enabled: bool = False` in `config.py`) — requires a local Ollama install and its own setup pass.

- Analyzes live market data (RSI, MACD, SMAs, volume ratio, support/resistance) rather than just trade history, so it works from the first candle
- Optionally folds in trade history as extra context if you have some
- Returns direction, confidence, natural-language reasoning, detected patterns, and suggested risk parameters

```bash
BOT_STRATEGY_LLM_ENABLED=false
BOT_STRATEGY_LLM_WEIGHT=1.0
```

Full setup, prompt structure, sampling behavior for backtests, and troubleshooting: see **[LLM_SETUP.md](LLM_SETUP.md)**.

## 🔄 Signal Aggregation Modes

Set via `BOT_STRATEGY_AGGREGATION_MODE` (`strategies/strategy_manager.py`, `SignalAggregationMode`):

| Mode | Behavior | Use when |
|---|---|---|
| `weighted_voting` (default) | Direction with highest weighted-confidence score wins (must exceed 50% of total weight) | Want balanced signals and to weight strategies differently |
| `voting` | Each enabled strategy gets one vote; majority (>50%) wins | Want simple, equal-say democratic voting |
| `unanimous` | All enabled strategies must agree | Want maximum confidence, fewer but higher-quality signals |
| `any` | Any strategy can trigger; uses the most confident signal | Want maximum trading opportunities |
| `best` | Uses whichever signal has the highest confidence, regardless of agreement | Want dynamic strategy selection without requiring consensus |

Example (`weighted_voting`): EMA says BULLISH at confidence 0.7 (weight 1.0) → weighted score 0.7; RSI+BB says NEUTRAL at confidence 0.3 (weight 1.0) → weighted score 0.0. Result: BULLISH, since 0.7 of the (weighted) total exceeds the 50% threshold.

## 📈 Recommended Starting Points

**Conservative** — `unanimous` mode, `BOT_MIN_SIGNAL_CONFIDENCE=0.5`, all technical strategies enabled at equal weight. Only trades when everything agrees.

**Balanced (recommended default)** — `weighted_voting`, `BOT_MIN_SIGNAL_CONFIDENCE=0.3`, weight the strategy that fits current conditions slightly higher (e.g. EMA 1.2 in a trending market).

**Active/aggressive** — `any` mode, `BOT_MIN_SIGNAL_CONFIDENCE=0.25`. Maximizes trading opportunities; either strategy can trigger.

**Single-regime focus** — disable strategies that don't fit the current regime rather than tuning weights around them: disable RSI+BB in a strong trend, disable EMA/MACD in a ranging market.

Note: walk-forward testing across 6 non-overlapping 30-day windows (see `docs/backtest_reports/` and the `walk_forward_*_only.py` scripts) found no standalone edge for EMA-only, RSI+BB-only, or MACD-only against recent BTC/USDT 1h data — treat any of these starting points as a hypothesis to validate with your own backtests, not an assumed edge.

## 📊 Dashboard & Monitoring

```bash
# List strategies and their enabled/weight state
curl -u admin:password http://localhost:8000/api/strategies

# Per-strategy signal/acceptance stats
curl -u admin:password http://localhost:8000/api/strategies/stats

# Enable / disable / toggle a strategy at runtime (persists to the database)
curl -X POST -u admin:password http://localhost:8000/api/strategies/EMA_Crossover/enable
curl -X POST -u admin:password http://localhost:8000/api/strategies/EMA_Crossover/disable
curl -X POST -u admin:password http://localhost:8000/api/strategies/EMA_Crossover/toggle
```

`/api/strategies/stats` returns, per strategy: `signals_generated`, `signals_used`, `avg_confidence`, `generation_rate`, `usage_rate`, `acceptance_rate`.

| Acceptance rate | Meaning |
|---|---|
| >70% | Strategy dominates aggregation — consider whether its weight is too high |
| 40-70% | Healthy contribution |
| 20-40% | Normal for strict aggregation modes (`unanimous`) |
| <20% | Too filtered — check aggregation mode, confidence threshold, or whether this strategy fits current market conditions |

## 🔍 Database Schema

Trades carry strategy attribution:

```sql
SELECT timestamp, side, price, pnl, strategy_name, signal_confidence
FROM trades WHERE strategy_name = 'EMA_Crossover'
ORDER BY timestamp DESC LIMIT 10;

SELECT strategy_name, COUNT(*) AS trades,
       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winning_trades,
       AVG(pnl) AS avg_pnl, SUM(pnl) AS total_pnl
FROM trades WHERE strategy_name IS NOT NULL
GROUP BY strategy_name;
```

## 🛠️ Adding a New Strategy

1. Create `strategies/my_strategy.py`:
   ```python
   from .base_strategy import BaseStrategy, StrategySignal

   class MyCustomStrategy(BaseStrategy):
       def __init__(self, config: dict):
           super().__init__("MyCustom", config)

       def compute_signal(self, exchange, symbol, timeframe, candle_data=None):
           # strategy logic here; return a StrategySignal
           pass

       def get_description(self) -> str:
           return "My custom strategy description"

       def get_parameters(self) -> dict:
           return {"param1": self.param1}
   ```
2. Register it in `strategies/__init__.py`'s `__all__` and wherever `strategy_manager.py` instantiates the built-in strategies.
3. Add its config fields to `config.py` following the pattern used for MACD/LLM (env var + database-backed key + default).

## 📊 Backtesting Multiple Configurations

```bash
python backtest.py 30    # 30-day backtest using current .env / database config
```

The backtest automatically uses your enabled strategies, weights, and aggregation mode — results should match what live trading would have done with that config.

**What to vary when comparing configs:**
- **Isolate one strategy** — disable the others (`strategy_*_enabled=False`) to see its standalone contribution. For a repeatable, multi-window version of this, see `scripts/walk_forward_ema_only.py` / `walk_forward_macd_only.py` / `walk_forward_rsi_bb_only.py`.
- **Aggregation mode** — rerun the same window under `weighted_voting`, `unanimous`, `any`, `best`, `voting` and compare win rate / P&L / acceptance rates.
- **Strategy weights** — favor one strategy over another (e.g. `EMA_WEIGHT=1.5`, `RSI_BB_WEIGHT=0.8`) and see if it improves results, rather than assuming equal weight is optimal.
- **Confidence threshold** — sweep `BOT_MIN_SIGNAL_CONFIDENCE` (e.g. 0.2 / 0.3 / 0.5) to trade off signal frequency against quality.
- **Time period** — a single 30/60-day window is a small sample; compare multiple non-overlapping windows before trusting a result (see the walk-forward scripts and `docs/backtest_reports/` for the existing methodology and its caveats around overfitting to a re-tested window).

## 🐛 Troubleshooting

**No signals being generated:** confirm the strategy is enabled (`BOT_STRATEGY_*_ENABLED=true`), multi-strategy mode is on (`BOT_USE_MULTI_STRATEGY=true`), and the confidence threshold isn't too high — try `BOT_MIN_SIGNAL_CONFIDENCE=0.2` or a looser aggregation mode (`weighted_voting`/`any`) as a diagnostic step.

**Too many signals:** raise `BOT_MIN_SIGNAL_CONFIDENCE`, switch to a stricter aggregation mode (`unanimous`), or disable a strategy that's overtrading.

**Strategies constantly disagree (low acceptance rates across the board):** try `best` or `any` mode, adjust weights to favor the strategy that fits current conditions, or disable the strategy that doesn't fit the current regime rather than trying to out-vote it.

**"Multi-strategy system not available":** confirms `strategies/` package is present and `BOT_USE_MULTI_STRATEGY=true` — check `curl -u admin:password http://localhost:8000/api/strategies` for the `multi_strategy_enabled` flag.

## 💡 Pro Tips

1. **Match strategy to regime**: increase EMA/MACD weight in trending markets, increase RSI+BB weight when ranging, favor `unanimous` mode in choppy/volatile conditions.
2. **Confidence threshold**: start at 0.3 — higher means fewer, better signals; lower means more signals with more noise.
3. **Weights don't need to be 1.0** — try 1.5 for a primary strategy and 0.8 for a secondary one, and validate the choice with a backtest rather than intuition.
4. **Check `/api/strategies/stats` regularly** — a strategy with a persistently low acceptance rate isn't contributing and is a candidate to disable or reweight.
5. **Backtest before changing live config** — and remember a single window is a small sample; see the walk-forward scripts for a multi-window methodology.

## 🎓 Code References

- `strategies/base_strategy.py` — strategy interface
- `strategies/ema_crossover_strategy.py`, `strategies/rsi_bb_strategy.py`, `strategies/macd_volume_strategy.py` — the three technical strategies
- `strategies/llm/` — LLM pattern strategy (`strategy.py`, `market_data.py`, `indicators.py`, `prompt_builder.py`, `llm_client.py`, `response_parser.py`, `cache_manager.py`)
- `strategies/strategy_manager.py` — signal aggregation logic

## 📞 Support

Check logs (`./status.sh` or `tail -f logs/bot.log`), review live config (`/api/config`), check strategy stats (`/api/strategies/stats`), and test any change in backtest before applying it live.

## 🎉 What Good Multi-Strategy Performance Looks Like

- Win rate >50% and positive P&L, beating buy-and-hold over the tested window
- More than one strategy actually contributing (not one at >70% acceptance while others sit under 20%)
- Consistent results across multiple non-overlapping time windows, not just one lucky period

---

**Happy multi-strategy trading!**
