#!/usr/bin/env python3
"""Test POST request details"""
import requests
import json
from decimal import Decimal

# Test data
body_str = '{"category":"linear","symbol":"PLUMEUSDT","side":"Buy","orderType":"Market","qty":"4070004"}'

# Check if encoding matters
print(f"body_str type: {type(body_str)}")
print(f"body_str: {body_str}")

# Check if bytes conversion changes anything
body_bytes = body_str.encode('utf-8')
print(f"\nbody_bytes: {body_bytes}")

# Check if using json param instead of data
params_dict = {
    "category": "linear",
    "symbol": "PLUMEUSDT", 
    "side": "Buy",
    "orderType": "Market",
    "qty": "4070004"  # String
}

# If we use json= param, requests will serialize
# Let's see what happens
print(f"\nUsing json= param would serialize to: {json.dumps(params_dict, separators=(',', ':'))}")

# Check if there's any issue with the JSON string itself
# Maybe the issue is that Bybit expects qty as NUMBER not STRING?

# Test what happens if we pass qty as number
params_dict_num = {
    "category": "linear",
    "symbol": "PLUMEUSDT",
    "side": "Buy", 
    "orderType": "Market",
    "qty": 4070004  # Number, not string
}
print(f"\nWith number qty: {json.dumps(params_dict_num, separators=(',', ':'))}")

print("\n=== POSSIBLE ISSUES ===")
print("1. Bybit may expect qty as NUMBER, not STRING")
print("2. When Bybit parses string '4070004', it may convert to float first")
print("3. Float 4070004 becomes 407000400000000 due to precision loss")
print("4. Or Bybit's parser has a bug with large string numbers")

# Check float conversion
print(f"\n=== Float test ===")
print(f"float(4070004) = {float(4070004)}")
print(f"int(float(4070004)) = {int(float(4070004))}")

# Check if 4070004 * 1e8 = 407000400000000
print(f"\n4070004 * 100000000 = {4070004 * 100000000}")
print(f"This matches Bybit's order_qty!")
