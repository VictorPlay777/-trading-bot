#!/usr/bin/env python3
"""Test DOGEUSDT with string qty"""
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

# Direct API call with string qty
api_key = config.BYBIT_API_KEY or "rRsm08OPN027nk5hgF"
api_secret = config.BYBIT_API_SECRET or "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
base_url = "https://api-demo.bybit.com"

params = {
    "category": "linear",
    "symbol": "DOGEUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": "100"  # String instead of int
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

print(f"Request body: {body_str}")
print(f"Sending order...")

response = requests.post(url, headers=headers, data=body_str, timeout=30)
result = response.json()
print(f"Response: {result}")
