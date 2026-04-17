#!/bin/bash
# Show recent log entries
cd ~/-trading-bot || exit 1

# Find latest log in root directory
LATEST_LOG=$(ls -t bot_*.log 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    echo "=== $LATEST_LOG ==="
    tail -n 20 "$LATEST_LOG"
else
    echo "No bot_*.log files found in ~/-trading-bot/"
    echo "Current directory contents:"
    ls -la *.log 2>/dev/null || echo "No .log files"
fi
