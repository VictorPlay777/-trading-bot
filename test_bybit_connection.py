"""
Test Bybit Testnet API Connection
Tests ONLY connection to testnet with API keys
"""
import requests
import hmac
import hashlib
import time
import json
from urllib.parse import urlencode

# Testnet configuration
BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"

# Get API keys from environment or use provided ones
import os
API_KEY = os.getenv("BYBIT_API_KEY", "VnZUZfAbKNzqRbk6gX")
API_SECRET = os.getenv("BYBIT_API_SECRET", "14rtDoRPimG0Z1lkSYg6RVR5vtQbY26Tkg9o")

def generate_signature(timestamp, params_str=""):
    """Generate HMAC SHA256 signature for Bybit API"""
    param_str = timestamp + API_KEY + RECV_WINDOW + params_str
    return hmac.new(
        API_SECRET.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_headers(timestamp, signature):
    """Get request headers"""
    return {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "Content-Type": "application/json"
    }

def test_public_endpoint():
    """Test public endpoint (no auth required)"""
    print("=" * 60)
    print("TEST 1: Public Endpoint (GET /v5/market/time)")
    print("=" * 60)
    
    try:
        url = f"{BASE_URL}/v5/market/time"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("retCode") == 0:
            print(f"✓ SUCCESS - Server time: {data.get('result', {}).get('timeSecond')}")
            return True
        else:
            print(f"✗ FAILED - Error: {data.get('retMsg')}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Exception: {e}")
        return False

def test_private_endpoint():
    """Test private endpoint (auth required)"""
    print("\n" + "=" * 60)
    print("TEST 2: Private Endpoint (GET /v5/account/wallet-balance)")
    print("=" * 60)
    
    try:
        timestamp = str(int(time.time() * 1000))
        params = "accountType=UNIFIED"
        signature = generate_signature(timestamp, params)
        headers = get_headers(timestamp, signature)
        
        url = f"{BASE_URL}/v5/account/wallet-balance?{params}"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data.get("retCode") == 0:
            print(f"✓ SUCCESS - API keys are valid!")
            result = data.get('result', {})
            print(f"  Account Type: {result.get('accountType')}")
            balances = result.get('list', [])
            if balances:
                for bal in balances[:2]:  # Show first 2 balances
                    coin = bal.get('coin', 'N/A')
                    equity = bal.get('equity', '0')
                    print(f"  {coin}: {equity}")
            return True
        else:
            print(f"✗ FAILED - Error Code: {data.get('retCode')}")
            print(f"  Message: {data.get('retMsg')}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Exception: {e}")
        return False

def test_order_endpoint_simulation():
    """Test order endpoint (simulate, don't place real order)"""
    print("\n" + "=" * 60)
    print("TEST 3: Order Endpoint Simulation (GET /v5/order/realtime)")
    print("=" * 60)
    
    try:
        timestamp = str(int(time.time() * 1000))
        params = "category=linear&symbol=BTCUSDT"
        signature = generate_signature(timestamp, params)
        headers = get_headers(timestamp, signature)
        
        url = f"{BASE_URL}/v5/order/realtime?{params}"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data.get("retCode") == 0:
            print(f"✓ SUCCESS - Can access order data")
            orders = data.get('result', {}).get('list', [])
            print(f"  Open orders: {len(orders)}")
            return True
        else:
            print(f"✗ FAILED - Error Code: {data.get('retCode')}")
            print(f"  Message: {data.get('retMsg')}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Exception: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("BYBIT TESTNET API CONNECTION TEST")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:10]}...")
    print(f"API Secret: {API_SECRET[:10]}...")
    
    results = []
    
    # Test 1: Public endpoint
    results.append(("Public Endpoint", test_public_endpoint()))
    
    # Test 2: Private endpoint
    results.append(("Private Endpoint (Wallet)", test_private_endpoint()))
    
    # Test 3: Order endpoint
    results.append(("Order Endpoint", test_order_endpoint_simulation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Ready for live trading on testnet.")
    elif passed > 0:
        print("\n⚠ Some tests failed. Check API keys and permissions.")
    else:
        print("\n✗ All tests failed. Cannot connect to testnet.")

if __name__ == "__main__":
    main()
