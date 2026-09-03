import os
from dotenv import load_dotenv
load_dotenv()
print("API_KEY:", os.getenv("BYBIT_API_KEY"))
print("API_SECRET:", os.getenv("BYBIT_API_SECRET"))