class OrphanOrderCleaner:
    def __init__(self, exchange):
        self.ex = exchange

    def cleanup_symbol_reduce_only(self, symbol: str):
        try:
            oo = self.ex.get_open_orders(symbol).get("result", {}).get("list", [])
        except Exception:
            return
        for o in oo:
            if o.get("reduceOnly"):
                oid = o.get("orderId")
                if oid:
                    try:
                        self.ex.cancel_order(symbol, oid)
                    except Exception:
                        pass

