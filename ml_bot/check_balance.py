#!/usr/bin/env python3
"""Check balance on Bybit demo account"""
import requests
import hmac
import hashlib
import time
import json

API_KEY = "rRsm08OPN027nk5hgF"
API_SECRET = "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
BASE_URL = "https://api-demo.bybit.com"

def get_signature(timestamp, params_str="", body_str=""):
    sign_str = timestamp + "rRsm08OPN027nk5hgF" + "5000" + params_str + body_str
    return hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

timestamp = str(int(time.time() * 1000))
params = "category=UNIFIED&accountType=UNIFIED"
signature = get_signature(timestamp, params)

headers = {
    "X-BAPI-API-KEY": API_KEY,
    "X-BAPI-SIGN": signature,
    "X-BAPI-TIMESTAMP": timestamp,
    "X-BAPI-RECV-WINDOW": "5000",
    "Content-Type": "application/json"
}

response = requests.get(f"{BASE_URL}/v5/account/wallet-balance?{params}", headers=headers)
data = response.json()
print(f"Full response: {data}")
if data.get('retCode') == 0:
    balance = data.get('result', {}).get('list', [])
    if balance:
        print(f"Balance: {balance[0]}")
else:
    print(f"Error: {data.get('retMsg')}")
