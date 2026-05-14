#!/usr/bin/env bash
# Stops V9.1 cleanly so the user can manually close all positions, fix balance,
# and then start V10 from a clean slate.
#
# Run: bash stop_v9_for_v10.sh
#
# AFTER this:
#   1. On Bybit web: manually close ALL open positions
#   2. Verify balance, take a screenshot for the V10 baseline
#   3. Run: bash restart_v10.sh

set -u

cd ~/-trading-bot

echo "=== [1/3] Killing v9.1 supervisor and bot ==="
pkill -9 -f run_selective_ml_forever.sh 2>/dev/null || true
pkill -9 -f "selective_ml_bot.py" 2>/dev/null || true
sleep 3

echo "=== [2/3] Verifying nothing is alive ==="
REMAINING=$(ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep | grep -v "_v10" | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "WARNING: $REMAINING processes still alive:"
    ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep | grep -v "_v10"
    pkill -9 -f run_selective_ml_forever.sh 2>/dev/null || true
    pkill -9 -f "selective_ml_bot.py" 2>/dev/null || true
    sleep 3
fi
rm -f selective_ml_supervisor.lock

echo "=== [3/3] Status ==="
PROC_COUNT=$(ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep | grep -v "_v10" | wc -l)
if [ "$PROC_COUNT" -eq 0 ]; then
    echo "[OK] V9.1 stopped cleanly. Bot is NOT running."
    echo ""
    echo "Next steps:"
    echo "  1. On Bybit web UI: close all open positions manually"
    echo "  2. Note balance for V10 baseline"
    echo "  3. Run: bash restart_v10.sh"
else
    echo "[ERROR] $PROC_COUNT v9 process(es) still alive. Investigate."
fi
