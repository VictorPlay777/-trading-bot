"""
Bybit V5 API Client - REST wrapper using requests (sync)
Bypasses CloudFront blocking of aiohttp
"""
import hashlib
import hmac
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode
import requests

from config import api_config
from logger import get_logger, log_event

logger = get_logger()


class BybitAPIError(Exception):
    """Custom exception for API errors"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Bybit API Error {code}: {message}")


class BybitClient:
    """Sync Bybit V5 API Client using requests"""
    
    def __init__(self):
        self.api_key = api_config.key
        self.api_secret = api_config.secret
        self.base_url = api_config.base_url
        self.recv_window = api_config.recv_window
        self._last_request_time = 0.0
        self._min_interval = 0.05  # 50ms between requests
        self.max_retries = 3  # Max retry attempts for connection errors
        self.category = "linear"  # Default category for futures
    
    def _generate_signature(self, timestamp: str, query_string: str = "", body_str: str = "") -> str:
        """Generate V5 API signature - EXACT format as working bot.py"""
        # For POST: param = timestamp + API_KEY + RECV_WINDOW + query_string + body_str
        # For GET: param = timestamp + API_KEY + RECV_WINDOW + query_string
        param = timestamp + self.api_key + str(self.recv_window) + query_string + body_str
        
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        """Get request headers - exact format as working bot.py"""
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(self.recv_window)
        }
    
    def _rate_limit(self):
        """Simple rate limiting"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()
    
    def _request(
        self,
        method: str,
        endpoint: str,
        query: str = "",
        body: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated request using requests with retry logic"""
        self._rate_limit()
        
        timestamp = str(int(time.time() * 1000))
        
        # For POST requests, include body in signature
        body_str = ""
        if body and method.upper() == "POST":
            body_str = json.dumps(body, separators=(",", ":"))
        
        # Generate signature
        signature = self._generate_signature(timestamp, query, body_str)
        headers = self._get_headers(timestamp, signature)
        
        url = self.base_url + endpoint
        if query:
            url += "?" + query
        
        # Retry logic for connection errors
        for attempt in range(self.max_retries):
            try:
                timeout = 30  # 30 second timeout
                if method.upper() == "GET":
                    r = requests.get(url, headers=headers, timeout=timeout)
                else:  # POST
                    headers["Content-Type"] = "application/json"
                    r = requests.post(url, headers=headers, data=body_str, timeout=timeout)
                
                # Log response details for debugging
                logger.debug(f"Response status: {r.status_code}")
                logger.debug(f"Response text (first 200 chars): {r.text[:200]}")
                
                # Check HTTP status
                if r.status_code != 200:
                    logger.error(f"HTTP {r.status_code}: {r.text[:500]}")
                    raise BybitAPIError(r.status_code, r.text[:200])
                
                data = r.json()
                
                # Check for API errors
                if data.get("retCode") != 0:
                    raise BybitAPIError(data.get("retCode"), data.get("retMsg", "Unknown error"))
                
                return data
                
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    # Regenerate timestamp and signature for retry
                    timestamp = str(int(time.time() * 1000))
                    signature = self._generate_signature(timestamp, query, body_str)
                    headers = self._get_headers(timestamp, signature)
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                    raise
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}, text: {r.text[:500] if 'r' in locals() else 'N/A'}")
                raise
    
    async def close(self):
        """Dummy close for compatibility"""
        pass
    
    # ==================== Market Data ====================
    
    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        category: str = "linear"
    ) -> List[Dict[str, Any]]:
        """Get candlestick data"""
        query = f"category={category}&symbol={symbol}&interval={interval}&limit={limit}"
        data = self._request("GET", "/v5/market/kline", query)
        return data.get("result", {}).get("list", [])
    
    def get_orderbook(self, symbol: str, limit: int = 50, category: str = "linear") -> Dict:
        """Get orderbook"""
        query = f"category={category}&symbol={symbol}&limit={limit}"
        return self._request("GET", "/v5/market/orderbook", query)
    
    def get_tickers(self, symbol: Optional[str] = None, category: str = "linear") -> Dict:
        """Get 24h ticker data"""
        query = f"category={category}"
        if symbol:
            query += f"&symbol={symbol}"
        return self._request("GET", "/v5/market/tickers", query)

    def get_instruments_info(self, symbol: Optional[str] = None, category: str = "linear") -> List:
        """Get instruments info (including lot size requirements)"""
        query = f"category={category}"
        if symbol:
            query += f"&symbol={symbol}"
        data = self._request("GET", "/v5/market/instruments-info", query)
        
        # Debug logging
        logger.debug(f"get_instruments_info raw data type: {type(data)}")
        if isinstance(data, dict):
            result = data.get("result", {})
            if isinstance(result, dict):
                return result.get("list", [])
            else:
                logger.error(f"Unexpected result type: {type(result)}")
                return []
        else:
            logger.error(f"Unexpected data type from API: {type(data)}, value: {str(data)[:100]}")
            return []
    
    def get_max_leverage(self, symbol: str, category: str = "linear") -> int:
        """
        Get maximum available leverage for a symbol from Bybit
        
        Args:
            symbol: Trading symbol
            category: Market category
            
        Returns:
            Maximum leverage as integer (e.g., 100, 50, 25, etc.)
        """
        try:
            instruments = self.get_instruments_info(symbol=symbol, category=category)
            if instruments and len(instruments) > 0:
                instrument = instruments[0]
                leverage_filter = instrument.get("leverageFilter", {})
                max_leverage = leverage_filter.get("maxLeverage", "100")
                # Convert from string like "100" or "50.00" to int
                return int(float(max_leverage))
            else:
                logger.warning(f"No instrument info found for {symbol}, defaulting to 100x")
                return 100
        except Exception as e:
            logger.error(f"Error getting max leverage for {symbol}: {e}")
            return 100
    
    def get_all_trading_symbols(self, min_volume_24h: float = 1000000, category: str = "linear") -> List[str]:
        """
        Get all active trading symbols with minimum volume
        
        Args:
            min_volume_24h: Minimum 24h volume in USDT (default 1M)
            category: Market category (linear for USDT perpetual)
            
        Returns:
            List of trading symbols (e.g., ["BTCUSDT", "ETHUSDT", ...])
        """
        try:
            # Get all instruments
            instruments = self.get_instruments_info(category=category)
            logger.debug(f"Got {len(instruments)} instruments from API")
            
            # Check if instruments is valid
            if not isinstance(instruments, list):
                logger.error(f"Invalid instruments data type: {type(instruments)}")
                return ["BTCUSDT", "ETHUSDT"]
            
            symbols = []
            
            # Get tickers for volume info
            tickers_response = self.get_tickers(category=category)
            
            # Extract list from response (API returns dict with result.list)
            tickers = []
            if isinstance(tickers_response, dict):
                tickers = tickers_response.get("result", {}).get("list", [])
            elif isinstance(tickers_response, list):
                tickers = tickers_response
            
            logger.debug(f"Got {len(tickers)} tickers")
            
            ticker_map = {t.get("symbol"): t for t in tickers if isinstance(t, dict) and t.get("symbol")}
            logger.debug(f"Created ticker map with {len(ticker_map)} entries")
            
            for instrument in instruments:
                # Skip if instrument is not a dict
                if not isinstance(instrument, dict):
                    continue
                
                symbol = instrument.get("symbol", "")
                
                # Skip non-perpetual and inverse contracts
                if not symbol or not symbol.endswith("USDT"):
                    continue
                
                # Check status
                status = instrument.get("status", "")
                if status != "Trading":
                    continue
                
                # Check volume
                ticker = ticker_map.get(symbol, {})
                volume_24h = float(ticker.get("turnover24h", 0))
                
                if volume_24h >= min_volume_24h:
                    symbols.append(symbol)
            
            logger.info(f"Found {len(symbols)} active trading symbols with volume >= ${min_volume_24h:,.0f}")
            return sorted(symbols)
            
        except Exception as e:
            logger.error(f"Error getting trading symbols: {e}")
            return ["BTCUSDT", "ETHUSDT"]  # Fallback to major pairs
    
    # ==================== Account ====================
    
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict:
        """Get wallet balance"""
        query = f"accountType={account_type}"
        return self._request("GET", "/v5/account/wallet-balance", query)
    
    # ==================== Position ====================
    
    def get_positions(
        self,
        symbol: Optional[str] = None,
        category: str = "linear"
    ) -> List[Dict[str, Any]]:
        """Get open positions"""
        query = f"category={category}"
        if symbol:
            query += f"&symbol={symbol}"
        data = self._request("GET", "/v5/position/list", query)
        return data.get("result", {}).get("list", [])
    
    def set_leverage(
        self,
        symbol: str,
        buy_leverage: int,
        sell_leverage: int,
        category: str = "linear"
    ) -> Dict:
        """Set leverage for a symbol"""
        body = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(sell_leverage)
        }
        try:
            return self._request("POST", "/v5/position/set-leverage", body=body)
        except BybitAPIError as e:
            # Error 110043: leverage not modified (already set to this value)
            if e.code == 110043:
                logger.warning(f"Leverage already set to {buy_leverage}x for {symbol}")
                return {"retCode": 0, "retMsg": "Leverage already set"}
            raise

    def set_margin_mode(self, symbol: str, margin_mode: str = "cross", category: str = "linear") -> Dict:
        """Set margin mode (cross or isolated) for a symbol"""
        body = {
            "category": category,
            "symbol": symbol,
            "marginMode": margin_mode
        }
        try:
            return self._request("POST", "/v5/position/switch-margin-mode", body=body)
        except BybitAPIError as e:
            # Error 110028: margin mode not modified (already set to this value)
            if e.code == 110028:
                logger.warning(f"Margin mode already set to {margin_mode} for {symbol}")
                return {"retCode": 0, "retMsg": "Margin mode already set"}
            raise
    
    # ==================== Order ====================
    
    def place_order(
        self,
        symbol: str,
        side: str,  # Buy or Sell
        order_type: str,  # Market, Limit
        qty: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,  # Percentage-based SL
        take_profit_pct: Optional[float] = None,  # Percentage-based TP
        category: str = "linear",
        order_link_id: Optional[str] = None,
        market_unit: Optional[str] = None,  # "qty" (baseCoin) or "quoteCoin" (USDT) for market orders
        reduce_only: bool = False,  # Only reduce position, don't open new
        close_on_trigger: bool = False  # Close position on trigger (for stop orders)
    ) -> Dict:
        """Place an order
        
        Args:
            reduce_only: True to only reduce position size (close position)
            close_on_trigger: True for stop orders that close position
        """
        body = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }
        
        # Add reduceOnly and closeOnTrigger for position closing
        if reduce_only:
            body["reduceOnly"] = True
        if close_on_trigger:
            body["closeOnTrigger"] = True

        # Add marketUnit for market orders if specified
        if order_type == "Market" and market_unit:
            body["marketUnit"] = market_unit

        if price and order_type == "Limit":
            body["price"] = str(price)

        # Use percentage-based TP/SL (like Bybit app)
        if stop_loss_pct is not None:
            body["stopLoss"] = str(stop_loss_pct)
            body["stopLossType"] = "Percentage"
        elif stop_loss:
            body["stopLoss"] = str(stop_loss)
            body["stopLossType"] = "Price"

        if take_profit_pct is not None:
            body["takeProfit"] = str(take_profit_pct)
            body["takeProfitType"] = "Percentage"
        elif take_profit:
            body["takeProfit"] = str(take_profit)
            body["takeProfitType"] = "Price"

        if order_link_id:
            body["orderLinkId"] = order_link_id

        log_event("info", f"Placing order: {side} {qty} {symbol}",
                  symbol=symbol, side=side, qty=qty, order_type=order_type)

        # Retry logic with fallback approaches
        max_order_retries = 3
        for attempt in range(max_order_retries):
            try:
                return self._request("POST", "/v5/order/create", body=body)
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                if attempt < max_order_retries - 1:
                    # Fallback 1: Remove market_unit if it's a market order
                    if attempt == 0 and order_type == "Market" and market_unit:
                        logger.warning(f"Order failed (attempt {attempt + 1}/{max_order_retries}): {e}. Retrying without market_unit...")
                        body.pop("marketUnit", None)
                        continue
                    
                    # Fallback 2: Try as limit order at current price if market order fails
                    if attempt == 1 and order_type == "Market":
                        logger.warning(f"Order failed (attempt {attempt + 1}/{max_order_retries}): {e}. Retrying as limit order...")
                        body["orderType"] = "Limit"
                        # Get current price
                        current_price = self.get_latest_price(symbol)
                        if current_price > 0:
                            body["price"] = str(current_price)
                        continue
                    
                    # Fallback 3: General retry with delay
                    wait_time = 2 ** attempt
                    logger.warning(f"Order failed (attempt {attempt + 1}/{max_order_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Order failed after {max_order_retries} attempts: {e}")
                    raise
    
    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
        category: str = "linear"
    ) -> Dict:
        """Cancel an order"""
        body = {"category": category, "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        
        return self._request("POST", "/v5/order/cancel", body=body)
    
    def get_open_orders(
        self,
        symbol: Optional[str] = None,
        category: str = "linear"
    ) -> List[Dict]:
        """Get open orders"""
        query = f"category={category}"
        if symbol:
            query += f"&symbol={symbol}"
        data = self._request("GET", "/v5/order/realtime", query)
        return data.get("result", {}).get("list", [])
    
    def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        category: str = "linear"
    ) -> List[Dict]:
        """Get order history"""
        query = f"category={category}&limit={limit}"
        if symbol:
            query += f"&symbol={symbol}"
        data = self._request("GET", "/v5/order/history", query)
        return data.get("result", {}).get("list", [])
    
    # ==================== Helpers ====================
    
    def get_latest_price(self, symbol: str, category: str = "linear") -> float:
        """Get latest mark price"""
        tickers = self.get_tickers(symbol, category)
        ticker_list = tickers.get("result", {}).get("list", [])
        if ticker_list:
            return float(ticker_list[0].get("lastPrice", 0))
        return 0.0
    
    def get_instrument_info(self, symbol: str, category: str = "linear") -> Dict:
        """Get instrument specifications"""
        query = f"category={category}&symbol={symbol}"
        data = self._request("GET", "/v5/market/instruments-info", query)
        instruments = data.get("result", {}).get("list", [])
        return instruments[0] if instruments else {}
    
    def check_position_state(self, symbol: str) -> Optional[Dict]:
        """Check actual position state from exchange"""
        try:
            positions = self.get_positions(symbol)
            for pos in positions:
                size = float(pos.get("size", 0))
                if size != 0:
                    avg_price = pos.get("avgPrice", 0)
                    if avg_price == "" or avg_price is None:
                        avg_price = 0
                    else:
                        avg_price = float(avg_price)

                    unrealised_pnl = pos.get("unrealisedPnl", 0)
                    if unrealised_pnl == "" or unrealised_pnl is None:
                        unrealised_pnl = 0
                    else:
                        unrealised_pnl = float(unrealised_pnl)

                    liq_price = pos.get("liqPrice", 0)
                    if liq_price == "" or liq_price is None:
                        liq_price = 0
                    else:
                        liq_price = float(liq_price)

                    return {
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),  # Buy or Sell
                        "size": abs(size),
                        "entry_price": avg_price,
                        "leverage": int(pos.get("leverage", 1)),
                        "unrealized_pnl": unrealised_pnl,
                        "liq_price": liq_price
                    }
            return None
        except Exception as e:
            logger.error(f"Error checking position state: {e}")
            return None

    def set_trading_stop(
        self,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop: Optional[float] = None,
        category: str = "linear",
        position_idx: int = 0
    ) -> Dict:
        """Set stop loss, take profit, or trailing stop for an existing position
        
        Args:
            position_idx: 0=one-way mode, 1=hedge-mode Buy, 2=hedge-mode Sell
        """
        body = {
            "category": category,
            "symbol": symbol,
            "positionIdx": position_idx,  # One-way mode default
        }
        
        if stop_loss is not None:
            body["stopLoss"] = str(stop_loss)
        
        if take_profit is not None:
            body["takeProfit"] = str(take_profit)
        
        if trailing_stop is not None:
            body["trailingStop"] = str(trailing_stop)
        
        return self._request("POST", "/v5/position/trading-stop", body=body)

    def set_leverage(
        self,
        symbol: str,
        buy_leverage: int,
        sell_leverage: Optional[int] = None,
        category: str = "linear"
    ) -> Dict:
        """Set leverage for a symbol
        
        Args:
            symbol: Trading symbol
            buy_leverage: Leverage for buy orders (1-100)
            sell_leverage: Leverage for sell orders (defaults to buy_leverage)
            category: Market category
            
        Returns:
            API response
        """
        body = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(sell_leverage if sell_leverage else buy_leverage),
        }
        
        try:
            return self._request("POST", "/v5/position/set-leverage", body=body)
        except BybitAPIError as e:
            # Error 110043: leverage not modified (already set to this value)
            if e.code == 110043:
                logger.info(f"Leverage already set to {buy_leverage}x for {symbol}")
                return {"retCode": 0, "retMsg": "Leverage already set"}
            raise

    def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """Get order book for a symbol"""
        try:
            response = self._request('GET', '/v5/market/orderbook', {
                'category': self.category,
                'symbol': symbol,
                'limit': limit
            })
            if response and 'result' in response and 'list' in response['result']:
                return response['result']['list'][0] if response['result']['list'] else None
        except Exception as e:
            logger.error(f"Error getting orderbook for {symbol}: {e}")
        return None

    def get_available_symbols(self, min_volume_24h: float = 1000000) -> List[str]:
        """Get available symbols with minimum 24h volume"""
        try:
            response = self._request('GET', '/v5/market/tickers', {
                'category': self.category
            })
            if response and 'result' in response and 'list' in response['result']:
                symbols = []
                for item in response['result']['list']:
                    symbol = item.get('symbol', '')
                    volume_24h = float(item.get('volume24h', 0)) * float(item.get('lastPrice', 0))

                    # Filter by volume and only include USDT pairs
                    if symbol.endswith('USDT') and volume_24h >= min_volume_24h:
                        symbols.append(symbol)

                logger.info(f"Found {len(symbols)} symbols with 24h volume >= ${min_volume_24h:.0f}")
                return symbols
        except Exception as e:
            logger.error(f"Error getting available symbols: {e}")
        return []

    def get_symbol_leverage_limit(self, symbol: str) -> int:
        """Get max leverage for a symbol"""
        try:
            response = self._request('GET', '/v5/market/instruments-info', {
                'category': self.category,
                'symbol': symbol
            })
            if response and 'result' in response and 'list' in response['result']:
                instrument = response['result']['list'][0]
                # Try to get leverageFilter from the response
                leverage_filter = instrument.get('leverageFilter')
                if leverage_filter and isinstance(leverage_filter, dict):
                    leverage_list = leverage_filter.get('leverageList', [])
                    if leverage_list and isinstance(leverage_list, list):
                        return max(int(item.get('leverage', 20)) for item in leverage_list)
                # Fallback: try to get maxLeverage directly
                if leverage_filter and isinstance(leverage_filter, dict):
                    max_lev_str = leverage_filter.get('maxLeverage', '20')
                    try:
                        max_lev = int(float(max_lev_str))
                        if max_lev > 1000:
                            max_lev = max_lev // 100  # Scale down if API returns 7500 instead of 75
                        return max_lev
                    except (ValueError, TypeError):
                        pass
                # Fallback: try to get from other fields
                logger.warning(f"Could not get leverageList for {symbol}, using instruments info")
        except Exception as e:
            logger.error(f"Error getting leverage limit for {symbol}: {e}")
        return 20  # Default fallback
