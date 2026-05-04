#!/usr/bin/env python3
"""Test how many candles Bybit API returns for top volatile coins"""
import sys
sys.path.insert(0, '.')
from trader.exchange_demo import Exchange
import yaml

# Load config
cfg = yaml.safe_load(open('config.yaml', 'r', encoding='utf-8'))

# Initialize exchange
ex = Exchange(cfg)

# Test top volatile coins from your logs
test_symbols = [
    'BSBUSDT',    # #1 in volatility
    'PUMPBTCUSDT', # #2
    'TACUSDT',    # #3
    'BTCUSDT',    # Major coin for comparison
    'ETHUSDT',    # Major coin
    'FHEUSDT',    # Recently traded
]

print("=== Testing Candle Counts ===\n")

for symbol in test_symbols:
    try:
        ohlcv = ex.fetch_ohlcv_symbol(symbol, limit=600)
        print(f"{symbol:15} | {len(ohlcv):4} candles | timeframe: {ex.timeframe}")
        
        # Show first and last candle timestamps if available
        if len(ohlcv) > 0:
            first_ts = ohlcv[0][0]
            last_ts = ohlcv[-1][0]
            from datetime import datetime
            first_dt = datetime.fromtimestamp(first_ts)
            last_dt = datetime.fromtimestamp(last_ts)
            span_hours = (last_ts - first_ts) / 3600
            print(f"                 First: {first_dt} | Last: {last_dt} | Span: {span_hours:.1f}h")
            
    except Exception as e:
        print(f"{symbol:15} | ERROR: {e}")

print("\n=== Done ===")
