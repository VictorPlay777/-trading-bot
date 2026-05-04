import ccxt
import config  # новый модуль
from utils.timeframes import to_ccxt_tf

class Exchange:
    def __init__(self, cfg):
        options = cfg.get('ccxt', {})
        self.symbol = cfg['symbol']
        self.timeframe = to_ccxt_tf(cfg['timeframe'])
        use_testnet = (config.MODE != "real")
        
        # Для paper trading без ключей используем только публичные данные
        if config.MODE == "paper" and not config.BYBIT_API_KEY:
            self.ex = ccxt.bybit({
                "enableRateLimit": options.get("enableRateLimit", True),
                "options": options.get("options", {"defaultType": "swap"})
            })
        else:
            self.ex = ccxt.bybit({
                "apiKey": config.BYBIT_API_KEY,
                "secret": config.BYBIT_API_SECRET,
                "enableRateLimit": options.get("enableRateLimit", True),
                "options": options.get("options", {"defaultType": "swap"})
            })
        
        if use_testnet:
            self.ex.set_sandbox_mode(True)
    def fetch_ohlcv(self, limit=500): return self.ex.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
    def fetch_ticker(self): return self.ex.fetch_ticker(self.symbol)
    def market_buy(self, qty): return self.ex.create_order(self.symbol, type="market", side="buy", amount=qty)
    def market_sell(self, qty): return self.ex.create_order(self.symbol, type="market", side="sell", amount=qty)
    def limit_order(self, symbol, side, qty, price, reduce_only=False):
        return self.ex.create_order(symbol, type="limit", side=side, amount=qty, price=price, params={'reduceOnly': reduce_only})
    def set_leverage(self, leverage: int): return self.ex.set_leverage(leverage, self.symbol)
