#!/bin/bash
# Show recent log entries
cd ~/-trading-bot || exit 1

LATEST_LOG=$(ls -t logs/bot_*.log 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    tail -n 20 "$LATEST_LOG"
else
    echo "No logs found"
fi
