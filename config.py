import os
from dotenv import load_dotenv

load_dotenv()

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
MODE = os.getenv("MODE", "paper")  # "paper" или "real"

# Для paper trading не требуются API ключи для публичных данных
if MODE == "real" and (not BYBIT_API_KEY or not BYBIT_API_SECRET):
    raise ValueError("Для real trading требуются API-ключи. Используйте .env с BYBIT_API_KEY и BYBIT_API_SECRET")