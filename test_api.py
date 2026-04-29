import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

# Тестируемые MODE
modes = ["paper", "testnet", "real"]

# API ключи
api_key = os.getenv("BYBIT_API_KEY", "rRsm08OPN027nk5hgF")
api_secret = os.getenv("BYBIT_API_SECRET", "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA")

print(f"Testing API key: {api_key}")
print(f"API secret: {api_secret[:10]}...")
print("-" * 50)

for mode in modes:
    print(f"\nTesting MODE={mode}")
    try:
        ex = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"}
        })
        
        if mode != "real":
            ex.set_sandbox_mode(True)
            # Явно задаем URL для testnet
            ex.urls['api']['rest']['public'] = 'https://api-demo.bybit.com'
            ex.urls['api']['rest']['private'] = 'https://api-demo.bybit.com'
        
        # Пробуем получить баланс
        balance = ex.fetch_balance()
        print(f"✓ MODE={mode} - SUCCESS!")
        print(f"  Balance: {balance}")
        
    except Exception as e:
        print(f"✗ MODE={mode} - FAILED: {e}")

print("\n" + "=" * 50)
print("Test complete")
