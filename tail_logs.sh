#!/bin/bash
# Follow logs in real-time
cd ~/-trading-bot || exit 1

# Find latest log in root directory
LATEST_LOG=$(ls -t bot_*.log 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    echo "Following: $LATEST_LOG"
    echo "Press Ctrl+C to stop"
    tail -f "$LATEST_LOG"
else
    echo "No bot_*.log files found in ~/-trading-bot/"
    echo "Current directory contents:"
    ls -la *.log 2>/dev/null || echo "No .log files"
fi
