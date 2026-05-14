#!/bin/bash
cd /home/svy1990/-trading-bot/ml_bot
# Kill any existing instances
pkill -9 -f 'selective_ml_bot|run_selective_ml_forever' 2>/dev/null
sleep 3
# Start with proper log redirect
nohup ./run_selective_ml_forever.sh >> selective_ml_supervisor.log 2>&1 < /dev/null &
disown
sleep 2
echo "Started bot, PIDs:"
pgrep -fa 'selective_ml|run_selective'
