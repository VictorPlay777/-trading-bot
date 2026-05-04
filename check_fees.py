#!/usr/bin/env python3
"""Check trading fees on Bybit demo account"""
import requests
import hmac
import hashlib
import time
import json

API_KEY = "rRsm08OPN027nk5hgF"
API_SECRET = "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
BASE_URL = "https://api-demo.bybit.com"

def get_signature(timestamp, params_str="", body_str=""):
    sign_str = timestamp + API_KEY + "5000" + params_str + body_str
    return hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

# Get trading fee rate
timestamp = str(int(time.time() * 1000))
params = "category=linear&symbol=BTCUSDT"
signature = get_signature(timestamp, params)

headers = {
    "X-BAPI-API-KEY": API_KEY,
    "X-BAPI-SIGN": signature,
    "X-BAPI-TIMESTAMP": timestamp,
    "X-BAPI-RECV-WINDOW": "5000",
    "Content-Type": "application/json"
}

response = requests.get(f"{BASE_URL}/v5/account/fee-rate?{params}", headers=headers)
data = response.json()
print(f"Fee rate response: {data}")

if data.get('retCode') == 0:
    result = data.get('result', {})
    print(f"\n=== Trading Fees for BTCUSDT ===")
    print(f"Maker fee: {result.get('makerFee', 'N/A')}")
    print(f"Taker fee: {result.get('takerFee', 'N/A')}")
    
    # Calculate example
    maker_fee = float(result.get('makerFee', 0))
    taker_fee = float(result.get('takerFee', 0))
    position_value = 500000  # 500K USDT position
    print(f"\n=== Example for 500K USDT position ===")
    print(f"Maker fee: {position_value * maker_fee:.2f} USDT")
    print(f"Taker fee: {position_value * taker_fee:.2f} USDT")
    print(f"Total (open+close): {(position_value * taker_fee * 2):.2f} USDT")
else:
    print(f"Error: {data.get('retMsg')}")
