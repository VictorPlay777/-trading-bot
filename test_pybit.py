"""
Test Bybit Testnet API using official pybit SDK
"""
from pybit.unified_trading import HTTP
import os

# API Keys
API_KEY = os.getenv("BYBIT_API_KEY", "VnZUZfAbKNzqRbk6gX")
API_SECRET = os.getenv("BYBIT_API_SECRET", "14rtDoRPimG0Z1lkSYg6RVR5vtQbY26Tkg9o")

def main():
    print("=" * 60)
    print("BYBIT TESTNET API - PYBIT SDK TEST")
    print("=" * 60)
    print(f"API Key: {API_KEY[:15]}...")
    
    try:
        # Create session with testnet=True
        print("\n[1] Creating HTTP session with testnet=True...")
        session = HTTP(
            testnet=True,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        print("✓ Session created successfully")
        
        # Test 1: Get server time (public)
        print("\n[2] Testing get_server_time()...")
        try:
            result = session.get_server_time()
            print(f"✓ SUCCESS - Server time: {result}")
        except Exception as e:
            print(f"✗ FAILED: {e}")
        
        # Test 2: Get wallet balance (private)
        print("\n[3] Testing get_wallet_balance()...")
        try:
            result = session.get_wallet_balance(accountType="UNIFIED")
            print(f"✓ SUCCESS - Wallet balance retrieved")
            print(f"  Result: {result}")
        except Exception as e:
            print(f"✗ FAILED: {e}")
        
        # Test 3: Get positions (private)
        print("\n[4] Testing get_positions()...")
        try:
            result = session.get_positions(
                category="linear",
                symbol="BTCUSDT"
            )
            print(f"✓ SUCCESS - Positions retrieved")
            print(f"  Result: {result}")
        except Exception as e:
            print(f"✗ FAILED: {e}")
        
        # Test 4: Get klines (public)
        print("\n[5] Testing get_kline()...")
        try:
            result = session.get_kline(
                category="linear",
                symbol="BTCUSDT",
                interval="15",
                limit=10
            )
            print(f"✓ SUCCESS - Got {len(result.get('list', []))} candles")
        except Exception as e:
            print(f"✗ FAILED: {e}")
            
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
