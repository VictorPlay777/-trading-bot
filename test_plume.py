#!/usr/bin/env python3
"""Test PLUMEUSDT order"""
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

# PLUMEUSDT has qtyStep=1 (from previous logs), so no decimals
qty = Decimal('4070004')
print(f"Testing PLUMEUSDT with qty: {qty}")

try:
    result = ex.market_buy_symbol('PLUMEUSDT', qty)
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")
