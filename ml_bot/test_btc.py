#!/usr/bin/env python3
"""Test with BTCUSDT which definitely exists"""
import sys
sys.path.insert(0, '/home/svy1990/-trading-bot/ml_bot')
import os
os.chdir('/home/svy1990/-trading-bot/ml_bot')

from decimal import Decimal
from trader.exchange_demo import Exchange
import yaml

# Load config
with open('config_scanner.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Create exchange
ex = Exchange(cfg)

# Test with BTC (smaller qty)
# BTC at ~$75k, qty 0.001 = $75
qty = Decimal('0.001')
print(f"Testing BTCUSDT with qty: {qty}")

try:
    result = ex.market_buy_symbol('BTCUSDT', qty)
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")

# Also test SOLUSDT
qty2 = Decimal('1')
print(f"\nTesting SOLUSDT with qty: {qty2}")
try:
    result = ex.market_buy_symbol('SOLUSDT', qty2)
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")

# Get all tickers to verify PLUMEUSDT exists
print("\n=== Checking if PLUMEUSDT exists ===")
try:
    tickers = ex.fetch_all_tickers()
    symbols = [t.get('symbol') for t in tickers]
    if 'PLUMEUSDT' in symbols:
        print("PLUMEUSDT EXISTS")
        # Find it and show details
        for t in tickers:
            if t.get('symbol') == 'PLUMEUSDT':
                print(f"  Details: {t}")
    else:
        print("PLUMEUSDT NOT FOUND in tickers")
        # Show similar symbols
        similar = [s for s in symbols if 'PLU' in s or 'UME' in s]
        if similar:
            print(f"  Similar: {similar[:5]}")
except Exception as e:
    print(f"Error fetching tickers: {e}")
