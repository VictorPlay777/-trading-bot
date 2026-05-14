#!/usr/bin/env python3
"""Simple test to trace qty multiplication bug"""
import sys
sys.path.insert(0, '/home/svy1990/-trading-bot/ml_bot')

from decimal import Decimal

# Test str() conversion
qty = Decimal('4070004')
print(f"Original qty: {qty}")
print(f"str(qty): {str(qty)}")
print(f"repr(qty): {repr(qty)}")

# Test what market_buy_symbol receives
qty_str = str(qty)
print(f"\nIn market_buy_symbol:")
print(f"  qty_input: {qty}")
print(f"  qty_str: {qty_str}")

# Test params
params = {
    "category": "linear",
    "symbol": "PLUMEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": qty_str
}
print(f"\nParams: {params}")

# Test JSON dumps
import json
body_str = json.dumps(params, separators=(",", ":"))
print(f"\nJSON body: {body_str}")

# Check if there's any int conversion
print(f"\nChecking int() conversion:")
try:
    int_qty = int(qty)
    print(f"  int(qty) = {int_qty}")
except:
    print(f"  int(qty) failed")

# Check float conversion  
print(f"\nChecking float() conversion:")
try:
    float_qty = float(qty)
    print(f"  float(qty) = {float_qty}")
except:
    print(f"  float(qty) failed")
