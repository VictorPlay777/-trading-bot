#!/bin/bash
# Follow logs in real-time
cd ~/-trading-bot || exit 1

LATEST_LOG=$(ls -t logs/bot_*.log 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    echo "Following: $LATEST_LOG"
    echo "Press Ctrl+C to stop"
    tail -f "$LATEST_LOG"
else
    echo "No logs found"
fi
