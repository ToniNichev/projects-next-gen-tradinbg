# 📊 Trade Indicator Data Flow
## How Buy/Sell Markers Get from Strategy to Chart

---

## 🔄 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. STRATEGY GENERATES SIGNAL                  │
│                                                                   │
│  strategies.py (EMA_Crossover, RSI_BB, MACD, etc.)              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  signal = {                                                │  │
│  │    "direction": "bullish",           ← Signal direction    │  │
│  │    "strategy_name": "EMA_Crossover", ← Strategy that made  │  │
│  │    "confidence": 0.75,                  this signal        │  │
│  │    "price": 50000,                                         │  │
│  │    "indicators": {...}                                     │  │
│  │  }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                      2. TRADER EXECUTES TRADE                    │
│                                                                   │
│  paper_trader.py → handle_signal()                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  trade = TradeRecord(                                      │  │
│  │    side="buy",                                             │  │
│  │    price=50000,                                            │  │
│  │    amount=0.01,                                            │  │
│  │    signal=signal  ← Keeps full signal object              │  │
│  │  )                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                 3A. BACKTEST PATH (In-Memory)                    │
│                                                                   │
│  backtest.py → chart_data["trades"]                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  {                                                         │  │
│  │    "strategy_name": "EMA_Crossover",  ✅ CORRECT          │  │
│  │    "signal_direction": "EMA_Crossover", (compatibility)   │  │
│  │    "side": "buy",                                          │  │
│  │    "price": 50000,                                         │  │
│  │    ...                                                     │  │
│  │  }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  backtest.html (line 1410-1435)                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  const strategyName = t.strategy_name || 'Unknown';       │  │
│  │  ✅ Correctly uses strategy_name field                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  RESULT: ✅ Each strategy gets its own color                     │
└─────────────────────────────────────────────────────────────────┘

                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                  3B. LIVE/PAPER TRADING PATH                     │
│                                                                   │
│  paper_trader.py → _log_trade() → database                       │
│  Lines 149, 159:                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  trade_data = {                                            │  │
│  │    "signal_direction": trade.signal.get("direction"),     │  │
│  │                        ↑                                   │  │
│  │                    Stores "bullish" or "bearish"           │  │
│  │                                                            │  │
│  │    "strategy_name": trade.signal.get("strategy_name"),    │  │
│  │                     ↑                                      │  │
│  │                Stores "EMA_Crossover", etc.                │  │
│  │    ...                                                     │  │
│  │  }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                      4. DATABASE STORAGE                         │
│                                                                   │
│  SQLite: data/trading.db → trades table                          │
│  ┌──────────────┬─────────────────┬─────────────────────┐       │
│  │  timestamp   │ signal_direction│   strategy_name     │       │
│  ├──────────────┼─────────────────┼─────────────────────┤       │
│  │  10:00:00    │    bullish      │   EMA_Crossover     │       │
│  │  10:30:00    │    bullish      │   RSI_BB_Mean...    │       │
│  │  11:00:00    │    bearish      │   MACD_Volume...    │       │
│  └──────────────┴─────────────────┴─────────────────────┘       │
│                                                                   │
│  ⚠️ NOTE: TWO SEPARATE FIELDS!                                   │
│    - signal_direction: Direction of signal (bullish/bearish)     │
│    - strategy_name: Which strategy made it (EMA/RSI/MACD)        │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                     5. API ENDPOINT RETURNS DATA                 │
│                                                                   │
│  app.py → /api/trades                                            │
│  Returns JSON array of trades from database                      │
│  [                                                                │
│    {                                                              │
│      "timestamp": "2026-02-11T10:00:00Z",                        │
│      "signal_direction": "bullish",    ← Direction               │
│      "strategy_name": "EMA_Crossover", ← Strategy name           │
│      "side": "buy",                                              │
│      "price": 50000,                                             │
│      ...                                                          │
│    }                                                              │
│  ]                                                                │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                    6. DASHBOARD CHART RENDERS                    │
│                                                                   │
│  ui.html → updateTradeMarkers() → Line 1246                      │
│                                                                   │
│  ❌ CURRENT (BROKEN):                                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  const strategyName = trade.signal_direction || 'Unknown';│  │
│  │                            ↑                               │  │
│  │                      Uses DIRECTION field!                │  │
│  │                                                            │  │
│  │  Result:                                                   │  │
│  │    All "bullish" trades → grouped as "bullish" (1 color)  │  │
│  │    All "bearish" trades → grouped as "bearish" (1 color)  │  │
│  │    ❌ Can't distinguish strategies!                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ✅ FIXED (CORRECT):                                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  const strategyName = trade.strategy_name || 'Unknown';   │  │
│  │                            ↑                               │  │
│  │                      Uses STRATEGY NAME field!            │  │
│  │                                                            │  │
│  │  Result:                                                   │  │
│  │    "EMA_Crossover" → Cyan triangles                       │  │
│  │    "RSI_BB_MeanReversion" → Pink triangles                │  │
│  │    "MACD_Volume_Momentum" → Gold triangles                │  │
│  │    ✅ Each strategy has its own color!                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                      7. VISUAL RESULT ON CHART                   │
│                                                                   │
│  ❌ BEFORE FIX:                          ✅ AFTER FIX:           │
│                                                                   │
│  All trades one/two colors:             Each strategy colored:   │
│  ▲ Gray/Unknown (bullish)               ▲ Cyan (EMA)            │
│  ▲ Gray/Unknown (bullish)               ▲ Pink (RSI+BB)         │
│  ▼ Gray/Unknown (bearish)               ▲ Gold (MACD)           │
│                                          ▼ Cyan (EMA)            │
│  Can't tell strategies apart            Clear strategy distinction│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Insight

The bug is a **field name mismatch** at visualization time:

| Location | Field Used | Content | Correct? |
|----------|-----------|---------|----------|
| **Database Storage** | `signal_direction` | "bullish"/"bearish" | ✅ Correct storage |
| **Database Storage** | `strategy_name` | "EMA_Crossover"/etc | ✅ Correct storage |
| **Backtest Chart** | `strategy_name` | "EMA_Crossover"/etc | ✅ Correct usage |
| **Dashboard Chart** | `signal_direction` | "bullish"/"bearish" | ❌ Wrong field! |

**Fix:** Dashboard should use `strategy_name` field like Backtest does.

---

## 📋 Field Comparison Table

| Field Name | Purpose | Example Values | Used For |
|------------|---------|----------------|----------|
| `signal_direction` | Signal direction | "bullish", "bearish", "neutral" | Determining if buy/sell |
| `strategy_name` | Strategy identifier | "EMA_Crossover", "RSI_BB_MeanReversion", "MACD_Volume_Momentum", "LLM_Pattern" | Coloring markers by strategy |
| `side` | Trade execution side | "buy", "sell" | Determining marker direction |
| `confidence` | Signal confidence | 0.0 - 1.0 | Filtering weak signals |

**Dashboard was using the wrong field for grouping/coloring!**

---

## 🔧 The Fix (One Line)

```diff
File: templates/ui.html
Line: 1246

- const strategyName = trade.signal_direction || 'Unknown';
+ const strategyName = trade.strategy_name || 'Unknown';
```

**This changes:**
- FROM: Group by "bullish" vs "bearish" (wrong)
- TO: Group by "EMA_Crossover" vs "RSI_BB" vs "MACD" (correct)

---

## 🎨 Color Assignment Logic

After fix, colors are assigned like this:

```javascript
// templates/ui.html lines 884-892
const STRATEGY_COLORS = {
  'EMA_Crossover': '#00D9FF',        // Cyan
  'RSI_BB_MeanReversion': '#FF6B9D', // Pink  
  'MACD_Volume_Momentum': '#FFD700', // Gold
  'llm_pattern': '#9D4EDD',          // Purple
  'LLM_Pattern': '#9D4EDD',          // Purple
  'Aggregated': '#FFFFFF',           // White
  'Unknown': '#808080',              // Gray
};

// Get color for this trade's strategy
const strategyName = trade.strategy_name;  // "EMA_Crossover"
const color = STRATEGY_COLORS[strategyName]; // '#00D9FF' (cyan)

// Create marker with this color
{
  label: `🟢 EMA Crossover BUY`,
  backgroundColor: '#00D9FF',  // Cyan
  borderColor: '#ffffff',
  // ... marker will appear as cyan triangle
}
```

**Result:** Each strategy gets its distinct color automatically!
