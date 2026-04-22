import logging
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Order execution engine with adaptive TP/SL.
    Supports market, limit, and adaptive order types.
    """
    
    def __init__(self, config: dict, api_key: str, api_secret: str, testnet: bool = True):
        self.config = config
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Execution config
        self.execution_config = config.get("execution", {})
        self.execution_type = self.execution_config.get("type", "hybrid")
        self.min_order_delay_ms = self.execution_config.get("min_order_delay_ms", 200)
        self.max_slippage_pct = self.execution_config.get("max_slippage_pct", 0.15)
        
        # Risk config for TP/SL
        self.risk_config = config.get("risk", {})
        self.base_tp_pct = self.risk_config.get("base_tp_pct", 0.25)
        self.base_sl_pct = self.risk_config.get("base_sl_pct", 0.12)
        self.atr_multiplier_tp = self.risk_config.get("atr_multiplier_tp", 1.2)
        self.atr_multiplier_sl = self.risk_config.get("atr_multiplier_sl", 0.7)
        
        # API endpoints
        self.base_url = "https://api-testnet.bybit.com/v5" if testnet else "https://api.bybit.com/v5"
        
        # Order tracking
        self.last_order_time: Dict[str, float] = {}  # symbol -> timestamp
        self.active_orders: Dict[str, dict] = {}  # order_id -> order info
        self.positions: Dict[str, dict] = {}  # symbol -> position info
        
        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start(self):
        """Initialize HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def stop(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            
    def _generate_signature(self, timestamp: str, query_string: str = "", body_str: str = "") -> str:
        """Generate V5 API signature - EXACT format as working api_client.py"""
        import hmac
        import hashlib
        
        # For POST: param = timestamp + API_KEY + RECV_WINDOW + query_string + body_str
        # For GET: param = timestamp + API_KEY + RECV_WINDOW + query_string
        recv_window = "5000"
        param = timestamp + self.api_key + recv_window + query_string + body_str
        
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
    async def _make_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """Make API request."""
        if not self.session:
            await self.start()
            
        url = f"{self.base_url}{endpoint}"
        timestamp = str(int(datetime.now().timestamp() * 1000))
        
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        
        # Add signature
        if params:
            import json
            query_string = ""
            body_str = json.dumps(params, separators=(",", ":"))  # No sort_keys like api_client.py
            signature = self._generate_signature(timestamp, query_string, body_str)
            headers["X-BAPI-SIGN"] = signature
            
        try:
            if method == "GET":
                async with self.session.get(url, headers=headers, params=params) as resp:
                    return await resp.json()
            elif method == "POST":
                async with self.session.post(url, headers=headers, json=params) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"API request error: {e}")
            return {"retCode": -1, "retMsg": str(e)}
            
    def calculate_tp_sl(self, symbol: str, entry_price: float, direction: str, atr: float = 0) -> Tuple[float, float]:
        """
        Calculate adaptive TP and SL based on config and ATR.
        Returns (tp_price, sl_price).
        """
        # Base TP/SL
        tp_pct = self.base_tp_pct / 100
        sl_pct = self.base_sl_pct / 100
        
        # Adjust based on ATR if available
        if atr > 0:
            tp_pct = max(tp_pct, atr * self.atr_multiplier_tp / entry_price)
            sl_pct = max(sl_pct, atr * self.atr_multiplier_sl / entry_price)
            
        # Calculate prices
        if direction == "long":
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:  # short
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)
            
        return tp_price, sl_price
        
    async def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None, 
                         tp: Optional[float] = None, sl: Optional[float] = None) -> dict:
        """
        Place order with adaptive TP/SL.
        Returns order info.
        """
        # Check order delay
        last_time = self.last_order_time.get(symbol, 0)
        current_time = datetime.now().timestamp() * 1000
        if current_time - last_time < self.min_order_delay_ms:
            logger.warning(f"Order delay for {symbol}: {current_time - last_time}ms < {self.min_order_delay_ms}ms")
            await asyncio.sleep((self.min_order_delay_ms - (current_time - last_time)) / 1000)
            
        # Determine order type
        order_type = "Market" if price is None else "Limit"
        
        # Build order params
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type,
            "qty": str(qty),
            "timeInForce": "GTC"
        }
        
        if price:
            params["price"] = str(price)
            
        # Add TP/SL if provided
        if tp and sl:
            params["stopLoss"] = str(sl)
            params["takeProfit"] = str(tp)
            params["tpslMode"] = "Full"
            
        # Place order
        response = await self._make_request("POST", "/order/create", params)
        
        # Update last order time
        self.last_order_time[symbol] = datetime.now().timestamp() * 1000
        
        # Log result
        if response.get("retCode") == 0:
            order_id = response.get("result", {}).get("orderId")
            logger.info(f"Order placed: {symbol} {side} {qty} @ {price or 'market'} (ID: {order_id})")
            
            self.active_orders[order_id] = {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "tp": tp,
                "sl": sl,
                "status": "New",
                "timestamp": datetime.now()
            }
        else:
            logger.error(f"Order failed: {response.get('retMsg')}")
            
        return response
        
    async def close_position(self, symbol: str) -> dict:
        """Close position for symbol."""
        # Get current position
        position = await self.get_position(symbol)
        if not position or position.get("size", 0) == 0:
            logger.warning(f"No position to close for {symbol}")
            return {"retCode": 0, "retMsg": "No position"}
            
        size = abs(position["size"])
        side = "Buy" if position["side"] == "Sell" else "Sell"
        
        # Place market order to close
        return await self.place_order(symbol, side, size)
        
    async def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position for symbol."""
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        response = await self._make_request("GET", "/position/list", params)
        
        if response.get("retCode") == 0 and response.get("result", {}).get("list"):
            positions = response["result"]["list"]
            for pos in positions:
                if pos["symbol"] == symbol:
                    self.positions[symbol] = {
                        "symbol": symbol,
                        "side": pos["side"],
                        "size": float(pos["size"]),
                        "entry_price": float(pos["avgPrice"]),
                        "unrealized_pnl": float(pos["unrealisedPnl"])
                    }
                    return self.positions[symbol]
                    
        return None
        
    async def get_all_positions(self) -> Dict[str, dict]:
        """Get all open positions."""
        params = {"category": "linear"}
        
        response = await self._make_request("GET", "/position/list", params)
        
        positions = {}
        if response.get("retCode") == 0 and response.get("result", {}).get("list"):
            for pos in response["result"]["list"]:
                if float(pos["size"]) != 0:
                    symbol = pos["symbol"]
                    positions[symbol] = {
                        "symbol": symbol,
                        "side": pos["side"],
                        "size": float(pos["size"]),
                        "entry_price": float(pos["avgPrice"]),
                        "unrealized_pnl": float(pos["unrealisedPnl"])
                    }
                    self.positions[symbol] = positions[symbol]
                    
        return positions
        
    def get_active_orders(self) -> Dict[str, dict]:
        """Get all active orders."""
        return self.active_orders.copy()
