"""
Test ONLY POST request with signature using YOLO bot code
"""
import requests
import hmac
import hashlib
import json
import time

# YOLO bot keys
API_KEY = "rRsm08OPN027nk5hgF"
API_SECRET = "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"

def generate_signature(timestamp, query_string="", body_str=""):
    """Generate signature EXACT like YOLO bot"""
    param = timestamp + API_KEY + RECV_WINDOW + query_string + body_str
    return hmac.new(
        API_SECRET.encode('utf-8'),
        param.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_headers(timestamp, signature):
    """Get headers EXACT like YOLO bot"""
    return {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW
    }

print("=" * 60)
print("TESTING POST REQUEST WITH SIGNATURE")
print("=" * 60)

# Prepare order
timestamp = str(int(time.time() * 1000))
body = {
    "category": "linear",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "orderType": "Market",
    "qty": "0.001"
}

# Convert body to JSON string for signature
body_str = json.dumps(body, separators=(",", ":"))
print(f"Body string: {body_str}")

# Generate signature
signature = generate_signature(timestamp, "", body_str)
print(f"Signature: {signature[:20]}...")

# Get headers
headers = get_headers(timestamp, signature)

# Make request
url = f"{BASE_URL}/v5/order/create"
print(f"URL: {url}")
print(f"Headers: {headers}")

try:
    response = requests.post(url, headers=headers, data=body_str, timeout=30)
    print(f"\nStatus: {response.status_code}")
    print(f"Response: {response.text}")
    
    data = response.json()
    if data.get("retCode") == 0:
        print("\n✓ SUCCESS - Order placed!")
    else:
        print(f"\n✗ FAILED - Error {data.get('retCode')}: {data.get('retMsg')}")
        
except Exception as e:
    print(f"\n✗ EXCEPTION: {e}")
