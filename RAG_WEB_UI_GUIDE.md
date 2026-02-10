# RAG Web UI Management Guide

## ✅ What's New

You can now **manage RAG indexing directly from the Web UI**! No need to run command-line scripts.

## 📍 Where to Find It

1. Open your dashboard: `http://localhost:8000`
2. Navigate to: **Strategy Configuration** page
3. Scroll to: **🤖 LLM Pattern Analysis Strategy** section
4. Find: **🔍 RAG (Retrieval Augmented Generation)** box (blue)

## 🎯 Available Actions

### Check Status
Click **"Check Status"** button to see:
- ✅ Is RAG available and enabled?
- 📊 How many trades are indexed?
- 💡 Is RAG ready to use?
- 🔢 Configuration details

**Example Output:**
```
✅ RAG Ready
📊 Trades Indexed: 150 / 5 required
🔢 Retrieves: 10 similar trades per query
💾 Storage: ./data/chroma_db
🤖 Model: all-MiniLM-L6-v2
```

### Index Trades
Click **"Index Trades"** button to:
- 📥 Import all historical trades from database
- 🔄 Convert to semantic embeddings
- 💾 Store in vector database for fast search
- ⏱️ Takes ~1-2 seconds per 100 trades

**Example Output:**
```
✅ Successfully indexed 150 trades
📊 Total Indexed: 150 trades
⏱️ Duration: 3.2s
💡 RAG is now active and ready!
```

## 🔄 Typical Workflow

### First Time Setup (New Bot)
1. Start your bot: `python3 main.py`
2. Let it trade for a while (accumulate 5+ trades)
3. Open Web UI → Strategy Configuration
4. Click **"Check Status"** → See how many trades you have
5. Click **"Index Trades"** → RAG will index them
6. ✅ Done! RAG is now active

### Periodic Maintenance (Ongoing)
As you accumulate more trades:
1. Visit Strategy Configuration page
2. Click **"Index Trades"** weekly/monthly
3. New trades get indexed automatically
4. Keeps RAG context fresh and relevant

## 🎨 Visual Indicators

### Status Colors
- 🟢 **Green** - RAG ready and working
- 🟡 **Yellow** - RAG available but waiting for trades
- 🔴 **Red** - RAG not available (dependencies missing)

### Messages
- ✅ **RAG Ready** - Active with enough trades
- ⏳ **Waiting for trades** - Need more trade history
- ❌ **Not Available** - Dependencies not installed

## 📊 API Endpoints

The Web UI uses these endpoints (you can also use them directly):

### GET `/api/rag/status`
Check RAG system status
```bash
curl http://localhost:8000/api/rag/status
```

### POST `/api/rag/index`
Trigger trade indexing
```bash
curl -X POST http://localhost:8000/api/rag/index \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000, "batch_size": 50}'
```

## 🔧 Configuration

RAG settings are in `.env` or dashboard:
```bash
BOT_LLM_USE_RAG=true              # Enable/disable RAG
BOT_LLM_RAG_NUM_RESULTS=10        # Similar trades to retrieve
BOT_LLM_RAG_MIN_TRADES=5          # Minimum trades needed
```

## ❓ Troubleshooting

### "RAG Not Available"
**Problem**: Dependencies not installed

**Solution**:
```bash
pip install chromadb sentence-transformers
# Restart dashboard after installing
```

### "Waiting for trades"
**Problem**: Not enough trade history

**Solution**:
- Run bot for a while to accumulate trades
- Or: Lower minimum in config: `BOT_LLM_RAG_MIN_TRADES=3`
- Check status shows: `0 / 5 required` → need 5 more trades

### "Indexing Failed"
**Problem**: Database or permissions issue

**Solutions**:
1. Check database is accessible
2. Check `./data/chroma_db/` is writable
3. Try CLI: `python3 index_trades_rag.py` for detailed error

### Button Does Nothing
**Problem**: JavaScript error or network issue

**Solutions**:
1. Check browser console for errors (F12 → Console)
2. Refresh page and try again
3. Check dashboard logs for API errors

## 💡 Tips

### When to Index
- **After setup**: Index once you have 5+ trades
- **Weekly**: If actively trading
- **Monthly**: If trading infrequently
- **After backtests**: If backtests create trade records

### Performance
- Indexing 100 trades: ~1-2 seconds
- Indexing 1000 trades: ~10-20 seconds
- First index downloads model (~80MB, one-time)

### Storage
- Vector database: `./data/chroma_db/`
- Size: ~10MB per 1000 trades
- Include in backups alongside `./data/trading.db`

## 🎯 Verification

After indexing, verify RAG is working:

1. **Check Status Button**: Should show "RAG Ready"
2. **Bot Logs**: Look for:
   ```
   llm_pattern: RAG enabled - 150 trades indexed
   llm_pattern: RAG context - 10 similar trades (70% win rate)
   ```
3. **LLM Analysis**: Should be faster (2-3s vs 10-15s)

## 🆚 CLI vs Web UI

| Feature | CLI | Web UI |
|---------|-----|--------|
| **Index Trades** | `python3 index_trades_rag.py` | Click "Index Trades" |
| **Check Status** | `python3 index_trades_rag.py --stats` | Click "Check Status" |
| **Clear Index** | `python3 index_trades_rag.py --clear` | Not available (use CLI) |
| **Convenience** | Requires terminal | Browser-based |
| **Automation** | Can script/cron | Manual clicks |

**Recommendation**: Use Web UI for quick management, CLI for automation/scripting.

## 📚 Related Docs

- `RAG_QUICKSTART.md` - Initial setup guide
- `RAG_IMPLEMENTATION.md` - Technical details
- `RAG_STATUS.md` - Current installation status

---

**You're all set!** RAG indexing is now just two clicks away. 🎉
