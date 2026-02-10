# Dashboard Restart Instructions

## The Issue
The packages are installed, but the dashboard needs to be restarted to load them.

## How to Restart

### Step 1: Stop the Dashboard
In the terminal where the dashboard is running:
- Press `Ctrl + C`
- Wait for it to stop completely

### Step 2: Start Again
```bash
cd /Users/toninichev/Applications/trading.toninichev.com
python3 dashboard.py
```

### Step 3: Look for Success Messages
You should see:
```
✅ chromadb imported successfully
✅ sentence-transformers imported successfully
```

If you still see warnings about missing modules, the dashboard is using a different Python.

## Alternative: Use the Exact Python Binary

If restart doesn't work, start with the exact Python path:
```bash
/Library/Developer/CommandLineTools/usr/bin/python3 dashboard.py
```

## After Restart

1. Go to http://localhost:8000
2. Strategy Configuration page
3. Click "Check Status"
4. Should see "✅ RAG Ready"
