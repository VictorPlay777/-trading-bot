#!/usr/bin/env bash
# V10 research bot restart script.
# Kills v10 supervisor + bot, clears lockfile, starts one supervisor.
# Use only AFTER stopping v9.1 (kill_selective_ml.sh) and manually closing all positions.
#
# Run: bash restart_v10.sh

set -u

cd ~/-trading-bot

echo "=== [1/5] Killing v10 supervisor and bot ==="
pkill -9 -f run_v10_forever.sh 2>/dev/null || true
pkill -9 -f "selective_ml_bot_v10.py" 2>/dev/null || true
sleep 3

echo "=== [2/5] Verifying everything is dead ==="
REMAINING=$(ps -eo pid,cmd | grep -E "selective_ml_bot_v10\.py|run_v10_forever\.sh" | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "WARNING: $REMAINING processes still alive, killing again..."
    ps -eo pid,cmd | grep -E "selective_ml_bot_v10\.py|run_v10_forever\.sh" | grep -v grep
    pkill -9 -f run_v10_forever.sh 2>/dev/null || true
    pkill -9 -f "selective_ml_bot_v10.py" 2>/dev/null || true
    sleep 3
fi

echo "=== [3/5] Removing lockfile ==="
rm -f v10_supervisor.lock

echo "=== [4/5] Starting one supervisor ==="
mkdir -p logs/v10
nohup bash run_v10_forever.sh >> v10_supervisor.log 2>&1 &
sleep 5

echo "=== [5/5] Running processes ==="
ps -eo pid,ppid,lstart,cmd | grep -E "selective_ml_bot_v10|run_v10_forever" | grep -v grep

PROC_COUNT=$(ps -eo pid,cmd | grep -E "selective_ml_bot_v10\.py|run_v10_forever\.sh" | grep -v grep | wc -l)
echo ""
if [ "$PROC_COUNT" -eq 2 ]; then
    echo "[OK] Exactly 2 processes running (1 v10 supervisor + 1 v10 bot)"
else
    echo "[ERROR] Expected 2 processes, got $PROC_COUNT"
fi

echo ""
echo "Logs:"
echo "  tail -f logs/ml.log"
echo "  tail -f logs/v10/signals_all.jsonl | head -20"
echo "  ls -la logs/v10/"
