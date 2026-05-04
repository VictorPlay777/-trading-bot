#!/bin/bash
set -e

# Usage:
#   cd ~/-trading-bot/ml_bot
#   bash restart_selective_bot.sh
#
# Script:
# - restarts selective_ml_bot.py
# - writes logs to selective_ml_bot.log
# - streams logs to current terminal continuously

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BOT_DIR"

if [ ! -f "venv/bin/activate" ]; then
  echo "ERROR: venv not found at $BOT_DIR/venv"
  exit 1
fi

source venv/bin/activate

echo "=== Stopping old selective bot ==="
pkill -f "python3 selective_ml_bot.py" 2>/dev/null || true
sleep 2

echo "=== Starting selective bot ==="
nohup python3 selective_ml_bot.py --config config_scanner.yaml > selective_ml_bot.log 2>&1 < /dev/null &
sleep 2

echo "=== Process ==="
pgrep -af "selective_ml_bot.py" || true

echo "=== Live logs (Ctrl+C to stop viewing) ==="
tail -n 120 -f selective_ml_bot.log

