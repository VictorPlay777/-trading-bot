import pandas as pd


class MarketStream:
    def __init__(self, exchange):
        self.exchange = exchange

    def get_ohlcv(self, symbol: str, limit: int = 600) -> pd.DataFrame:
        raw = self.exchange.fetch_ohlcv_symbol(symbol, limit=limit)
        df = pd.DataFrame(raw, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df.set_index("time")

    def get_tickers(self):
        return self.exchange.fetch_all_tickers()

