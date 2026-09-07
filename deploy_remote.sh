#!/usr/bin/env bash
set -e

DEPLOY_DIR="/home/user1/trading-bot"
cd "$DEPLOY_DIR"

# Extract new sources over the live directory, preserving runtime data.
tar -xzf /tmp/deploy.tar.gz \
  --exclude='venv' \
  --exclude='.venv*' \
  --exclude='logs' \
  --exclude='.env' \
  --exclude='*.log' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.bundle'

. venv/bin/activate
pip install -q -r requirements.txt

# Stop previous bot/supervisor if running.
pkill -f run_selective_ml_forever || true
pkill -f selective_ml_bot.py || true
sleep 2

# Start the v7 selective ML bot with the auto-restart supervisor.
chmod +x run_selective_ml_forever.sh
nohup bash run_selective_ml_forever.sh >> selective_ml_supervisor.log 2>&1 &
sleep 3

echo "Deployment complete!"
ps aux | grep -E "selective_ml_bot|run_selective_ml_forever" | grep -v grep || true
tail -n 20 selective_ml_supervisor.log || true
