# LLM Pattern Analysis Strategy - Setup Guide

This guide will help you set up the LLM Pattern Analysis Strategy, which uses local AI models via Ollama to analyze your trading history and identify patterns.

## Overview

The LLM strategy uses a locally-running large language model to:
- Analyze your last N days of trade history
- Identify patterns in winning vs losing trades
- Detect support/resistance levels from past trades
- Generate trading signals with detailed reasoning
- Cache results to avoid expensive repeated analysis

## Prerequisites

- Trading bot already installed and configured
- At least 3 trades in your database history (more is better)
- 4GB+ RAM recommended for running LLM models
- Stable internet connection for initial model download

## Step 1: Install Ollama

Ollama is a tool for running large language models locally on your machine.

### macOS/Linux

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Verify installation
ollama --version
```

### Windows

Download and install from: https://ollama.ai/download

## Step 2: Pull an LLM Model

The bot supports several models. We recommend starting with **Mistral** for the best balance of speed and quality.

```bash
# Recommended: Mistral (fast and accurate)
ollama pull mistral

# Alternative models:
# ollama pull llama2          # Good general-purpose model
# ollama pull llama2:13b      # Larger, more capable (needs 16GB+ RAM)
# ollama pull phi             # Fastest, smallest model
# ollama pull codellama       # Good for technical analysis
```

## Step 3: Start Ollama Service

Ollama needs to be running in the background for the bot to use it.

```bash
# Start Ollama server (keep this terminal open)
ollama serve
```

**Important**: Keep this terminal window open while the trading bot is running, or set up Ollama as a system service (see below).

## Step 4: Configure the Bot

The LLM strategy is pre-configured with sensible defaults, but you can customize it in your `.env` file or via the web dashboard.

### Environment Variables (`.env` file)

```bash
# Enable/disable LLM strategy
BOT_STRATEGY_LLM_ENABLED=true

# Strategy weight (relative to other strategies)
BOT_STRATEGY_LLM_WEIGHT=1.0

# Ollama configuration
BOT_LLM_OLLAMA_URL=http://localhost:11434
BOT_LLM_OLLAMA_MODEL=mistral

# Analysis parameters
BOT_LLM_LOOKBACK_DAYS=7          # Days of history to analyze
BOT_LLM_CACHE_MINUTES=15         # Cache analysis for 15 minutes
BOT_LLM_TIMEOUT_SECONDS=60       # Timeout for LLM requests
BOT_LLM_REQUIRE_PATTERNS=false   # Only generate signals if patterns found
```

### Web Dashboard Configuration

1. Navigate to **Strategy Configuration** page
2. Scroll to **LLM Pattern Analysis Strategy** section
3. Adjust parameters:
   - **Strategy Weight**: Influence relative to other strategies (0.0-2.0)
   - **Ollama Model**: Select from dropdown (mistral, llama2, phi, etc.)
   - **Lookback Days**: How many days of trade history to analyze (1-30)
   - **Cache Refresh Interval**: How often to run new analysis (5-120 minutes)
   - **Analysis Timeout**: Max seconds to wait for LLM response (30-300)
   - **Ollama URL**: Change if running Ollama on different machine
   - **Require Pattern Detection**: Only generate signals if LLM finds patterns

4. Click "Test Connection" to verify Ollama is accessible
5. Click "Run Analysis Now" to trigger immediate analysis
6. Click "Save Configuration" to persist changes

## Step 5: Verify Setup

### Test LLM Connection

```bash
# Test if Ollama is running and model is available
curl http://localhost:11434/api/version

# Test model inference
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "Analyze this trading pattern: Buy at $50000, Sell at $51000. What do you observe?",
  "stream": false
}'
```

### Check Bot Logs

Start your trading bot and watch for LLM-related log messages:

```bash
python main.py
```

Look for:
```
✓ Enabled: llm_pattern (weight: 1.0)
LLM pattern analysis scheduler started
Starting scheduled LLM pattern analysis...
LLM analysis complete: bullish (confidence: 0.75, patterns: 3, duration: 8.2s)
```

### View Results in Dashboard

1. Open dashboard: http://localhost:8000
2. Go to **Strategy Configuration** page
3. Scroll to LLM Strategy section
4. Click "Run Analysis Now"
5. Check the result display area for analysis output

## Step 6: Understanding LLM Analysis Output

The LLM will provide:

- **Direction**: `bullish` (buy signal), `bearish` (sell signal), or `neutral` (no trade)
- **Confidence**: 0.0 to 1.0 (how confident the LLM is in its analysis)
- **Reasoning**: Natural language explanation of the decision
- **Patterns Found**: List of specific patterns identified (e.g., "Support at $50000", "Resistance at $52000")
- **Suggested Risk Parameters**: Stop loss, take profit, and position size

Example output:
```json
{
  "direction": "bullish",
  "confidence": 0.78,
  "reasoning": "Recent trades show strong support at $48000 with multiple bounces. Win rate is 65% on upward moves above this level. Current price near support suggests buying opportunity.",
  "patterns_found": [
    "Support level at $48000 (3 successful buys)",
    "Resistance at $52000 (2 exits)",
    "Higher win rate on morning trades",
    "Average winning trade: +$850, Average loss: -$320"
  ],
  "suggested_stop_loss": 47500,
  "suggested_take_profit": 51500,
  "suggested_position_size": 0.30
}
```

## Market Data Analysis (What the LLM Actually Sees)

The strategy analyzes live market data, not just your bot's trade history — it works from the first candle, with no minimum trade count required. Each analysis cycle:

1. Fetches ~100 recent candles from the exchange
2. Calculates RSI(14), MACD, SMA 20/50, and a volume ratio (current vs. average)
3. Detects support/resistance from recent swing highs/lows
4. Optionally folds in your trade history (3+ trades) as extra context, if available
5. Sends all of the above to the LLM and caches the result for `BOT_LLM_CACHE_MINUTES`

The LLM returns direction, confidence, reasoning, detected patterns, and suggested stop-loss/take-profit/position size (see the example JSON in Step 6 above). Trade-history context is a bonus input, not a requirement — so backtests and fresh bots get real signals immediately instead of "not enough trade history, returning neutral."

## Backtest Sampling (Why Backtests Don't Analyze Every Candle)

Calling the LLM on every candle is too slow to be practical: at ~8s/call, a 7-day backtest on 5m candles (2,016 candles) would take ~4.5 hours. `BOT_LLM_BACKTEST_SAMPLE_INTERVAL` (default `12`) makes backtests analyze only every Nth candle and reuse the last analysis for the candles in between — live trading and manual "Run Analysis Now" are unaffected by this setting and always analyze immediately.

| Interval | 5m timeframe | 1h timeframe | Use case |
|---|---|---|---|
| 1 | every candle | every candle | testing only, very slow |
| 12 | every hour | every 12h | **default** |
| 24 | every 2h | every day | less frequent |
| 50+ | quick smoke-test runs | — | fast iteration, fewer trade opportunities |

Match the interval to your timeframe's actual cadence — 12 candles means something very different on 5m vs. 1h vs. 4h.

## Troubleshooting: Backtest Produces Zero Trades / Only Neutral Signals

Work through these in order — they're the common causes, roughly most-to-least likely:

1. **LLM is genuinely returning `neutral`.** LLMs default to caution on mixed signals. Try: lower `BOT_MIN_SIGNAL_CONFIDENCE` (e.g. `0.2`), raise `llm_temperature` (e.g. `0.5`) for more decisive output, or test on a clearly trending period — ranging/choppy markets produce more neutrals.
2. **Signal generated but below the confidence threshold.** Check `BOT_MIN_SIGNAL_CONFIDENCE` (default 0.3) and try `BOT_LLM_REQUIRE_PATTERNS=false`.
3. **Multi-strategy aggregation is filtering it out.** `unanimous` mode requires every enabled strategy to agree; `weighted_voting` with a low `BOT_STRATEGY_LLM_WEIGHT` can get outvoted. To isolate the LLM strategy for testing, disable EMA/RSI_BB/MACD and set aggregation to `any`.
4. **Sample interval too sparse for the backtest length.** E.g. a 100-candle backtest with `sample_interval=50` only analyzes twice — reduce the interval or extend the backtest window.
5. **Suggested position size below your minimum.** Check `BOT_MIN_POSITION_SIZE` against what the LLM is suggesting.

To confirm sampling and signals are actually running, watch for this pattern in the logs:
```
llm_pattern: Backtest configured - 168 candles, sampling every 12 = 14 analyses
llm_pattern: Generated signal - BULLISH (confidence: 65.0%, position: 25.0%)
```
If confidence stays low across a full backtest with a trending period and `require_patterns=false`, that's likely a genuine reflection of mixed market conditions rather than a config problem.

## Speed Tuning

If a single analysis takes 60-90s (vs. a healthy 8-15s), in rough order of impact:

- **Reduce `BOT_LLM_BACKTEST_SAMPLE_INTERVAL`** first — fewer LLM calls is the single biggest lever for backtest wall-clock time.
- **Shorten responses**: lower `llm_num_predict` (e.g. `500`) and `BOT_LLM_LOOKBACK_DAYS` (e.g. `3`).
- **RAG does not speed anything up** — it adds retrieved context to the prompt for better accuracy, which means *more* tokens to process, not fewer. Don't disable it expecting a speed win; disable it only if you're deliberately trading accuracy for raw speed.
- **Check GPU acceleration**: on macOS, Activity Monitor → GPU History while a request runs. Apple Silicon should use the GPU automatically; if usage is flat at 0%, restart Ollama (`pkill ollama && ollama serve`) — CPU-only inference is the most common cause of 60s+ responses.
- **Smaller/faster model**: `phi3` is both faster and more consistently JSON-compliant than `mistral` for this use case.
- **Cloud LLM as a last resort**: OpenAI/Anthropic APIs run 2-6s per analysis instead of local inference time, at the cost of a small per-call fee and requiring `llm_client.py` to support that provider.

## Advanced Configuration

### Running Ollama as a System Service

#### macOS (using launchd)

Create `/Library/LaunchDaemons/com.ollama.service.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ollama.service</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/ollama</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

```bash
sudo launchctl load /Library/LaunchDaemons/com.ollama.service.plist
```

#### Linux (using systemd)

Create `/etc/systemd/system/ollama.service`:

```ini
[Unit]
Description=Ollama LLM Service
After=network.target

[Service]
Type=simple
User=your_username
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Using Remote Ollama Instance

If you want to run Ollama on a different machine (e.g., a powerful server):

1. On the remote machine, start Ollama with network binding:
   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ```

2. In your bot's `.env` file, update the URL:
   ```bash
   BOT_LLM_OLLAMA_URL=http://192.168.1.100:11434
   ```

### Model Selection Guide

| Model | Size | Speed | Quality | RAM Required | Best For |
|-------|------|-------|---------|--------------|----------|
| **mistral** | 4.1GB | Fast | Excellent | 8GB | **Recommended default** |
| llama2 | 3.8GB | Fast | Good | 8GB | General trading analysis |
| llama2:13b | 7.4GB | Medium | Excellent | 16GB | Deep analysis, complex patterns |
| phi | 1.6GB | Very Fast | Fair | 4GB | Quick signals, limited resources |
| codellama | 3.8GB | Fast | Good | 8GB | Technical indicator analysis |

### Performance Tuning

#### Faster Analysis
- Use smaller models (`phi`, `llama2`)
- Reduce `BOT_LLM_LOOKBACK_DAYS` (e.g., 3-5 days)
- Increase `BOT_LLM_CACHE_MINUTES` (e.g., 30-60 minutes)
- Lower `BOT_LLM_TIMEOUT_SECONDS`

#### Better Quality
- Use larger models (`llama2:13b`)
- Increase `BOT_LLM_LOOKBACK_DAYS` (e.g., 14-30 days)
- Ensure you have sufficient trade history (50+ trades)
- Enable `BOT_LLM_REQUIRE_PATTERNS=true` for conservative signals

## Troubleshooting

### "Cannot connect to Ollama"

**Problem**: Bot can't reach Ollama service

**Solutions**:
1. Check if Ollama is running: `ps aux | grep ollama` or `curl http://localhost:11434/api/version`
2. Start Ollama: `ollama serve`
3. Verify the URL in config matches (default: `http://localhost:11434`)
4. Check firewall settings if using remote Ollama

### "Model not found"

**Problem**: Selected model hasn't been downloaded

**Solution**: 
```bash
# List available models
ollama list

# Pull the missing model
ollama pull mistral
```

### "LLM request timed out"

**Problem**: Analysis taking too long

**Solutions**:
1. Use a faster model (`mistral` or `phi`)
2. Increase `BOT_LLM_TIMEOUT_SECONDS` in config
3. Reduce `BOT_LLM_LOOKBACK_DAYS`
4. Check system resources (RAM, CPU)

### "No LLM analysis available yet"

**Problem**: Analysis hasn't run since bot started

**Solutions**:
1. Wait 15-60 seconds for initial analysis to complete
2. Manually trigger analysis via dashboard "Run Analysis Now" button
3. Check logs for error messages
4. Verify you have at least 3 trades in database

### "Insufficient trade history"

**Problem**: Not enough trades for meaningful analysis

**Solutions**:
1. Run bot for more time to accumulate trade history
2. Reduce `BOT_LLM_LOOKBACK_DAYS` to use fewer trades
3. Import historical trades if available
4. Consider using other strategies until history builds up

### High Memory Usage

**Problem**: Ollama consuming too much RAM

**Solutions**:
1. Use smaller model (`phi` instead of `llama2:13b`)
2. Close other applications
3. Increase system swap space
4. Run Ollama on a separate machine with more RAM

## Integration with Other Strategies

The LLM strategy works alongside other strategies (EMA, RSI+BB, MACD) in the multi-strategy system.

### Aggregation Modes

- **weighted_voting** (default): LLM signal is weighted by its confidence and strategy weight
- **unanimous**: All strategies (including LLM) must agree
- **any**: Trade if LLM OR any other strategy signals
- **best**: Use the strategy with highest confidence

Set in config:
```bash
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
```

### Strategy Weights

Adjust relative influence:
```bash
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
BOT_STRATEGY_MACD_WEIGHT=1.0
BOT_STRATEGY_LLM_WEIGHT=1.5   # Give LLM 50% more influence
```

## Best Practices

1. **Start Conservative**: Use `BOT_LLM_REQUIRE_PATTERNS=true` initially
2. **Monitor Performance**: Track which LLM signals lead to profitable trades
3. **Experiment with Models**: Different models have different strengths
4. **Adjust Lookback Period**: Match to your trading timeframe (day trading = 3-7 days, swing trading = 14-30 days)
5. **Cache Appropriately**: Balance freshness vs computation cost (15-30 min cache is usually good)
6. **Review LLM Reasoning**: Read the analysis explanations in dashboard to understand bot's decisions
7. **Combine with Other Strategies**: LLM works best as one input among multiple signals

## Resources

- **Ollama Documentation**: https://github.com/jmorganca/ollama
- **Model Library**: https://ollama.ai/library
- **Bot Strategy Guide**: See `MULTI_STRATEGY_GUIDE.md`
- **Dashboard Guide**: See `MANUAL_TRADING_GUIDE.md`

## Support

If you encounter issues not covered here:

1. Check bot logs for detailed error messages
2. Test Ollama independently with `ollama run mistral "test"`
3. Verify model is working: `curl http://localhost:11434/api/generate -d '{"model": "mistral", "prompt": "test"}'`
4. Review `llm_scheduler.py` and app logs (`logs/app.log`, `logs/bot_error.log`)

---

**Note**: LLM analysis is computationally expensive. The first analysis after bot startup may take 10-60 seconds depending on your hardware and model size. Subsequent analyses use cached results when possible.

**Warning**: LLM-generated signals should be one component of your trading strategy, not the sole decision maker. Always combine with technical analysis and risk management.
