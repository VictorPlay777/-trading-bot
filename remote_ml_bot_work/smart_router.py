class SmartRouter:
    def __init__(self, exchange, timeout_ms=600, requote_attempts=3):
        self.ex = exchange
        self.timeout_ms = timeout_ms
        self.requote_attempts = requote_attempts

    def enter(self, symbol: str, side: str, qty):
        # Deterministic entry: market-only to avoid duplicate fills from
        # limit-requote + market fallback race conditions.
        ticker = self.ex.fetch_ticker_symbol(symbol)
        ask = float(ticker.get("ask1Price", ticker.get("lastPrice", 0)))
        bid = float(ticker.get("bid1Price", ticker.get("lastPrice", 0)))
        px = ask if side == "long" else bid
        limit_side = "Buy" if side == "long" else "Sell"
        # qty may be contracts or notional; here qty comes as contracts from strategy.
        qty_norm = self.ex.normalize_qty(symbol, qty, price=px, qty_in_notional=False, is_market=True)
        if qty_norm <= 0:
            self.ex.logger.warning(
                f"[SMART ROUTER] qty_too_small symbol={symbol} raw_qty={qty} normalized_qty={qty_norm} price={px}"
            )
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}

        if side == "long":
            return self.ex.market_buy_symbol(symbol, qty_norm)
        return self.ex.market_sell_symbol(symbol, qty_norm)

