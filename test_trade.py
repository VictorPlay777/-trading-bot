"""
Test actual trade on demo account
Buy and sell BTCUSDT to verify trading works
"""
import sys
sys.path.insert(0, '.')

from trader.exchange import Exchange
import config
import time

# Test config
cfg = {
    'symbol': 'BTCUSDT',
    'timeframe': '15',
    'ccxt': {}
}

print("=" * 60)
print("TESTING ACTUAL TRADE ON DEMO ACCOUNT")
print("=" * 60)
print(f"API Key: {config.BYBIT_API_KEY[:15]}...")
print(f"Mode: {config.MODE}")

try:
    ex = Exchange(cfg)
    print("\n✓ Exchange created")
    
    # Get current price
    print("\n[1] Getting current price...")
    ticker = ex.fetch_ticker()
    price = float(ticker.get('lastPrice', 0))
    print(f"✓ Current price: ${price}")
    
    # Calculate small quantity (0.001 BTC ~ $77)
    qty = 0.001
    print(f"\n[2] Placing MARKET BUY order for {qty} BTC...")
    buy_result = ex.market_buy(qty)
    print(f"✓ BUY ORDER PLACED")
    print(f"  Result: {buy_result}")
    
    # Wait 2 seconds
    print("\n[3] Waiting 2 seconds...")
    time.sleep(2)
    
    # Sell back
    print(f"\n[4] Placing MARKET SELL order for {qty} BTC...")
    sell_result = ex.market_sell(qty)
    print(f"✓ SELL ORDER PLACED")
    print(f"  Result: {sell_result}")
    
    # Check balance
    print("\n[5] Checking final balance...")
    balance = ex.get_wallet_balance()
    print(f"✓ Balance retrieved")
    
    print("\n" + "=" * 60)
    print("TRADE TEST COMPLETE!")
    print("=" * 60)
    print("✓ Trading works on demo account!")
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
