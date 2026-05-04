#!/bin/bash
# Start all trading bots in background

# Kill existing bots
pkill -f "python3 run_live.py"

# Wait a moment
sleep 2

# Start 5 bots (BTC, ETH, SOL, XRP, ADA)
nohup python3 run_live.py --config config.yaml > ml_live_btc.log 2>&1 &
echo "Started BTC bot"

nohup python3 run_live.py --config config_eth.yaml > ml_live_eth.log 2>&1 &
echo "Started ETH bot"

nohup python3 run_live.py --config config_sol.yaml > ml_live_sol.log 2>&1 &
echo "Started SOL bot"

nohup python3 run_live.py --config config_xrp.yaml > ml_live_xrp.log 2>&1 &
echo "Started XRP bot"

nohup python3 run_live.py --config config_ada.yaml > ml_live_ada.log 2>&1 &
echo "Started ADA bot"

echo "All bots started. Check logs with tail -f ml_live_*.log"
