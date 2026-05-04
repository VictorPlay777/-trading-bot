from datetime import datetime
class Broker:
    def __init__(self, ex, cfg, logger=None):
        self.ex = ex; self.cfg = cfg; self.logger = logger
    def enter_market(self, direction: str, qty: float):
        if direction=='long': order=self.ex.market_buy(qty)
        else: order=self.ex.market_sell(qty)
        if self.logger: self.logger.info(f"Вход {direction} qty={qty} → {order}")
        return order
