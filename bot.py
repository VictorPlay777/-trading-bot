import time
import hmac
import hashlib
import requests
import json

ASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"


# ======================
# 🔐 SIGN v5
# ======================
def sign(timestamp, query_string=""):
    param = timestamp + API_KEY + RECV_WINDOW + query_string
    return hmac.new(
        API_SECRET.encode("utf-8"),
        param.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def get_timestamp():
    return str(int(time.time() * 1000))


# ======================
# 📊 BALANCE# ======================
def get_balance():
    ts = get_timestamp()

    query = "accountType=UNIFIED"

    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-SIGN": sign(ts, query),
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
    }

    url = BASE_URL + "/v5/account/wallet-balance?" + query

    r = requests.get(url, headers=headers)

    data = r.json()

    print(json.dumps(data, indent=2))

    # удобный вывод USDT
    try:
        usdt = data["result"]["list"][0]["totalEquity"]
        print("\n💰 USDT balance:", usdt)
    except:
        print("\n⚠️ Не удалось достать баланс (проверь accountType)")


# ======================
# 🚀 RUN
# ======================
get_balance()