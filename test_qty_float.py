#!/usr/bin/env python3
"""Test qty as float"""
import sys
sys.path.insert(0, '/home/svy1990/-trading-bot/ml_bot')
import os
os.chdir('/home/svy1990/-trading-bot/ml_bot')

from decimal import Decimal
from trader.exchange_demo import Exchange
import yaml
import json

# Load config
with open('config_scanner.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Create exchange
ex = Exchange(cfg)

# Test with float
qty_float = float(Decimal('4070004'))
print(f"Testing qty as float: {qty_float}")

# Direct test
params = {
    "category": "linear",
    "symbol": "PLUMEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": qty_float
}
print(f"Params: {params}")
print(f"JSON: {json.dumps(params, separators=(',', ':'))}")

try:
    result = ex.market_buy_symbol('PLUMEUSDT', qty_float)
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")
