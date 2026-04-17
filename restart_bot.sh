#!/bin/bash
# Restart trading bot script

cd ~/-trading-bot

echo "=== Stopping old bot ==="
pkill -f main_new.py
sleep 3

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Starting new bot ==="
source venv/bin/activate
nohup python main_new.py > /dev/null 2>&1 &
sleep 2

echo "=== Bot restarted! ==="
NEW_PID=$(pgrep -f main_new.py | head -1)
echo "New PID: $NEW_PID"

# Show latest log file
LATEST_LOG=$(ls -t bot_*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    echo "Log file: $LATEST_LOG"
    echo "--- Last 5 lines ---"
    tail -n 5 "$LATEST_LOG"
else
    echo "Log file will be created as: bot_YYYYMMDD_HHMMSS.log"
fi
