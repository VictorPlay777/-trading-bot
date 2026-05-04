#!/usr/bin/env python3
"""Set leverage for BTCUSDT on Bybit demo account"""
import requests
import hmac
import hashlib
import time
import json

API_KEY = "rRsm08OPN027nk5hgF"
API_SECRET = "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
BASE_URL = "https://api-demo.bybit.com"
SYMBOL = "BTCUSDT"
LEVERAGE = 1  # Set to 1x leverage (no leverage)

def get_signature(timestamp, params_str="", body_str=""):
    sign_str = timestamp + API_KEY + "5000" + params_str + body_str
    return hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

# Set leverage
body = {
    "category": "linear",
    "symbol": SYMBOL,
    "buyLeverage": str(LEVERAGE),
    "sellLeverage": str(LEVERAGE)
}
body_str = json.dumps(body, separators=(',', ':'))

timestamp = str(int(time.time() * 1000))
signature = get_signature(timestamp, "", body_str)

headers = {
    "X-BAPI-API-KEY": API_KEY,
    "X-BAPI-SIGN": signature,
    "X-BAPI-TIMESTAMP": timestamp,
    "X-BAPI-RECV-WINDOW": "5000",
    "Content-Type": "application/json"
}

response = requests.post(f"{BASE_URL}/v5/position/set-leverage", headers=headers, data=body_str)
data = response.json()
print(f"Set leverage response: {data}")

if data.get('retCode') == 0:
    print(f"✅ Leverage set to {LEVERAGE}x for {SYMBOL}")
else:
    print(f"❌ Error: {data.get('retMsg')}")
