#!/usr/bin/env python3
"""Test qty with decimal places"""
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

# Get symbol info for PLUMEUSDT
info = ex.get_symbol_info('PLUMEUSDT')
if info:
    lot_filter = info.get("lotSizeFilter", {})
    print(f"PLUMEUSDT lotSizeFilter:")
    for k, v in lot_filter.items():
        print(f"  {k}: {v}")
else:
    print("Could not get symbol info")

# Test different qty formats
test_qtys = [
    Decimal('4070004'),
    Decimal('4070004.0'),
    Decimal('4070004.00'),
]

print("\n=== Testing different qty formats ===")
for qty in test_qtys:
    print(f"\nTesting qty: {qty}")
    try:
        result = ex.market_buy_symbol('PLUMEUSDT', qty)
        print(f"  SUCCESS: {result}")
    except Exception as e:
        error = str(e)
        print(f"  ERROR: {error[:100]}")
