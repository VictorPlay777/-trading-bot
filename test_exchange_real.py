#!/usr/bin/env python3
"""Test real Exchange class"""
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

# Test qty
qty = Decimal('4070004')
print(f"Test qty: {qty} (type: {type(qty)})")
print(f"str(qty): {str(qty)}")

# Manually test what market_buy_symbol does
print("\n=== Testing market_buy_symbol internals ===")
qty_str = str(qty)
print(f"qty_str: {qty_str}")

params = {
    "category": ex.category,
    "symbol": "PLUMEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": qty_str
}
print(f"params: {params}")
print(f"params['qty'] type: {type(params['qty'])}")

# Test json.dumps
import json
from trader.exchange_demo import DecimalEncoder

body_str = json.dumps(params, separators=(",", ":"), cls=DecimalEncoder)
print(f"\nJSON body: {body_str}")

# Check if DecimalEncoder is actually used
print(f"\n=== Checking DecimalEncoder ===")
test_decimal = Decimal('4070004')
encoded = DecimalEncoder().default(test_decimal)
print(f"DecimalEncoder().default(Decimal('4070004')) = {encoded} (type: {type(encoded)})")

# Try actual API call (will fail but shows the flow)
print("\n=== Trying actual API call ===")
try:
    result = ex.market_buy_symbol('PLUMEUSDT', qty)
    print(f"API result: {result}")
except Exception as e:
    print(f"API error: {e}")
    import traceback
    traceback.print_exc()
