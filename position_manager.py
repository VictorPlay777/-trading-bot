"""
Position Manager - Manages all positions with PROBE/SCOUT/MOMENTUM trade types
"""
import logging
import time
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import pandas as pd

logger = logging.getLogger(__name__)


class TradeType(Enum):
    """Trade types"""
    PROBE = "probe"  # 5% of position - test market
    SCOUT = "scout"  # 20% of position - confirmed signal
    MOMENTUM = "momentum"  # 30-50% of position - sharp movement
    NORMAL = "normal"  # Full position


@dataclass
class Position:
    """Position data"""
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    quantity: float
    trade_type: TradeType
    leverage: int
    stop_loss: Optional[float]
    take_profit: Optional[float]
    trailing_stop: Optional[float]
    entry_time: datetime
    pyramiding_level: int = 0  # 0 = initial, 1-3 = pyramiding levels
    pnl: float = 0.0
    status: str = "open"  # "open", "closed"
    sl_tp_set: bool = False  # Flag to track if SL/TP have been applied to exchange
    
    @property
    def notional(self) -> float:
        """Position notional value"""
        return self.quantity * self.entry_price


class PositionManager:
    """
    Manages all positions with PROBE/SCOUT/MOMENTUM trade types
    
    Trade Types:
    - PROBE: 5% of position size - test market
    - SCOUT: 20% of position size - confirmed signal
    - MOMENTUM: 30-50% of position size - sharp movement
    
    Pyramiding:
    - Level 1: +1.3x
    - Level 2: +1.5x
    - Level 3: +1.7x
    
    Rules:
    - Add only to profitable positions
    - Max 3-4 additions
    - Don't exceed max position size
    - Never add to losing position
    - Always use stop loss
    - Trailing stop for strong profits
    """
    
    def __init__(self, config, api_client):
        self.cfg = config
        self.api = api_client
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        
        # Trade type percentages
        self.probe_pct = 0.05  # 5% of max position
        self.scout_pct = 0.20  # 20% of max position
        self.momentum_pct_min = 0.30  # 30% of max position
        self.momentum_pct_max = 0.50  # 50% of max position
        
        # Pyramiding multipliers
        self.pyramiding_multipliers = [1.3, 1.5, 1.7]  # Level 1, 2, 3
        self.max_pyramiding_levels = 3
        
        # Stop loss settings
        self.sl_atr_multiplier = 1.0  # SL = 1x ATR
        self.sl_fixed_pct = 0.02  # 2% fixed SL fallback (increased to ensure validity)
        
        # Trailing stop settings
        self.trailing_stop_activation_pct = 0.01  # Activate at 1% profit
        self.trailing_stop_distance_pct = 0.01  # 1% trailing distance
        
    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        trade_type: TradeType,
        max_position_size: float,
        leverage: int,
        atr: Optional[float] = None
    ) -> bool:
        """
        Open a new position
        
        Args:
            symbol: Trading symbol
            direction: "long" or "short"
            entry_price: Entry price
            trade_type: Trade type (PROBE/SCOUT/MOMENTUM/NORMAL)
            max_position_size: Maximum position size in USD
            leverage: Leverage to use
            atr: ATR for stop loss calculation
            
        Returns:
            True if position opened successfully, False otherwise
        """
        try:
            # Check if position already exists
            if symbol in self.positions:
                logger.warning(f"Position already exists for {symbol}")
                return False
            
            # Get instrument info for qty_step and min_qty
            instrument_info = self.api.get_instrument_info(symbol)
            qty_step = float(instrument_info.get("lotSizeFilter", {}).get("qtyStep", 0.001))
            min_qty = float(instrument_info.get("lotSizeFilter", {}).get("minOrderQty", 0.001))
            
            # Calculate position size based on trade type
            if trade_type == TradeType.PROBE:
                position_size = max_position_size * self.probe_pct
            elif trade_type == TradeType.SCOUT:
                position_size = max_position_size * self.scout_pct
            elif trade_type == TradeType.MOMENTUM:
                # Use 30-50% based on momentum strength (simplified to 40% for now)
                position_size = max_position_size * 0.40
            else:  # NORMAL
                position_size = max_position_size
            
            # Calculate quantity
            quantity = position_size / entry_price
            
            # Round quantity to qty_step precision with better precision handling
            quantity = round(quantity / qty_step) * qty_step
            quantity = round(quantity, 8)  # Round to 8 decimal places to avoid floating point issues
            
            # Ensure quantity meets minimum order requirement
            if quantity < min_qty:
                quantity = min_qty
            
            # Log the final quantity for debugging
            logger.debug(f"Calculated quantity: {quantity}, qty_step: {qty_step}, min_qty: {min_qty}")
            
            logger.info(f"Position size: ${position_size:.2f}, Quantity: {quantity} BTC, Entry: ${entry_price:.2f}")
            
            # Calculate stop loss and take profit for position tracking (not for order)
            if atr:
                sl_distance = atr * self.sl_atr_multiplier
            else:
                sl_distance = entry_price * self.sl_fixed_pct
            
            if direction == "long":
                stop_loss = entry_price - sl_distance  # Below entry for long
                take_profit = entry_price + (sl_distance * 2)  # Above entry for long (2x risk)
            else:
                stop_loss = entry_price + sl_distance  # Above entry for short
                take_profit = entry_price - (sl_distance * 2)  # Below entry for short (2x risk)
            
            # Place order via API without stop loss/take profit (will add in next cycle)
            result = self.api.place_order(
                symbol=symbol,
                side="Buy" if direction == "long" else "Sell",
                order_type="Market",
                qty=quantity
            )
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to open position for {symbol}: {result.get('retMsg')}")
                return False
            
            # SL/TP will be set in next engine cycle after position is confirmed
            # This avoids sleep() delay and handles async position creation
            
            # Create position object (SL/TP will be set later)
            position = Position(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                trade_type=trade_type,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=None,
                entry_time=datetime.utcnow(),
                pyramiding_level=0,
                status="open",
                sl_tp_set=False  # Will be set in next engine cycle
            )
            
            self.positions[symbol] = position
            logger.info(f"Opened {trade_type.value} position: {direction} {quantity:.4f} {symbol} @ {entry_price:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}")
            return False
    
    def close_position(self, symbol: str, reason: str = "") -> bool:
        """
        Close an existing position
        
        Args:
            symbol: Trading symbol
            reason: Reason for closing
            
        Returns:
            True if position closed successfully, False otherwise
        """
        try:
            if symbol not in self.positions:
                logger.warning(f"No position found for {symbol}")
                return False
            
            position = self.positions[symbol]
            
            # Place closing order with reduceOnly to ensure we only close, not open new position
            result = self.api.place_order(
                symbol=symbol,
                side="Sell" if position.direction == "long" else "Buy",
                order_type="Market",
                qty=position.quantity,
                reduce_only=True  # Bybit API: only reduce position, don't open new
            )
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to close position for {symbol}: {result.get('retMsg')}")
                return False
            
            # Update position status
            position.status = "closed"
            logger.info(f"Closed position: {symbol} (reason: {reason})")
            
            # Remove from active positions
            del self.positions[symbol]
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            return False
    
    def pyramid_position(self, symbol: str, current_price: float, max_position_size: float) -> bool:
        """
        Add to a profitable position (pyramiding)
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            max_position_size: Maximum position size in USD
            
        Returns:
            True if pyramiding successful, False otherwise
        """
        try:
            if symbol not in self.positions:
                logger.warning(f"No position found for {symbol}")
                return False
            
            position = self.positions[symbol]
            
            # Check if position is profitable
            if position.direction == "long":
                profit_pct = (current_price - position.entry_price) / position.entry_price
            else:
                profit_pct = (position.entry_price - current_price) / position.entry_price
            
            if profit_pct <= 0:
                logger.warning(f"Position not profitable, cannot pyramid {symbol}")
                return False
            
            # Check if max pyramiding level reached
            if position.pyramiding_level >= self.max_pyramiding_levels:
                logger.warning(f"Max pyramiding level reached for {symbol}")
                return False
            
            # Calculate addition size
            multiplier = self.pyramiding_multipliers[position.pyramiding_level]
            additional_quantity = position.quantity * (multiplier - 1)
            
            # Check if would exceed max position size
            new_total_notional = (position.quantity + additional_quantity) * current_price
            if new_total_notional > max_position_size:
                logger.warning(f"Pyramiding would exceed max position size for {symbol}")
                return False
            
            # Place addition order
            result = self.api.place_order(
                symbol=symbol,
                side="Buy" if position.direction == "long" else "Sell",
                order_type="Market",
                qty=additional_quantity
            )
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to pyramid position for {symbol}: {result.get('retMsg')}")
                return False
            
            # Update position
            position.quantity += additional_quantity
            position.pyramiding_level += 1
            logger.info(f"Pyramided position {symbol}: level {position.pyramiding_level}, added {additional_quantity:.4f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error pyramiding position for {symbol}: {e}")
            return False
    
    def update_trailing_stop(self, symbol: str, current_price: float) -> bool:
        """
        Update trailing stop for a profitable position
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            
        Returns:
            True if trailing stop updated, False otherwise
        """
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            # Calculate profit
            if position.direction == "long":
                profit_pct = (current_price - position.entry_price) / position.entry_price
            else:
                profit_pct = (position.entry_price - current_price) / position.entry_price
            
            # Check if profit threshold reached
            if profit_pct < self.trailing_stop_activation_pct:
                return False
            
            # Calculate new trailing stop
            if position.direction == "long":
                new_trailing_stop = current_price * (1 - self.trailing_stop_distance_pct)
            else:
                new_trailing_stop = current_price * (1 + self.trailing_stop_distance_pct)
            
            # Update if better than current
            if position.trailing_stop is None or \
               (position.direction == "long" and new_trailing_stop > position.trailing_stop) or \
               (position.direction == "short" and new_trailing_stop < position.trailing_stop):
                
                # Update stop loss via API
                result = self.api.place_order(
                    symbol=symbol,
                    side="Buy" if position.direction == "short" else "Sell",
                    order_type="Stop",
                    qty=position.quantity,
                    stop_loss=new_trailing_stop
                )
                
                if result.get("retCode") == 0:
                    position.trailing_stop = new_trailing_stop
                    position.stop_loss = new_trailing_stop
                    logger.info(f"Updated trailing stop for {symbol}: {new_trailing_stop:.2f}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating trailing stop for {symbol}: {e}")
            return False
    
    def _calculate_stop_loss(self, entry_price: float, direction: str, atr: Optional[float]) -> Optional[float]:
        """Calculate stop loss based on ATR or fixed percentage"""
        if atr:
            sl_distance = atr * self.sl_atr_multiplier
        else:
            sl_distance = entry_price * self.sl_fixed_pct
        
        if direction == "long":
            return entry_price - sl_distance
        else:
            return entry_price + sl_distance
    
    def manage_smart_stops(self, symbol: str, current_price: float, atr: Optional[float] = None) -> bool:
        """
        Smart stop management with breakeven and trailing stops
        
        Strategy:
        - After 1x risk profit: Move SL to breakeven (entry price)
        - After 2x risk profit: Activate trailing stop
        - After 3x risk profit: Take partial profit (50%)
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            atr: Current ATR value for trailing distance
            
        Returns:
            True if any action taken, False otherwise
        """
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            # Calculate risk distance (initial SL distance from entry)
            if atr:
                risk_distance = atr * self.sl_atr_multiplier
            else:
                risk_distance = position.entry_price * self.sl_fixed_pct
            
            # Calculate current profit in price terms
            if position.direction == "long":
                profit_distance = current_price - position.entry_price
            else:
                profit_distance = position.entry_price - current_price
            
            # Calculate profit multiple of risk
            profit_multiple = profit_distance / risk_distance if risk_distance > 0 else 0
            
            action_taken = False
            
            # Stage 1: Move to breakeven after 1x risk profit
            if profit_multiple >= 1.0 and position.stop_loss:
                # Check if SL is below entry for long, above entry for short
                if position.direction == "long" and position.stop_loss < position.entry_price:
                    new_sl = position.entry_price
                    sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                    if sl_result.get("retCode") == 0:
                        position.stop_loss = new_sl
                        logger.info(f"Smart SL: Moved to breakeven for {symbol} at {new_sl:.2f}")
                        action_taken = True
                elif position.direction == "short" and position.stop_loss > position.entry_price:
                    new_sl = position.entry_price
                    sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                    if sl_result.get("retCode") == 0:
                        position.stop_loss = new_sl
                        logger.info(f"Smart SL: Moved to breakeven for {symbol} at {new_sl:.2f}")
                        action_taken = True
            
            # Stage 2: Activate trailing stop after 2x risk profit
            if profit_multiple >= 2.0:
                trailing_distance = atr if atr else position.entry_price * 0.01
                
                if position.direction == "long":
                    new_trailing_sl = current_price - trailing_distance
                    # Only update if new SL is higher than current
                    if new_trailing_sl > position.stop_loss:
                        sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_trailing_sl)
                        if sl_result.get("retCode") == 0:
                            position.stop_loss = new_trailing_sl
                            position.trailing_stop = new_trailing_sl
                            logger.info(f"Smart SL: Updated trailing stop for {symbol} to {new_trailing_sl:.2f}")
                            action_taken = True
                else:
                    new_trailing_sl = current_price + trailing_distance
                    # Only update if new SL is lower than current
                    if new_trailing_sl < position.stop_loss:
                        sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_trailing_sl)
                        if sl_result.get("retCode") == 0:
                            position.stop_loss = new_trailing_sl
                            position.trailing_stop = new_trailing_sl
                            logger.info(f"Smart SL: Updated trailing stop for {symbol} to {new_trailing_sl:.2f}")
                            action_taken = True
            
            return action_taken
            
        except Exception as e:
            logger.error(f"Error in smart stop management for {symbol}: {e}")
            return False
    
    def take_partial_profit(self, symbol: str, current_price: float, profit_multiple: float) -> bool:
        """
        Take partial profit at key levels
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            profit_multiple: Current profit as multiple of initial risk
            
        Returns:
            True if partial profit taken, False otherwise
        """
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            # Take 50% profit at 3x risk level (only once)
            if profit_multiple >= 3.0 and not getattr(position, 'partial_profit_taken', False):
                close_quantity = position.quantity * 0.5
                
                # Close 50% of position
                result = self.api.place_order(
                    symbol=symbol,
                    side="Sell" if position.direction == "long" else "Buy",
                    order_type="Market",
                    qty=close_quantity
                )
                
                if result.get("retCode") == 0:
                    position.quantity -= close_quantity
                    position.partial_profit_taken = True
                    logger.info(f"Partial profit taken for {symbol}: closed {close_quantity:.4f} at {profit_multiple:.1f}x risk")
                    
                    # Move SL to entry + 1x risk (lock in profit)
                    if position.direction == "long":
                        new_sl = position.entry_price + (position.entry_price * self.sl_fixed_pct)
                    else:
                        new_sl = position.entry_price - (position.entry_price * self.sl_fixed_pct)
                    
                    self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                    position.stop_loss = new_sl
                    logger.info(f"Moved SL to lock in 1x risk profit for {symbol}")
                    
                    return True
                else:
                    logger.error(f"Failed to take partial profit for {symbol}: {result.get('retMsg')}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error taking partial profit for {symbol}: {e}")
            return False
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """Get all active positions"""
        return list(self.positions.values())
    
    def has_position(self, symbol: str) -> bool:
        """Check if position exists for symbol"""
        return symbol in self.positions
    
    def update_pnl(self, symbol: str, current_price: float) -> None:
        """Update PnL for position"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        if position.direction == "long":
            position.pnl = (current_price - position.entry_price) * position.quantity
        else:
            position.pnl = (position.entry_price - current_price) * position.quantity
    
    def apply_sl_tp_to_exchange(self, symbol: str, actual_entry_price: float) -> bool:
        """
        Apply SL/TP to exchange position after it's confirmed open
        
        Args:
            symbol: Trading symbol
            actual_entry_price: Actual entry price from exchange
            
        Returns:
            True if SL/TP applied successfully, False otherwise
        """
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            # Skip if already set
            if position.sl_tp_set:
                return True
            
            # Recalculate SL/TP based on actual entry price
            risk_distance = actual_entry_price * self.sl_fixed_pct
            
            if position.direction == "long":
                stop_loss = actual_entry_price - risk_distance
                take_profit = actual_entry_price + (risk_distance * 2)
            else:
                stop_loss = actual_entry_price + risk_distance
                take_profit = actual_entry_price - (risk_distance * 2)
            
            # Apply to exchange
            result = self.api.set_trading_stop(
                symbol=symbol,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if result.get("retCode") == 0:
                position.stop_loss = stop_loss
                position.take_profit = take_profit
                position.sl_tp_set = True
                logger.info(f"Applied SL/TP to {symbol}: SL={stop_loss:.2f}, TP={take_profit:.2f}")
                return True
            else:
                logger.warning(f"Failed to apply SL/TP to {symbol}: {result.get('retMsg')}")
                return False
                
        except Exception as e:
            logger.error(f"Error applying SL/TP for {symbol}: {e}")
            return False
