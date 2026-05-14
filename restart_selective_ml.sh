#!/usr/bin/env bash
# Правильный перезапуск Selective ML bot.
# Убивает И supervisor И бота, удаляет lockfile, запускает один supervisor.
# Запуск: bash restart_selective_ml.sh

set -u

cd ~/-trading-bot

echo "=== [1/5] Killing all supervisors and bots ==="
pkill -9 -f run_selective_ml_forever.sh 2>/dev/null || true
pkill -9 -f "selective_ml_bot.py" 2>/dev/null || true
sleep 3

echo "=== [2/5] Verifying everything is dead ==="
REMAINING=$(ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "WARNING: $REMAINING processes still alive, killing again..."
    ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep
    pkill -9 -f run_selective_ml_forever.sh 2>/dev/null || true
    pkill -9 -f "selective_ml_bot.py" 2>/dev/null || true
    sleep 3
fi

echo "=== [3/5] Removing lockfile ==="
rm -f selective_ml_supervisor.lock

echo "=== [4/5] Starting one supervisor ==="
nohup bash run_selective_ml_forever.sh >> selective_ml_supervisor.log 2>&1 &
sleep 5

echo "=== [5/5] Running processes ==="
ps -eo pid,ppid,lstart,cmd | grep -E "selective|forever" | grep -v grep

PROC_COUNT=$(ps -eo pid,cmd | grep -E "selective_ml_bot\.py|run_selective_ml_forever\.sh" | grep -v grep | wc -l)
echo ""
if [ "$PROC_COUNT" -eq 2 ]; then
    echo "[OK] Exactly 2 processes running (1 supervisor + 1 bot)"
else
    echo "[ERROR] Expected 2 processes, got $PROC_COUNT"
fi
