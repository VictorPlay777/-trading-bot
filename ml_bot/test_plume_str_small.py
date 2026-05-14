#!/usr/bin/env python3
"""Test PLUMEUSDT with string qty (small amount)"""
import sys
sys.path.insert(0, '/home/svy1990/-trading-bot/ml_bot')
import os
os.chdir('/home/svy1990/-trading-bot/ml_bot')

import requests
import json
import time
import hmac
import hashlib
import config

api_key = config.BYBIT_API_KEY or "rRsm08OPN027nk5hgF"
api_secret = config.BYBIT_API_SECRET or "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
base_url = "https://api-demo.bybit.com"

# Try smaller qty
params = {
    "category": "linear",
    "symbol": "PLUMEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": "1000"  # Small string qty
}

timestamp = str(int(time.time() * 1000))
recv_window = "10000"

body_str = json.dumps(params, separators=(",", ":"))
param_str = timestamp + api_key + recv_window + "" + body_str
signature = hmac.new(
    api_secret.encode('utf-8'),
    param_str.encode('utf-8'),
    hashlib.sha256
).hexdigest()

headers = {
    "X-BAPI-API-KEY": api_key,
    "X-BAPI-TIMESTAMP": timestamp,
    "X-BAPI-RECV-WINDOW": recv_window,
    "X-BAPI-SIGN": signature,
    "Content-Type": "application/json"
}

url = f"{base_url}/v5/order/create"

print(f"Testing PLUMEUSDT with qty: 1000 (string)")
print(f"Request body: {body_str}")

response = requests.post(url, headers=headers, data=body_str, timeout=30)
result = response.json()
print(f"Response: {result}")
