#!/usr/bin/env python3
"""Test actual API call with detailed logging"""
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

# Test qty
qty = Decimal('4070004')
print(f"Test qty: {qty}")

# Prepare params like market_buy_symbol does
qty_str = str(qty)
params = {
    "category": ex.category,
    "symbol": "PLUMEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": qty_str
}
print(f"\nParams: {params}")

# Simulate _request logic
import time
import hmac
import hashlib

timestamp = str(int(time.time() * 1000))
query_str = ""

# Check DecimalEncoder
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

body_str = json.dumps(params, separators=(",", ":"), cls=DecimalEncoder)
print(f"\nJSON body: {body_str}")

# Check if qty is still string in JSON
import re
qty_in_json = re.search(r'"qty":"([^"]+)"', body_str)
if qty_in_json:
    print(f"qty in JSON: {qty_in_json.group(1)}")
else:
    qty_in_json_num = re.search(r'"qty":([\d.]+)', body_str)
    if qty_in_json_num:
        print(f"WARNING: qty is NUMBER in JSON: {qty_in_json_num.group(1)}")

# Make actual request to see what happens
print("\n=== Making actual API call ===")
try:
    result = ex.market_buy_symbol('PLUMEUSDT', qty)
    print(f"Result: {result}")
except Exception as e:
    error_str = str(e)
    print(f"Error: {error_str}")
    
    # Parse the error
    if "max_qty" in error_str:
        import re
        match = re.search(r'max_qty:(\d+)', error_str)
        if match:
            print(f"\nBybit says max_qty: {match.group(1)}")
        match2 = re.search(r'order_qty:(\d+)', error_str)
        if match2:
            print(f"Bybit says order_qty: {match2.group(1)}")
            
            # Check if order_qty matches our qty
            sent_qty = str(qty)
            received_qty = match2.group(1)
            print(f"\nWe sent: {sent_qty}")
            print(f"Bybit received: {received_qty}")
            if sent_qty != received_qty:
                print(f"MISMATCH! Multiplier: {int(received_qty) / int(sent_qty)}")
