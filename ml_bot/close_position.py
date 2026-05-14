#!/usr/bin/env python3
"""Close current position on Bybit demo account"""
import requests
import hmac
import hashlib
import time
import json

API_KEY = "rRsm08OPN027nk5hgF"
API_SECRET = "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
BASE_URL = "https://api-demo.bybit.com"
SYMBOL = "BTCUSDT"

def get_signature(timestamp, params_str="", body_str=""):
    sign_str = timestamp + API_KEY + "5000" + params_str + body_str
    return hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

# Get current position
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

response = requests.get(f"{BASE_URL}/v5/position/list?{params}", headers=headers)
data = response.json()
print(f"Position data: {data}")

if data.get('retCode') == 0:
    positions = data.get('result', {}).get('list', [])
    for pos in positions:
        if pos.get('symbol') == SYMBOL and float(pos.get('size', 0)) > 0:
            size = float(pos.get('size'))
            side = pos.get('side')
            print(f"Found position: {side} size={size}")
            
            # Close position with market order
            close_side = "Sell" if side == "Buy" else "Buy"
            body = {
                "category": "linear",
                "symbol": SYMBOL,
                "side": close_side,
                "orderType": "Market",
                "qty": str(size),
                "reduceOnly": True
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
            
            response = requests.post(f"{BASE_URL}/v5/order/create", headers=headers, data=body_str)
            data = response.json()
            print(f"Close order response: {data}")
            
            if data.get('retCode') == 0:
                print(f"✅ Position closed successfully")
            else:
                print(f"❌ Error closing position: {data.get('retMsg')}")
            break
else:
    print(f"No open position found")
