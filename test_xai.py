#!/usr/bin/env python3
"""Test xAI Grok API connection and signal generation"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xai_client import XAIClient

# Your API key
API_KEY = "xai-KefeZwOVRl1HghtRS54G6CqIx7Y29AJvjCa9mA6RKl266eecVfH4mfNVKyK19KOabHEYfdei0IxCTNpT"

def test_connection():
    """Test basic API connection"""
    print("Testing xAI API connection...")
    client = XAIClient(API_KEY)
    
    if client.test_connection():
        print("✓ API connection successful")
        return True
    else:
        print("✗ API connection failed")
        return False

def test_signal_generation():
    """Test signal generation with sample data"""
    print("\nTesting signal generation...")
    client = XAIClient(API_KEY)
    
    # Sample market data for BTCUSDT
    market_data = {
        "price": 65000.0,
        "volume": 1000000000,
        "ema_short": 64800.0,
        "ema_long": 62000.0,
        "rsi": 65.0,
        "atr": 500.0,
        "trend": "bullish"
    }
    
    signal = client.generate_trading_signal("BTCUSDT", market_data)
    
    if signal:
        print(f"✓ Signal generated:")
        print(f"  Direction: {signal.direction}")
        print(f"  Confidence: {signal.confidence:.2f}")
        print(f"  Reason: {signal.reason}")
        print(f"  Raw response:\n{signal.raw_response}")
        return True
    else:
        print("✗ Signal generation failed")
        return False

def test_multiple_symbols():
    """Test signals for multiple symbols"""
    print("\nTesting signals for multiple symbols...")
    client = XAIClient(API_KEY)
    
    symbols = [
        ("BTCUSDT", {"price": 65000.0, "volume": 1000000000, "ema_short": 64800.0, "ema_long": 62000.0, "rsi": 65.0, "atr": 500.0, "trend": "bullish"}),
        ("ETHUSDT", {"price": 3500.0, "volume": 500000000, "ema_short": 3450.0, "ema_long": 3200.0, "rsi": 55.0, "atr": 30.0, "trend": "neutral"}),
        ("SOLUSDT", {"price": 150.0, "volume": 200000000, "ema_short": 145.0, "ema_long": 140.0, "rsi": 45.0, "atr": 5.0, "trend": "bearish"}),
    ]
    
    for symbol, data in symbols:
        print(f"\n{symbol}:")
        signal = client.generate_trading_signal(symbol, data)
        if signal:
            print(f"  {signal.direction} (conf={signal.confidence:.2f}) - {signal.reason}")
        else:
            print(f"  No signal generated")

if __name__ == "__main__":
    print("=" * 60)
    print("xAI Grok API Test")
    print("=" * 60)
    
    # Test connection
    if not test_connection():
        print("\nConnection test failed. Exiting.")
        sys.exit(1)
    
    # Test signal generation
    if not test_signal_generation():
        print("\nSignal generation test failed. Exiting.")
        sys.exit(1)
    
    # Test multiple symbols (optional)
    test_multiple_symbols()
    
    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
