class OrderbookStream:
    def __init__(self, exchange):
        self.exchange = exchange

    def snapshot(self, symbol: str) -> dict:
        try:
            return self.exchange.get_orderbook(symbol)
        except Exception:
            return {"bids": [], "asks": [], "spread_bps": 999.0, "depth_usdt": 0.0}

