"""
Execution Layer - Order placement with retry logic and safety checks
"""
import asyncio
import uuid
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from api_client import BybitClient, BybitAPIError
from logger import get_logger, log_event
from config import execution_config, trading_config, risk_config
from strategy import Signal, SignalType
from risk_manager import PositionSize

logger = get_logger()


@dataclass
class OrderResult:
    """Order execution result"""
    success: bool
    order_id: Optional[str]
    filled_price: float
    filled_qty: float
    error: Optional[str] = None
    retry_count: int = 0


class ExecutionEngine:
    """
    Handles order execution with:
    - Retry logic
    - Order confirmation
    - Duplicate prevention
    - Idempotency
    """
    
    def __init__(self, api_client: BybitClient):
        self.api = api_client
        self.cfg = execution_config
        self._pending_orders: Dict[str, Dict] = {}  # Track pending orders
        self._order_history: Dict[str, datetime] = {}  # Prevent duplicates
    
    def _generate_order_link_id(self, symbol: str, side: str) -> str:
        """Generate unique order ID for idempotency"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique = str(uuid.uuid4())[:6]
        return f"bot_{symbol}_{side}_{timestamp}_{unique}"
    
    def _is_duplicate(self, order_link_id: str) -> bool:
        """Check if order is duplicate"""
        if order_link_id in self._order_history:
            age = (datetime.utcnow() - self._order_history[order_link_id]).total_seconds()
            if age < 60:  # Prevent duplicates within 60 seconds
                return True
        return False
    
    async def _place_order_with_retry(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult:
        """Place order with retry logic"""
        order_link_id = self._generate_order_link_id(symbol, side)
        
        # Check for duplicate
        if self._is_duplicate(order_link_id):
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=0.0,
                filled_qty=0.0,
                error="Duplicate order prevented"
            )
        
        last_error = None
        
        for attempt in range(self.cfg.max_retries):
            try:
                # Rate limiting between attempts
                if attempt > 0:
                    await asyncio.sleep(self.cfg.retry_delay_sec * (2 ** attempt))
                
                log_event("debug", f"Order attempt {attempt + 1}/{self.cfg.max_retries}",
                          symbol=symbol, side=side, qty=qty)
                
                result = await self.api.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    qty=qty,
                    price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    order_link_id=order_link_id
                )
                
                # Record order
                self._order_history[order_link_id] = datetime.utcnow()
                
                order_id = result.get("result", {}).get("orderId")
                
                # For market orders, check fill status
                if order_type == "Market":
                    filled = await self._confirm_fill(symbol, order_id, order_link_id)
                    if not filled:
                        continue  # Retry
                
                # Get filled price from order history
                filled_price = await self._get_filled_price(order_id, symbol)
                
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    filled_price=filled_price,
                    filled_qty=qty,
                    retry_count=attempt
                )
                
            except BybitAPIError as e:
                last_error = f"API Error {e.code}: {e.message}"
                log_event("warning", f"Order failed (attempt {attempt + 1}): {last_error}")
                
                # Don't retry on certain errors
                if e.code in [10001, 10002]:  # Invalid parameters
                    break
                    
            except Exception as e:
                last_error = str(e)
                log_event("warning", f"Order exception (attempt {attempt + 1}): {last_error}")
        
        return OrderResult(
            success=False,
            order_id=None,
            filled_price=0.0,
            filled_qty=0.0,
            error=f"Max retries exceeded: {last_error}",
            retry_count=self.cfg.max_retries
        )
    
    async def _confirm_fill(
        self,
        symbol: str,
        order_id: Optional[str],
        order_link_id: str,
        timeout: int = None
    ) -> bool:
        """Confirm order was filled"""
        timeout = timeout or self.cfg.confirmation_timeout_sec
        
        if not order_id and not order_link_id:
            return False
        
        start = datetime.utcnow()
        
        while (datetime.utcnow() - start).total_seconds() < timeout:
            try:
                # Check order history
                orders = await self.api.get_order_history(symbol, limit=10)
                
                for order in orders:
                    if (order.get("orderId") == order_id or 
                        order.get("orderLinkId") == order_link_id):
                        
                        status = order.get("orderStatus", "")
                        if status in ["Filled", "PartiallyFilledCanceled"]:
                            return True
                        elif status in ["Rejected", "Cancelled"]:
                            return False
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error confirming fill: {e}")
                await asyncio.sleep(0.5)
        
        return False
    
    async def _get_filled_price(self, order_id: str, symbol: str) -> float:
        """Get filled price from order history"""
        try:
            orders = await self.api.get_order_history(symbol, limit=10)
            for order in orders:
                if order.get("orderId") == order_id:
                    avg_price = order.get("avgPrice", "0")
                    return float(avg_price) if avg_price else 0.0
        except Exception as e:
            logger.error(f"Error getting filled price: {e}")
        
        # Fallback to current price
        try:
            return await self.api.get_latest_price(symbol)
        except:
            return 0.0
    
    async def execute_entry(
        self,
        signal: Signal,
        position_size: PositionSize
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Execute entry order based on signal
        """
        symbol = signal.symbol
        side = "Buy" if signal.signal_type == SignalType.LONG_ENTRY else "Sell"
        
        # Round size to appropriate precision (Bybit usually wants 3 decimals for BTC)
        qty = round(position_size.size, 3)
        
        if qty <= 0:
            return False, {"error": "Invalid position size"}
        
        log_event("info", f"Executing {side} entry for {symbol}, qty={qty}",
                  signal=signal.reason,
                  confidence=signal.confidence)

        # For short positions, stop loss must be above entry price
        sl = position_size.stop_loss_price
        tp = position_size.take_profit_1

        if side == "Sell":
            # Use signal's TP/SL values directly (already calculated correctly)
            if signal.stop_loss:
                sl = signal.stop_loss
            if signal.take_profit_1:
                tp = signal.take_profit_1

        result = await self._place_order_with_retry(
            symbol=symbol,
            side=side,
            order_type=self.cfg.entry_order_type,
            qty=qty,
            stop_loss=sl,
            take_profit=tp
        )
        
        if result.success:
            return True, {
                "order_id": result.order_id,
                "filled_price": result.filled_price,
                "qty": result.filled_qty,
                "retry_count": result.retry_count
            }
        else:
            log_event("error", f"Entry execution failed: {result.error}")
            return False, {"error": result.error}
    
    async def execute_exit(
        self,
        symbol: str,
        direction: str,
        reason: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Execute exit order
        """
        # Determine close side
        side = "Sell" if direction == "long" else "Buy"
        
        # Get position size from API to close exact amount
        try:
            positions = await self.api.get_positions(symbol)
            if not positions:
                return False, {"error": "No position found to close"}
            
            # Find matching position
            qty = 0.0
            for pos in positions:
                pos_side = pos.get("side", "")
                if (direction == "long" and pos_side == "Buy") or \
                   (direction == "short" and pos_side == "Sell"):
                    qty = abs(float(pos.get("size", 0)))
                    break
            
            if qty <= 0:
                return False, {"error": "Position size is zero"}
            
        except Exception as e:
            return False, {"error": f"Failed to get position: {e}"}
        
        log_event("info", f"Executing {side} exit for {symbol}, qty={qty}, reason: {reason}")
        
        result = await self._place_order_with_retry(
            symbol=symbol,
            side=side,
            order_type="Market",  # Always market for exits
            qty=round(qty, 3)
        )
        
        if result.success:
            return True, {
                "order_id": result.order_id,
                "filled_price": result.filled_price,
                "qty": result.filled_qty,
                "reason": reason
            }
        else:
            log_event("error", f"Exit execution failed: {result.error}")
            return False, {"error": result.error}
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for symbol"""
        try:
            result = await self.api.set_leverage(
                symbol=symbol,
                buy_leverage=leverage,
                sell_leverage=leverage
            )
            log_event("info", f"Leverage set to {leverage}x for {symbol}")
            return True
        except BybitAPIError as e:
            # Leverage might already be set
            if "leverage not modified" in e.message.lower():
                return True
            log_event("error", f"Failed to set leverage: {e.message}")
            return False
        except Exception as e:
            log_event("error", f"Exception setting leverage: {e}")
            return False
    
    async def check_position_state(self, symbol: str) -> Optional[Dict]:
        """Check actual position state from exchange"""
        try:
            positions = await self.api.get_positions(symbol)
            for pos in positions:
                size = float(pos.get("size", 0))
                if size != 0:
                    return {
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),  # Buy or Sell
                        "size": abs(size),
                        "entry_price": float(pos.get("avgPrice", 0)),
                        "leverage": int(pos.get("leverage", 1)),
                        "unrealized_pnl": float(pos.get("unrealisedPnl", 0)),
                        "liq_price": float(pos.get("liqPrice", 0))
                    }
            return None
        except Exception as e:
            logger.error(f"Error checking position state: {e}")
            return None
    
    async def sync_state(self, symbol: str, expected_direction: Optional[str]) -> Optional[str]:
        """Sync local state with exchange"""
        actual = await self.check_position_state(symbol)
        
        if actual is None:
            return None  # No position
        
        actual_direction = "long" if actual["side"] == "Buy" else "short"
        
        if expected_direction != actual_direction:
            log_event("warning", f"Position direction mismatch: expected {expected_direction}, got {actual_direction}")
        
        return actual_direction
