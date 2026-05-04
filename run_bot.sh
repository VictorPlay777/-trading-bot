#!/bin/bash
source venv/bin/activate
pkill -f scanner.py
nohup python3 scanner.py --config config.yaml > ml_live_scanner.log 2>&1 &
