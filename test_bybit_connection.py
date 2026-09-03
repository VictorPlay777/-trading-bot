import os
os.environ["BYBIT_API_KEY"] = "XvnYt5kZGnA6SHDZXp"
os.environ["BYBIT_API_SECRET"] = "jt0g1wswGaCe9EPEP0ene7rAJmiqcizlL6zk"

import ccxt

print("Testing Bybit connection with new keys...")
print(f"API Key: {os.environ['BYBIT_API_KEY']}")
print(f"API Secret: {os.environ['BYBIT_API_SECRET'][:10]}...")

try:
    ex = ccxt.bybit({
        "apiKey": os.environ["BYBIT_API_KEY"],
        "secret": os.environ["BYBIT_API_SECRET"],
        "enableRateLimit": True,
        "options": {"defaultType": "swap"}
    })
    
    ex.set_sandbox_mode(True)
    ex.urls['api']['rest']['public'] = 'https://api-demo.bybit.com'
    ex.urls['api']['rest']['private'] = 'https://api-demo.bybit.com'
    
    balance = ex.fetch_balance()
    print("SUCCESS! Connection to Bybit testnet works!")
    print(f"Balance: {balance}")
    
except Exception as e:
    print(f"FAILED: {e}")