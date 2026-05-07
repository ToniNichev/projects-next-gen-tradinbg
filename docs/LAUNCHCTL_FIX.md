# LaunchAgent Fix for Modern macOS

## ✅ What Was Fixed

The original service management scripts used deprecated `launchctl load/unload` commands that don't work on modern macOS versions (10.11+). 

### Changes Made:

1. **Updated `start.sh`** - Now uses `launchctl bootstrap` (modern command)
2. **Updated `stop.sh`** - Now uses `launchctl bootout` (modern command)
3. **Updated `status.sh`** - Better status reporting with resource usage
4. **Updated `restart.sh`** - Cleaner restart process
5. **Fixed `com.trading.bot.plist`** - Updated configuration

## 🚀 How to Use

### Start the Service

```bash
./start.sh
```

Output:
```
✓ Trading bot service started
  View logs: tail -f logs/bot.log
  Dashboard: http://localhost:8000
```

### Stop the Service

```bash
./stop.sh
```

### Check Status

```bash
./status.sh
```

Shows:
- Service status (RUNNING/STOPPED)
- Process ID
- CPU and Memory usage
- Recent logs (last 20 lines)

### Restart the Service

```bash
./restart.sh
```

## 🔧 Troubleshooting

### "Service is already running"

If you see this error, the service is already loaded. Use:

```bash
./restart.sh
```

Or stop and start manually:

```bash
./stop.sh
./start.sh
```

### Port 8000 Already in Use

Check for existing Python processes:

```bash
lsof -i :8000
```

Kill the process if needed:

```bash
kill <PID>
```

### Service Won't Start

1. **Check the plist file**:
   ```bash
   plutil -lint ~/Library/LaunchAgents/com.trading.bot.plist
   ```

2. **Test in foreground first**:
   ```bash
   ./run.sh
   ```
   This runs the bot directly without the LaunchAgent to verify it works.

3. **Check logs**:
   ```bash
   tail -f logs/bot_error.log
   ```

### View Service Details

```bash
launchctl print gui/$(id -u)/com.trading.bot
```

## 📝 Technical Details

### Old vs New Commands

| Old (Deprecated) | New (Modern) | Purpose |
|-----------------|--------------|---------|
| `launchctl load` | `launchctl bootstrap` | Start/load service |
| `launchctl unload` | `launchctl bootout` | Stop/unload service |
| `launchctl list | grep` | `launchctl print` | Check service status |

### Service Configuration

Location: `~/Library/LaunchAgents/com.trading.bot.plist`

Key settings:
- **RunAtLoad**: `false` - Don't auto-start when plist is loaded
- **KeepAlive**: Restart on unexpected exit
- **ThrottleInterval**: Wait 10 seconds between restart attempts
- **StandardOutPath**: `logs/bot.log`
- **StandardErrorPath**: `logs/bot_error.log`

## 🎯 Quick Reference

```bash
# Start service
./start.sh

# Check if running
./status.sh

# View live logs
tail -f logs/bot.log

# Stop service
./stop.sh

# Restart service
./restart.sh

# Test in foreground (for debugging)
./run.sh
```

## ✨ Benefits of Fixed Scripts

1. **Compatible** with macOS 10.11+
2. **Better error handling** - Clear success/failure messages
3. **Status reporting** - Shows CPU, memory, PID
4. **No duplicate starts** - Detects if already running
5. **Proper cleanup** - Ensures clean stop/start cycles

## 🔄 For Production Deployment

After these fixes, the service will:
- ✅ Start reliably with `./start.sh`
- ✅ Stop cleanly with `./stop.sh`
- ✅ Restart on crashes (KeepAlive)
- ✅ Write logs to `logs/bot.log` and `logs/bot_error.log`
- ✅ Run in background as daemon

The service is now ready for production use on macOS!
