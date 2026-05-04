#!/bin/bash
# Перезапуск ML-бота (мультивалютный scanner). Рабочая копия: ~/-trading-bot

cd ~/-trading-bot || exit 1

echo "=== Stopping ML bot processes ==="
pkill -f "ml_bot.py scanner" 2>/dev/null || true
pkill -f "python3 scanner.py" 2>/dev/null || true
pkill -f "python scanner.py" 2>/dev/null || true
sleep 3

echo "=== Pulling latest code ==="
git reset --hard HEAD
git clean -fd -e venv -e symbol_stats.json -e 'bot_*.log' -e learning_history.json -e leverage_cache.json \
  -e temp_bot/storage -e temp_bot/models -e temp_bot/logs -e 'ml_live_scanner.log'
git pull origin main

echo "=== Virtual environment ==="
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating venv..."
    python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate

echo "=== Installing ML dependencies (temp_bot) ==="
pip install --quiet -r temp_bot/requirements.txt 2>/dev/null || pip install -r temp_bot/requirements.txt

echo "=== Starting ML scanner ==="
# При необходимости поменяйте --top и --size под риск/капитал
nohup python3 ml_bot.py scanner --config temp_bot/config_scanner.yaml --top 100 --size 50000 >> ml_live_scanner.log 2>&1 &
sleep 2

echo "=== ML bot started ==="
pgrep -af "ml_bot.py|scanner.py" || true
echo "Logs: tail -f ml_live_scanner.log"
