#!/usr/bin/env python3
"""Test DOGEUSDT with integer qty (like PLUME)"""
import sys
sys.path.insert(0, '/home/svy1990/-trading-bot/ml_bot')
import os
os.chdir('/home/svy1990/-trading-bot/ml_bot')

from decimal import Decimal
from trader.exchange_demo import Exchange
import yaml

# Load config
with open('config_scanner.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Create exchange
ex = Exchange(cfg)

# DOGE at ~$0.17, qtyStep is usually 1
# Test with 100 DOGE = ~$17
qty = Decimal('100')
print(f"Testing DOGEUSDT with qty: {qty}")

try:
    result = ex.market_buy_symbol('DOGEUSDT', qty)
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")
