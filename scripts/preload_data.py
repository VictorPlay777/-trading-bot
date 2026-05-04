import argparse
import ccxt
import pandas as pd
import time
from datetime import datetime

def fetch_ohlcv(symbol, timeframe, since, until, limit=1000):
    all_data = []
    while since < until:
        candles = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
        if not candles:
            break
        all_data.extend(candles)
        since = candles[-1][0] + timeframe_to_ms(timeframe)
        time.sleep(exchange.rateLimit / 1000)  # уважение к API
        if since >= until:
            break
    return all_data

def timeframe_to_ms(tf: str) -> int:
    """Перевод таймфрейма ccxt (1m, 5m, 1h, 1d, 1w, 1M) в миллисекунды"""
    unit = tf[-1]
    num = int(tf[:-1])
    if unit == 'm':
        return num * 60 * 1000
    if unit == 'h':
        return num * 60 * 60 * 1000
    if unit == 'd':
        return num * 24 * 60 * 60 * 1000
    if unit == 'w':
        return num * 7 * 24 * 60 * 60 * 1000
    if unit == 'M':
        return num * 30 * 24 * 60 * 60 * 1000
    raise ValueError(f"Неподдерживаемый таймфрейм: {tf}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, required=True, help="Например: BTCUSDT")
    parser.add_argument("--timeframe", type=str, required=True, help="Например: 1h, 15m, 1d")
    parser.add_argument("--start", type=str, required=True, help="Формат YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="Формат YYYY-MM-DD")
    args = parser.parse_args()

    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "future"}})

    start_ts = int(datetime.strptime(args.start, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(args.end, "%Y-%m-%d").timestamp() * 1000)

    print(f"Загружаем {args.symbol} {args.timeframe} с {args.start} по {args.end}...")

    data = fetch_ohlcv(args.symbol, args.timeframe, start_ts, end_ts)

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

    output_path = f"data/{args.symbol}_{args.timeframe}.csv"
    df.to_csv(output_path, index=False)
    print(f"Сохранено {len(df)} свечей в {output_path}")
