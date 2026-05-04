"""
Exchange module for Bybit DEMO API (api-demo.bybit.com)
Uses direct HTTP requests like YOLO bot
"""
import time, hmac, hashlib, json, requests, sys, logging
from decimal import Decimal
import config
from utils.timeframes import to_ccxt_tf

# Setup logging for exchange debug
exchange_logger = logging.getLogger('exchange_debug')

class DecimalEncoder(json.JSONEncoder):
    """Custom encoder to keep large numbers as strings"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

class Exchange:
    def __init__(self, cfg):
        self.symbol = cfg['symbol']
        self.logger = logging.getLogger(__name__)  # Use module logger
        # Convert timeframe to Bybit V5 format
        tf_map = {
            '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
            '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
            '1d': 'D', '1w': 'W', '1M': 'M'
        }
        self.timeframe = tf_map.get(cfg['timeframe'], cfg['timeframe'])
        self.api_key = config.BYBIT_API_KEY or "rRsm08OPN027nk5hgF"
        self.api_secret = config.BYBIT_API_SECRET or "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA"
        self.base_url = "https://api-demo.bybit.com"  # DEMO URL
        self.recv_window = "10000"
        self.category = "linear"
        self._symbol_rules_cache = {}
    
    def _generate_signature(self, timestamp: str, params_str: str = "", body_str: str = "") -> str:
        """Generate HMAC SHA256 signature for Bybit API V5"""
        param_str = timestamp + self.api_key + self.recv_window + params_str + body_str
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self, timestamp: str, signature: str, auth: bool = True) -> dict:
        """Get request headers"""
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
        }
        if auth:
            headers["X-BAPI-SIGN"] = signature
        return headers
    
    def _request(self, method: str, endpoint: str, params: dict = None, auth: bool = True) -> dict:
        """Make HTTP request to Bybit API"""
        timestamp = str(int(time.time() * 1000))
        
        # Build query string for GET
        if method.upper() == "GET":
            if params:
                query_str = "&".join([f"{k}={v}" for k, v in params.items()])
            else:
                query_str = ""
            body_str = ""
        else:
            # For POST, body is in params
            query_str = ""
            if params:
                # Convert body to JSON string for signature (no spaces, like YOLO bot)
                # Use custom encoder to keep large numbers as strings
                self.logger.error(f"[EXCHANGE DEBUG] _request POST: params before json.dumps={params}")
                body_str = json.dumps(params, separators=(",", ":"), cls=DecimalEncoder)
                self.logger.error(f"[EXCHANGE DEBUG] _request POST: body_str after json.dumps={body_str}")
            else:
                body_str = ""
        
        # Generate signature for auth requests
        if auth:
            signature = self._generate_signature(timestamp, query_str, body_str)
            headers = self._get_headers(timestamp, signature, auth=True)
        else:
            headers = self._get_headers(timestamp, "", auth=False)
        
        # Build URL
        url = f"{self.base_url}{endpoint}"
        if query_str:
            url += f"?{query_str}"
        
        # Make request
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            else:
                headers["Content-Type"] = "application/json"
                response = requests.post(url, headers=headers, data=body_str, timeout=30)
            
            # Parse response
            data = response.json()
            
            # Check for API errors
            if data.get("retCode") != 0:
                raise Exception(f"API Error {data.get('retCode')}: {data.get('retMsg')}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
    
    def fetch_ohlcv(self, limit: int = 500):
        """Fetch candlestick data (public endpoint)"""
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "interval": self.timeframe,
            "limit": str(limit)
        }
        data = self._request("GET", "/v5/market/kline", params, auth=False)
        # Bybit returns data in reverse order (newest first), need to reverse
        candles = data.get("result", {}).get("list", [])
        # Bybit returns 7 columns: [time, open, high, low, close, volume, turnover]
        # We need only 6 columns (exclude turnover)
        candles = [c[:6] for c in candles]
        # Convert all columns to numbers
        for c in candles:
            c[0] = int(c[0]) / 1000  # timestamp to seconds
            c[1] = float(c[1])  # open
            c[2] = float(c[2])  # high
            c[3] = float(c[3])  # low
            c[4] = float(c[4])  # close
            c[5] = float(c[5])  # volume
        # Reverse to get oldest first (like ccxt)
        candles.reverse()
        return candles
    
    def fetch_ticker(self):
        """Fetch ticker data (public endpoint)"""
        params = {
            "category": self.category,
            "symbol": self.symbol
        }
        data = self._request("GET", "/v5/market/tickers", params, auth=False)
        tickers = data.get("result", {}).get("list", [])
        return tickers[0] if tickers else {}
    
    def fetch_all_tickers(self):
        """Fetch ALL linear tickers (public endpoint, no symbol filter)"""
        params = {
            "category": self.category
        }
        data = self._request("GET", "/v5/market/tickers", params, auth=False)
        return data.get("result", {}).get("list", [])
    
    def fetch_ohlcv_symbol(self, symbol: str, limit: int = 500):
        """Fetch candlestick data for any symbol (public endpoint)"""
        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": self.timeframe,
            "limit": str(limit)
        }
        data = self._request("GET", "/v5/market/kline", params, auth=False)
        candles = data.get("result", {}).get("list", [])
        candles = [c[:6] for c in candles]
        for c in candles:
            c[0] = int(c[0]) / 1000
            c[1] = float(c[1])
            c[2] = float(c[2])
            c[3] = float(c[3])
            c[4] = float(c[4])
            c[5] = float(c[5])
        candles.reverse()
        return candles
    
    def market_buy(self, qty: float):
        """Place market buy order"""
        # Ensure minimum order size (Bybit minimum for BTCUSDT is 0.01)
        min_qty = 0.01
        qty = max(qty, min_qty)
        # Round to 3 decimal places for Bybit precision
        qty = round(qty, 3)
        import sys
        print(f"[DEBUG] market_buy: original_qty={qty}, final_qty={qty}", file=sys.stderr)
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "side": "Buy",
            "orderType": "Market",
            "qty": str(qty)
        }
        print(f"[DEBUG] params: {params}", file=sys.stderr)
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def market_sell(self, qty: float):
        """Place market sell order"""
        # Ensure minimum order size (Bybit minimum for BTCUSDT is 0.01)
        min_qty = 0.01
        qty = max(qty, min_qty)
        # Round to 3 decimal places for Bybit precision
        qty = round(qty, 3)
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "side": "Sell",
            "orderType": "Market",
            "qty": str(qty)
        }
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def limit_buy(self, qty: float, price: float):
        """Place limit buy order (maker order - lower fee)"""
        min_qty = 0.01
        qty = max(qty, min_qty)
        qty = round(qty, 3)
        price = round(price, 2)
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "side": "Buy",
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC"
        }
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def limit_sell(self, qty: float, price: float):
        """Place limit sell order (maker order - lower fee)"""
        min_qty = 0.01
        qty = max(qty, min_qty)
        qty = round(qty, 3)
        price = round(price, 2)
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "side": "Sell",
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC"
        }
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def get_wallet_balance(self, account_type: str = "UNIFIED"):
        """Get wallet balance (private endpoint)"""
        params = {
            "accountType": account_type
        }
        return self._request("GET", "/v5/account/wallet-balance", params, auth=True)
    
    def get_positions(self, symbol: str = None):
        """Get open positions (private endpoint) - fetches ALL pages"""
        params = {
            "category": self.category
        }
        # API requires symbol or settleCoin
        if symbol:
            params["symbol"] = symbol
            return self._request("GET", "/v5/position/list", params, auth=True)
        else:
            params["settleCoin"] = "USDT"
            params["limit"] = "50"  # Max per page
            
        # Fetch all pages
        all_positions = []
        cursor = None
        while True:
            if cursor:
                params["cursor"] = cursor
            result = self._request("GET", "/v5/position/list", params, auth=True)
            if result.get('retCode') == 0:
                positions = result.get('result', {}).get('list', [])
                all_positions.extend(positions)
                cursor = result.get('result', {}).get('nextPageCursor')
                if not cursor:
                    break
            else:
                break
        
        # Return in same format as single request
        return {'retCode': 0, 'retMsg': 'OK', 'result': {'list': all_positions, 'category': self.category}}

    def get_executions(
        self,
        symbol: str = None,
        limit: int = 100,
        cursor: str = None,
        start_time_ms: int = None,
        end_time_ms: int = None,
    ):
        """
        Fetch executions (fills) from Bybit V5.
        Endpoint: GET /v5/execution/list
        Docs fields vary by account mode; caller must be tolerant.
        """
        params = {"category": self.category, "limit": str(limit)}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor
        if start_time_ms is not None:
            params["startTime"] = str(int(start_time_ms))
        if end_time_ms is not None:
            params["endTime"] = str(int(end_time_ms))
        return self._request("GET", "/v5/execution/list", params, auth=True)
    
    def set_leverage(self, leverage: int, symbol: str = None):
        """Set leverage for symbol (private endpoint)"""
        params = {
            "category": self.category,
            "symbol": symbol or self.symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        }
        return self._request("POST", "/v5/position/set-leverage", params, auth=True)
    
    def get_account_balance(self, account_type: str = "UNIFIED"):
        """Get account balance (alias for get_wallet_balance for compatibility)"""
        return self.get_wallet_balance(account_type)
    
    def _get_instrument_info(self, symbol: str = None):
        """Get instrument info for qty/lot size rules"""
        params = {
            "category": self.category,
            "symbol": symbol or self.symbol
        }
        data = self._request("GET", "/v5/market/instruments-info", params, auth=False)
        instruments = data.get("result", {}).get("list", [])
        return instruments[0] if instruments else None
    
    def _normalize_qty(self, qty: float, symbol: str = None) -> float:
        """Normalize qty according to Bybit lot size rules"""
        info = self._get_instrument_info(symbol)
        if not info:
            return round(qty, 3)
        
        lot_filter = info.get("lotSizeFilter", {})
        qty_step = lot_filter.get("qtyStep", "0.001")
        min_qty = lot_filter.get("minOrderQty", "0.001")
        max_qty = lot_filter.get("maxOrderQty", "1000000000")
        
        try:
            step = float(qty_step)
            min_q = float(min_qty)
            max_q = float(max_qty)
        except:
            step = 0.001
            min_q = 0.001
            max_q = 1000000000
        
        # Round down to step
        qty = (qty // step) * step
        # Ensure minimum
        qty = max(qty, min_q)
        # Ensure maximum
        qty = min(qty, max_q)
        
        return qty

    def _get_symbol_rules(self, symbol: str):
        sym = symbol or self.symbol
        if sym in self._symbol_rules_cache:
            return self._symbol_rules_cache[sym]
        info = self._get_instrument_info(sym)
        lot = (info or {}).get("lotSizeFilter", {})
        rules = {
            "qty_step": Decimal(str(lot.get("qtyStep", "0.001"))),
            "min_qty": Decimal(str(lot.get("minOrderQty", "0.001"))),
            "max_qty": Decimal(str(lot.get("maxOrderQty", "1000000000"))),
        }
        self._symbol_rules_cache[sym] = rules
        return rules

    def normalize_qty(self, symbol: str, qty, price: float = None, qty_in_notional: bool = False):
        """
        Normalize quantity for Bybit linear contracts.
        - supports qty passed as contracts OR notional USDT
        - floor to qty step
        - reject below min qty
        Returns Decimal normalized qty, or Decimal('0') if too small/invalid.
        """
        try:
            qty_dec = Decimal(str(qty))
            px = Decimal(str(price)) if price is not None else None
            if qty_in_notional:
                if px is None or px <= 0:
                    self.logger.error(f"[QTY NORM] {symbol} qty_in_notional but invalid price={price}")
                    return Decimal("0")
                qty_contracts = qty_dec / px
            else:
                qty_contracts = qty_dec

            rules = self._get_symbol_rules(symbol)
            step = rules["qty_step"]
            min_q = rules["min_qty"]
            max_q = rules["max_qty"]
            if step <= 0:
                step = Decimal("0.001")

            raw_qty = qty_contracts
            norm = (raw_qty // step) * step  # floor only
            if norm > max_q:
                norm = (max_q // step) * step

            self.logger.info(
                f"[QTY NORM] symbol={symbol} raw_qty={raw_qty} normalized_qty={norm} "
                f"step={step} min_qty={min_q} price={price} qty_in_notional={qty_in_notional}"
            )
            if norm < min_q or norm <= 0:
                self.logger.warning(
                    f"[QTY NORM] qty_too_small symbol={symbol} raw_qty={raw_qty} normalized_qty={norm} min_qty={min_q}"
                )
                return Decimal("0")
            return norm
        except Exception as e:
            self.logger.error(f"[QTY NORM] failed symbol={symbol} qty={qty} price={price}: {e}")
            return Decimal("0")
    
    def get_symbol_info(self, symbol: str):
        """Get trading rules for any symbol"""
        return self._get_instrument_info(symbol)
    
    def market_buy_symbol(self, symbol: str, qty):
        """Place market buy order (qty in coins)"""
        nqty = self.normalize_qty(symbol, qty)
        if nqty <= 0:
            self.logger.warning(f"[ORDER SKIP] qty_too_small symbol={symbol} side=Buy raw_qty={qty}")
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}
        # Always send qty as string - Bybit requires string format
        # Normalize: remove trailing .0 for integers ("250.0" → "250")
        qty_str = str(nqty)
        if isinstance(nqty, Decimal) and nqty == nqty.to_integral_value():
            qty_str = str(int(nqty))
        self.logger.error(f"[EXCHANGE DEBUG] market_buy_symbol: symbol={symbol} qty_input={qty} qty_str={qty_str}")
        
        params = {
            "category": self.category,
            "symbol": symbol,
            "side": "Buy",
            "orderType": "Market",
            "qty": qty_str  # Always string
        }
        self.logger.error(f"[EXCHANGE DEBUG] market_buy_symbol: params={params}")
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def market_sell_symbol(self, symbol: str, qty):
        """Place market sell order (qty in coins)"""
        nqty = self.normalize_qty(symbol, qty)
        if nqty <= 0:
            self.logger.warning(f"[ORDER SKIP] qty_too_small symbol={symbol} side=Sell raw_qty={qty}")
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}
        # Always send qty as string - Bybit requires string format
        # Normalize: remove trailing .0 for integers ("250.0" → "250")
        qty_str = str(nqty)
        if isinstance(nqty, Decimal) and nqty == nqty.to_integral_value():
            qty_str = str(int(nqty))
        self.logger.error(f"[EXCHANGE DEBUG] market_sell_symbol: symbol={symbol} qty_input={qty} qty_str={qty_str}")
        
        params = {
            "category": self.category,
            "symbol": symbol,
            "side": "Sell",
            "orderType": "Market",
            "qty": qty_str  # Always string
        }
        self.logger.error(f"[EXCHANGE DEBUG] market_sell_symbol: params={params}")
        return self._request("POST", "/v5/order/create", params, auth=True)
    
    def set_take_profit(self, symbol: str, side: str, qty, tp_price: float):
        """Set take profit limit order (reduce-only) after position opening.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'Buy' or 'Sell' (position side)
            qty: Position size to close
            tp_price: Take profit price (limit order price)
        """
        # Normalize qty
        qty_str = str(qty)
        if isinstance(qty, float) and qty == int(qty):
            qty_str = str(int(qty))
        elif isinstance(qty, Decimal) and qty == qty.to_integral_value():
            qty_str = str(int(qty))
        
        # For long position, we need to sell to close
        # For short position, we need to buy to close
        close_side = "Sell" if side == "Buy" else "Buy"
        
        params = {
            "category": self.category,
            "symbol": symbol,
            "side": close_side,
            "orderType": "Limit",
            "qty": qty_str,
            "price": str(tp_price),  # Limit price for TP
            "reduceOnly": True,  # Only reduce position, not increase
            "timeInForce": "GTC"  # Good till cancelled
        }
        
        self.logger.info(f"[TP ORDER] Setting TP for {symbol}: {close_side} {qty_str} @ {tp_price}")
        return self._request("POST", "/v5/order/create", params, auth=True)

    def limit_order(self, symbol: str, side: str, qty, price: float, reduce_only: bool = False):
        """Универсальный лимитный ордер (например ноги TP/SL). Для закрытия позиции всегда reduce_only=True."""
        nqty = self.normalize_qty(symbol, qty, price=price)
        if nqty <= 0:
            self.logger.warning(f"[ORDER SKIP] qty_too_small symbol={symbol} side={side} raw_qty={qty}")
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}
        qty_str = str(nqty)
        if isinstance(nqty, Decimal) and nqty == nqty.to_integral_value():
            qty_str = str(int(nqty))

        params = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "qty": qty_str,
            "price": str(price),
            "timeInForce": "GTC",
        }
        if reduce_only:
            params["reduceOnly"] = True

        self.logger.info(
            f"[LIMIT ORDER] {symbol} {side} qty={qty_str} @ {price} reduceOnly={reduce_only}"
        )
        return self._request("POST", "/v5/order/create", params, auth=True)

    def get_open_orders(self, symbol: str = None):
        """Открытые ордера (для отмены второй ноги TP/SL после исполнения одной)."""
        # Bybit V5: openOnly=0 -> active/open orders.
        params = {"category": self.category, "openOnly": 0}
        if symbol:
            params["symbol"] = symbol
        else:
            params["settleCoin"] = "USDT"
        return self._request("GET", "/v5/order/realtime", params, auth=True)

    def cancel_order(self, symbol: str, order_id: str):
        """Отмена ордера по orderId (linear)."""
        params = {
            "category": self.category,
            "symbol": symbol,
            "orderId": order_id,
        }
        self.logger.info(f"[CANCEL ORDER] {symbol} orderId={order_id}")
        return self._request("POST", "/v5/order/cancel", params, auth=True)

    def stop_limit_close(self, symbol: str, position_side: str, qty, trigger_price: float, limit_price: float = None):
        """
        Conditional stop-limit reduce-only close order.
        Needed to avoid immediate fill of plain limit SL.
        """
        nqty = self.normalize_qty(symbol, qty, price=limit_price or trigger_price)
        if nqty <= 0:
            self.logger.warning(f"[ORDER SKIP] qty_too_small symbol={symbol} stop_limit raw_qty={qty}")
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}
        qty_str = str(nqty)
        if isinstance(nqty, Decimal) and nqty == nqty.to_integral_value():
            qty_str = str(int(nqty))

        # Close side and trigger direction:
        # long SL: Sell when price falls to trigger => direction 2
        # short SL: Buy when price rises to trigger => direction 1
        if position_side == "long":
            side = "Sell"
            trigger_direction = 2
        else:
            side = "Buy"
            trigger_direction = 1

        if limit_price is None:
            limit_price = trigger_price

        params = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "qty": qty_str,
            "price": str(limit_price),
            "triggerPrice": str(trigger_price),
            "triggerDirection": trigger_direction,
            "orderFilter": "StopOrder",
            "reduceOnly": True,
            "timeInForce": "GTC",
        }
        self.logger.info(
            f"[STOP LIMIT SL] {symbol} {side} qty={qty_str} trigger={trigger_price} limit={limit_price}"
        )
        return self._request("POST", "/v5/order/create", params, auth=True)

    def market_reduce_only(self, symbol: str, position_side: str, qty):
        """
        Market reduce-only close.
        position_side: "long" | "short" (position direction to close).
        """
        nqty = self.normalize_qty(symbol, qty)
        if nqty <= 0:
            self.logger.warning(f"[ORDER SKIP] qty_too_small symbol={symbol} reduce_only raw_qty={qty}")
            return {"retCode": 10001, "retMsg": "qty_too_small", "result": {}}
        qty_str = str(nqty)
        if isinstance(nqty, Decimal) and nqty == nqty.to_integral_value():
            qty_str = str(int(nqty))
        side = "Sell" if position_side == "long" else "Buy"
        params = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": qty_str,
            "reduceOnly": True,
            "timeInForce": "IOC",
        }
        self.logger.info(f"[MARKET RO CLOSE] {symbol} side={side} qty={qty_str}")
        return self._request("POST", "/v5/order/create", params, auth=True)

    def fetch_ticker_symbol(self, symbol: str):
        params = {"category": self.category, "symbol": symbol}
        data = self._request("GET", "/v5/market/tickers", params, auth=False)
        lst = data.get("result", {}).get("list", [])
        return lst[0] if lst else {}

    def get_orderbook(self, symbol: str, limit: int = 50):
        params = {"category": self.category, "symbol": symbol, "limit": str(limit)}
        data = self._request("GET", "/v5/market/orderbook", params, auth=False)
        r = data.get("result", {})
        bids = [[float(x[0]), float(x[1])] for x in r.get("b", [])]
        asks = [[float(x[0]), float(x[1])] for x in r.get("a", [])]
        if bids and asks:
            spread_bps = (asks[0][0] - bids[0][0]) / ((asks[0][0] + bids[0][0]) / 2.0 + 1e-12) * 10000.0
        else:
            spread_bps = 999.0
        bid_depth = sum(p * q for p, q in bids[:10])
        ask_depth = sum(p * q for p, q in asks[:10])
        depth = min(bid_depth, ask_depth)
        imbalance = 0.0
        if bid_depth + ask_depth > 0:
            imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
        return {
            "bids": bids,
            "asks": asks,
            "spread_bps": float(spread_bps),
            "depth_usdt": float(depth),
            "imbalance": float(imbalance),
        }

    def get_funding_rate(self, symbol: str) -> float:
        params = {"category": self.category, "symbol": symbol, "limit": "1"}
        data = self._request("GET", "/v5/market/funding/history", params, auth=False)
        lst = data.get("result", {}).get("list", [])
        if not lst:
            return 0.0
        return float(lst[0].get("fundingRate", 0.0))

    def get_open_interest(self, symbol: str) -> float:
        params = {"category": self.category, "symbol": symbol, "intervalTime": "5min", "limit": "2"}
        data = self._request("GET", "/v5/market/open-interest", params, auth=False)
        lst = data.get("result", {}).get("list", [])
        if not lst:
            return 0.0
        return float(lst[0].get("openInterest", 0.0))
