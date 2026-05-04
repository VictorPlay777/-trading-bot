"""
Test Bybit DEMO API using pybit SDK with custom domain
"""
from pybit.unified_trading import HTTP
import os

# API Keys from demo.bybit.com
API_KEY = os.getenv("BYBIT_API_KEY", "VnZUZfAbKNzqRbk6gX")
API_SECRET = os.getenv("BYBIT_API_SECRET", "14rtDoRPimG0Z1lkSYg6RVR5vtQbY26Tkg9o")

class DemoHTTP(HTTP):
    """Custom HTTP class that uses api-demo.bybit.com instead of api-testnet.bybit.com"""
    
    def __init__(self, api_key=None, api_secret=None, **kwargs):
        # Override the domain
        self.demo_mode = True
        super().__init__(
            testnet=False,  # Don't use testnet, we'll override URL
            api_key=api_key,
            api_secret=api_secret,
            **kwargs
        )
        # Override the URL to use demo
        self.endpoint = "https://api-demo.bybit.com"
        
    def _submit_request(self, method=None, path=None, query=None, auth=False):
        # Override to use demo endpoint
        if self.demo_mode:
            url = f"https://api-demo.bybit.com{path}"
            if query:
                if isinstance(query, dict):
                    query_str = '&'.join([f"{k}={v}" for k, v in query.items()])
                else:
                    query_str = query
                url += f"?{query_str}"
            
            import requests
            import time
            import hmac
            import hashlib
            
            recv_window = "5000"
            timestamp = str(int(time.time() * 1000))
            
            if auth:
                # Generate signature
                params_str = query_str if isinstance(query, dict) else str(query)
                param_str = timestamp + self.api_key + recv_window + params_str
                signature = hmac.new(
                    self.api_secret.encode('utf-8'),
                    param_str.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                }
            else:
                headers = {}
            
            if method == "GET":
                return requests.get(url, headers=headers, timeout=10).json()
            else:
                return requests.post(url, headers=headers, json=query, timeout=10).json()
        
        return super()._submit_request(method, path, query, auth)

def test_with_pybit():
    """Test with standard pybit (testnet)"""
    print("=" * 60)
    print("TEST 1: Standard pybit (testnet)")
    print("=" * 60)
    
    try:
        session = HTTP(
            testnet=True,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        result = session.get_wallet_balance(accountType="UNIFIED")
        print(f"✓ SUCCESS: {result}")
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_with_requests():
    """Test with direct requests to api-demo.bybit.com"""
    print("\n" + "=" * 60)
    print("TEST 2: Direct requests to api-demo.bybit.com")
    print("=" * 60)
    
    import requests
    import time
    import hmac
    import hashlib
    
    base_url = "https://api-demo.bybit.com"
    recv_window = "5000"
    timestamp = str(int(time.time() * 1000))
    
    # Prepare params
    params = {"accountType": "UNIFIED"}
    params_str = f"accountType={params['accountType']}"
    
    # Generate signature
    param_str = timestamp + API_KEY + recv_window + params_str
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    
    url = f"{base_url}/v5/account/wallet-balance?{params_str}"
    
    print(f"URL: {url}")
    print(f"Headers: {headers}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        
        data = response.json()
        if data.get("retCode") == 0:
            print(f"✓ SUCCESS: Balance retrieved")
            return True
        else:
            print(f"✗ FAILED: {data.get('retMsg')}")
            return False
    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    print("BYBIT API TEST")
    print(f"API Key: {API_KEY}")
    print(f"API Secret: {API_SECRET[:20]}...")
    
    test1 = test_with_pybit()
    test2 = test_with_requests()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"pybit testnet: {'✓ PASS' if test1 else '✗ FAIL'}")
    print(f"demo direct: {'✓ PASS' if test2 else '✗ FAIL'}")
