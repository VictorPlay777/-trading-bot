"""
Test the new exchange.py module
"""
import sys
sys.path.insert(0, '.')

from trader.exchange import Exchange
import config

# Test config
cfg = {
    'symbol': 'BTCUSDT',
    'timeframe': '15',
    'ccxt': {}
}

print("=" * 60)
print("TESTING NEW EXCHANGE MODULE")
print("=" * 60)
print(f"API Key: {config.BYBIT_API_KEY[:15]}...")
print(f"API Secret: {config.BYBIT_API_SECRET[:15]}...")
print(f"Mode: {config.MODE}")

try:
    ex = Exchange(cfg)
    print("\n✓ Exchange created successfully")
    
    # Test 1: Fetch OHLCV (public)
    print("\n[1] Testing fetch_ohlcv()...")
    ohlcv = ex.fetch_ohlcv(limit=10)
    print(f"✓ Got {len(ohlcv)} candles")
    if ohlcv:
        print(f"  Latest candle: {ohlcv[0]}")
    
    # Test 2: Fetch ticker (public)
    print("\n[2] Testing fetch_ticker()...")
    ticker = ex.fetch_ticker()
    print(f"✓ Ticker retrieved")
    print(f"  Last price: {ticker.get('lastPrice', 'N/A')}")
    
    # Test 3: Get wallet balance (private)
    print("\n[3] Testing get_wallet_balance()...")
    balance = ex.get_wallet_balance()
    print(f"✓ Balance retrieved")
    print(f"  Result: {balance}")
    
    # Test 4: Get positions (private)
    print("\n[4] Testing get_positions()...")
    positions = ex.get_positions(symbol="BTCUSDT")
    print(f"✓ Positions retrieved")
    print(f"  Result: {positions}")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
