"""
Debug Bybit Testnet API Connection
"""
import requests
import hmac
import hashlib
import time

BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"

API_KEY = "VnZUZfAbKNzqRbk6gX"
API_SECRET = "14rtDoRPimG0Z1lkSYg6RVR5vtQbY26Tkg9o"

def generate_signature(timestamp, params_str=""):
    param_str = timestamp + API_KEY + RECV_WINDOW + params_str
    return hmac.new(
        API_SECRET.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def test_wallet():
    print("=" * 60)
    print("Testing /v5/account/wallet-balance")
    print("=" * 60)
    
    timestamp = str(int(time.time() * 1000))
    params = "accountType=UNIFIED"
    signature = generate_signature(timestamp, params)
    
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
    }
    
    url = f"{BASE_URL}/v5/account/wallet-balance?{params}"
    
    print(f"URL: {url}")
    print(f"Headers: {headers}")
    print(f"Timestamp: {timestamp}")
    print(f"Signature: {signature[:20]}...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Response length: {len(response.text)}")
        print(f"\nRaw response (first 500 chars):")
        print(response.text[:500])
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"\nParsed JSON:")
            print(f"  retCode: {data.get('retCode')}")
            print(f"  retMsg: {data.get('retMsg')}")
        except:
            print("\nCould not parse JSON")
            
    except Exception as e:
        print(f"Exception: {e}")

def test_positions():
    print("\n" + "=" * 60)
    print("Testing /v5/position/list")
    print("=" * 60)
    
    timestamp = str(int(time.time() * 1000))
    params = "category=linear&symbol=BTCUSDT"
    signature = generate_signature(timestamp, params)
    
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
    }
    
    url = f"{BASE_URL}/v5/position/list?{params}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:300]}")
    except Exception as e:
        print(f"Exception: {e}")

def test_klines():
    print("\n" + "=" * 60)
    print("Testing /v5/market/kline (public)")
    print("=" * 60)
    
    params = "category=linear&symbol=BTCUSDT&interval=15&limit=10"
    url = f"{BASE_URL}/v5/market/kline?{params}"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        data = response.json()
        if data.get("retCode") == 0:
            print(f"✓ SUCCESS - Got {len(data.get('result', {}).get('list', []))} candles")
        else:
            print(f"✗ Error: {data.get('retMsg')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_wallet()
    test_positions()
    test_klines()
