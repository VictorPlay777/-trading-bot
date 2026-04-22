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

from symbol_analytics import get_analytics

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
    
    def __init__(self, config, api_client, bot_config: dict = None):
        self.cfg = config
        self.api = api_client
        self.bot_config = bot_config or {}  # Bot-specific config
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        
        # Get genius/trend features from config
        genius_cfg = bot_config.get('genius_features', {}) if bot_config else {}
        trend_cfg = bot_config.get('trend_yolo_features', {}) if bot_config else {}
        self.skip_analytics_filter = genius_cfg.get('skip_analytics_filter', False) or trend_cfg.get('skip_analytics_filter', False)
        
        # Get max_positions from bot_config or fallback to global
        if bot_config and 'strategy' in bot_config:
            self.max_positions = bot_config['strategy'].get('max_positions', 20)
        else:
            self.max_positions = 20  # Default
        
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
            
            # Check max positions limit
            if len(self.positions) >= self.max_positions:
                logger.warning(f"Max positions ({self.max_positions}) reached, cannot open new position for {symbol}")
                return False
            
            # Get instrument info for qty_step, min_qty, and price filters
            instrument_info = self.api.get_instrument_info(symbol)
            qty_step = float(instrument_info.get("lotSizeFilter", {}).get("qtyStep", 0.001))
            min_qty = float(instrument_info.get("lotSizeFilter", {}).get("minOrderQty", 0.001))
            tick_size = float(instrument_info.get("priceFilter", {}).get("tickSize", 0.01))
            
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
            
            # [ADAPTIVE POSITION SIZING] Apply multiplier based on symbol performance
            analytics = get_analytics()
            size_multiplier = analytics.get_position_size_multiplier(symbol)
            position_size = position_size * size_multiplier
            
            # Log the multiplier for transparency
            if size_multiplier != 1.0:
                logger.info(f"[ADAPTIVE SIZE] {symbol}: multiplier={size_multiplier:.1f}x, base=${position_size/size_multiplier:.2f}, final=${position_size:.2f}")
            
            # Check if symbol should be traded at all (for non-Genius bots)
            # Genius bot uses risk adjustment instead of blocking
            if not self.skip_analytics_filter and not analytics.should_trade_symbol(symbol):
                logger.warning(f"[FILTER] {symbol} blocked by analytics - poor performance detected")
                return False
            
            # Calculate quantity
            quantity = position_size / entry_price
            
            # Check against max_qty BEFORE rounding to prevent Qty invalid errors
            max_qty = float(instrument_info.get("lotSizeFilter", {}).get("maxOrderQty", 999999))
            if quantity > max_qty:
                # Use 90% of max_qty to be safe
                quantity = max_qty * 0.9
                logger.warning(f"[QTY LIMIT] {symbol}: quantity {position_size/entry_price:.4f} exceeds max_qty {max_qty}, using {quantity:.4f}")
            
            # Round quantity to qty_step precision with better precision handling
            quantity = round(quantity / qty_step) * qty_step
            quantity = round(quantity, 8)  # Round to 8 decimal places to avoid floating point issues
            
            # Final check against min_qty after rounding
            min_qty = float(instrument_info.get("lotSizeFilter", {}).get("minOrderQty", 0.001))
            if quantity < min_qty:
                quantity = min_qty
                logger.warning(f"[MIN QTY] {symbol}: rounded quantity too low, using min_qty {min_qty}")
            
            # Ensure quantity meets minimum order requirement
            if quantity < min_qty:
                quantity = min_qty
            
            # Log the final quantity for debugging
            logger.debug(f"Calculated quantity: {quantity}, qty_step: {qty_step}, min_qty: {min_qty}")
            
            logger.info(f"Position size: ${position_size:.2f}, Quantity: {quantity} BTC, Entry: ${entry_price:.2f}")
            
            # Get current market price for SL/TP calculation
            current_price = self.api.get_latest_price(symbol)
            if current_price <= 0:
                current_price = entry_price
                logger.warning(f"Using entry price as fallback for SL/TP calculation: {current_price}")
            
            # [DYNAMIC R:R] Calculate SL/TP based on symbol performance
            analytics = get_analytics()
            risk_reward = analytics.get_risk_reward_ratio(symbol)
            
            sl_pct = 0.02  # Base 2% stop loss
            tp_pct = sl_pct * risk_reward  # TP based on R:R
            
            logger.info(f"[DYNAMIC R:R] {symbol}: Risk/Reward = 1:{risk_reward:.1f}, SL={sl_pct*100:.1f}%, TP={tp_pct*100:.1f}%")
            
            if direction == "long":
                stop_loss = current_price * (1 - sl_pct)   # 2% below current price
                take_profit = current_price * (1 + tp_pct)  # 4% above current price
            else:
                stop_loss = current_price * (1 + sl_pct)   # 2% above current price
                take_profit = current_price * (1 - tp_pct)  # 4% below current price
            
            # Round SL/TP to tick size
            stop_loss = round(stop_loss / tick_size) * tick_size
            take_profit = round(take_profit / tick_size) * tick_size
            
            # Validate SL/TP logic before sending
            if direction == "long":
                if stop_loss >= current_price:
                    logger.error(f"Invalid SL for long: SL {stop_loss} >= price {current_price}")
                    stop_loss = current_price * 0.98  # Force 2% below
                if take_profit <= current_price:
                    logger.error(f"Invalid TP for long: TP {take_profit} <= price {current_price}")
                    take_profit = current_price * 1.04  # Force 4% above
            else:  # short
                if stop_loss <= current_price:
                    logger.error(f"Invalid SL for short: SL {stop_loss} <= price {current_price}")
                    stop_loss = current_price * 1.02  # Force 2% above
                if take_profit >= current_price:
                    logger.error(f"Invalid TP for short: TP {take_profit} >= price {current_price}")
                    take_profit = current_price * 0.96  # Force 4% below
            
            logger.info(f"SL/TP calculated for {symbol}: SL={stop_loss:.4f}, TP={take_profit:.4f}, Current={current_price:.4f}")
            
            # Strategy: Open ONLY if SL/TP can be set immediately
            result = self.api.place_order(
                symbol=symbol,
                side="Buy" if direction == "long" else "Sell",
                order_type="Market",
                qty=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # Check result
            ret_msg = str(result.get('retMsg', ''))
            
            if result.get("retCode") != 0:
                # Check if SL/TP specific error
                sl_tp_error = any(err in ret_msg for err in [
                    'StopLoss', 'TakeProfit', 'base_price', 'can not set tp/sl', 'sl/ts'
                ])
                
                if sl_tp_error:
                    logger.error(f" SL/TP rejected for {symbol}: {ret_msg}. SAFETY FIRST - closing position!")
                    # Market order may have executed - close position immediately
                    try:
                        close_side = "Sell" if direction == "long" else "Buy"
                        self.api.place_order(
                            symbol=symbol,
                            side=close_side,
                            order_type="Market",
                            qty=quantity,
                            reduce_only=True
                        )
                        logger.info(f"Closed {symbol} immediately due to SL/TP rejection")
                    except Exception as e:
                        logger.error(f"Failed to close {symbol} after SL/TP rejection: {e}")
                else:
                    logger.error(f"Failed to open position for {symbol}: {ret_msg}")
                return False
            
            # Get actual entry price from executed order (handle slippage)
            try:
                order_data = result.get("result", {})
                actual_entry_price = None
                
                if "avgPrice" in order_data and order_data["avgPrice"]:
                    actual_entry_price = float(order_data["avgPrice"])
                elif "cumExecValue" in order_data and "cumExecQty" in order_data:
                    exec_qty = float(order_data.get("cumExecQty", 0))
                    exec_value = float(order_data.get("cumExecValue", 0))
                    if exec_qty > 0:
                        actual_entry_price = exec_value / exec_qty
                
                if not actual_entry_price or actual_entry_price <= 0:
                    actual_entry_price = entry_price
                    logger.warning(f"Using estimated entry price for {symbol}: {actual_entry_price}")
                else:
                    slippage_pct = abs(actual_entry_price - entry_price) / entry_price * 100
                    if slippage_pct > 0.1:
                        logger.warning(f"Slippage detected for {symbol}: {slippage_pct:.2f}% (expected {entry_price:.4f}, got {actual_entry_price:.4f})")
                
            except Exception as e:
                logger.warning(f"Could not get actual entry price for {symbol}: {e}, using estimated: {entry_price}")
                actual_entry_price = entry_price
            
            # SL/TP already set in the order - use the same values for tracking
            # Log slippage between expected and actual entry price
            slippage_pct = abs(actual_entry_price - current_price) / current_price * 100 if current_price > 0 else 0
            if slippage_pct > 0.5:
                logger.warning(f"High slippage for {symbol}: {slippage_pct:.2f}% (expected {current_price:.4f}, got {actual_entry_price:.4f})")
            
            # Create position object - SL/TP already set via API
            position = Position(
                symbol=symbol,
                direction=direction,
                entry_price=actual_entry_price,
                quantity=quantity,
                trade_type=trade_type,
                leverage=leverage,
                stop_loss=stop_loss,  # Same as sent to API
                take_profit=take_profit,  # Same as sent to API
                trailing_stop=None,
                entry_time=datetime.utcnow(),
                pyramiding_level=0,
                status="open",
                sl_tp_set=True  # SL/TP already set in place_order
            )
            
            self.positions[symbol] = position
            logger.info(f"Opened {trade_type.value} position: {direction} {quantity:.4f} {symbol} @ {actual_entry_price:.2f} (SL: {stop_loss:.4f}, TP: {take_profit:.4f})")
            
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
            
            # Check if position actually exists on exchange (avoid "position is zero" error)
            try:
                exchange_position = self.api.check_position_state(symbol)
                if not exchange_position or exchange_position.get("size", 0) == 0:
                    logger.warning(f"Position {symbol} already closed on exchange, removing from tracking")
                    del self.positions[symbol]
                    return True
            except Exception as e:
                logger.debug(f"Could not verify position state for {symbol}: {e}")
            
            # Get instrument info for proper quantity formatting
            instrument = self.api.get_instrument_info(symbol)
            lot_size_filter = instrument.get("lotSizeFilter", {})
            qty_step = float(lot_size_filter.get("qtyStep", 0.001))
            
            # Round quantity to qty_step precision
            close_quantity = round(position.quantity / qty_step) * qty_step
            close_quantity = round(close_quantity, 8)
            
            # Ensure minimum quantity
            min_qty = float(lot_size_filter.get("minOrderQty", 0.001))
            if close_quantity < min_qty:
                logger.warning(f"Close quantity {close_quantity} below minimum {min_qty} for {symbol}")
                close_quantity = min_qty
            
            # Get current position from exchange to verify direction
            try:
                current_pos = self.api.get_position(symbol)
                current_qty = float(current_pos.get("size", 0))
                if abs(current_qty) < min_qty:
                    logger.warning(f"Position {symbol} already closed (size={current_qty}), removing from tracking")
                    del self.positions[symbol]
                    return True
                # Determine correct close side based on actual position
                actual_direction = "long" if current_qty > 0 else "short"
                close_side = "Sell" if actual_direction == "long" else "Buy"
            except Exception as e:
                logger.warning(f"Could not get current position for {symbol}, using tracked direction: {e}")
                close_side = "Sell" if position.direction == "long" else "Buy"
            
            # Place closing order with reduceOnly to ensure we only close, not open new position
            result = self.api.place_order(
                symbol=symbol,
                side=close_side,
                order_type="Market",
                qty=close_quantity,
                reduce_only=True  # Bybit API: only reduce position, don't open new
            )
            
            if result.get("retCode") != 0:
                # If position already closed, just remove from tracking
                if "current position is zero" in str(result.get('retMsg', '')):
                    logger.warning(f"Position {symbol} already closed on exchange (zero position)")
                    del self.positions[symbol]
                    return True
                logger.error(f"Failed to close position for {symbol}: {result.get('retMsg')}")
                return False
            
            # Calculate PnL
            try:
                # Get actual exit price from order result or use current market price
                exit_price = float(result.get('result', {}).get('avgPrice', current_price if 'current_price' in locals() else position.entry_price))
                
                if position.direction == "long":
                    pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
                else:
                    pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
                
                # Estimate fees (0.055% entry + 0.055% exit)
                fees_pct = 0.11
                net_pnl = pnl_pct - fees_pct
                
                is_win = net_pnl > 0
                
                # Record in analytics
                analytics = get_analytics()
                analytics.record_trade(
                    symbol=symbol,
                    pnl=pnl_pct,
                    is_win=is_win,
                    fees=fees_pct
                )
                
                logger.info(f"Recorded trade: {symbol} {position.direction}, PnL: {net_pnl:.2f}% ({'WIN' if is_win else 'LOSS'}), Entry: {position.entry_price:.4f}, Exit: {exit_price:.4f}")
                
                # Log win/loss streaks
                stats = analytics.stats.get(symbol)
                if stats:
                    if stats.consecutive_wins >= 3:
                        logger.info(f"🔥 {symbol}: {stats.consecutive_wins} consecutive wins!")
                    elif stats.consecutive_losses >= 3:
                        logger.warning(f"❄️ {symbol}: {stats.consecutive_losses} consecutive losses, cooling off")
                
            except Exception as e:
                logger.error(f"Error recording trade stats for {symbol}: {e}")
            
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
            
            # [SMART PYRAMIDING] Check if position is profitable enough
            if position.direction == "long":
                profit_pct = (current_price - position.entry_price) / position.entry_price
            else:
                profit_pct = (position.entry_price - current_price) / position.entry_price
            
            # Require minimum 0.5% profit before pyramiding (was: >0)
            min_profit_for_pyramid = 0.005  # 0.5%
            if profit_pct < min_profit_for_pyramid:
                logger.debug(f"[SMART PYRAMID] {symbol}: Profit {profit_pct*100:.2f}% < {min_profit_for_pyramid*100:.1f}%, skipping")
                return False
            
            # Check symbol analytics - only pyramid if symbol is performing well
            analytics = get_analytics()
            stats = analytics.stats.get(symbol)
            if stats and stats.consecutive_losses >= 2:
                logger.warning(f"[SMART PYRAMID] {symbol}: {stats.consecutive_losses} consecutive losses, no pyramiding")
                return False
            
            # Reduce max levels from 3 to 2
            if position.pyramiding_level >= 2:  # Changed from 3 to 2
                logger.warning(f"Max pyramiding level reached for {symbol}")
                return False
            
            # Log pyramiding decision
            logger.info(f"[SMART PYRAMID] {symbol}: Adding to winner with {profit_pct*100:.2f}% profit")
            
            # Calculate addition size
            multiplier = self.pyramiding_multipliers[position.pyramiding_level]
            additional_quantity = position.quantity * (multiplier - 1)
            
            # Check if would exceed max position size
            new_total_notional = (position.quantity + additional_quantity) * current_price
            if new_total_notional > max_position_size:
                logger.warning(f"Pyramiding would exceed max position size for {symbol}")
                return False
            
            # Get instrument info for proper quantity formatting
            instrument = self.api.get_instrument_info(symbol)
            lot_size_filter = instrument.get("lotSizeFilter", {})
            qty_step = float(lot_size_filter.get("qtyStep", 0.001))
            min_qty = float(lot_size_filter.get("minOrderQty", 0.001))
            
            # Round quantity to qty_step precision
            additional_quantity = round(additional_quantity / qty_step) * qty_step
            additional_quantity = round(additional_quantity, 8)
            
            # Ensure minimum quantity
            if additional_quantity < min_qty:
                logger.warning(f"Pyramid quantity {additional_quantity} below minimum {min_qty} for {symbol}")
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
        CENTRALIZED trailing stop update with strict safety checks.
        This is the ONLY function that should update trailing stops.
        
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
            previous_sl = position.trailing_stop or position.stop_loss
            
            # Calculate profit
            if position.direction == "long":
                profit_pct = (current_price - position.entry_price) / position.entry_price
            else:
                profit_pct = (position.entry_price - current_price) / position.entry_price
            
            # Check if profit threshold reached
            if profit_pct < self.trailing_stop_activation_pct:
                return False
            
            # Calculate new trailing stop with strict rules
            if position.direction == "long":
                # For LONG: SL MUST be BELOW current price
                new_trailing_stop = current_price * (1 - self.trailing_stop_distance_pct)
                
                # SAFETY: Force valid SL if calculated wrong
                if new_trailing_stop >= current_price:
                    new_trailing_stop = current_price * 0.995  # 0.5% below current
                    logger.warning(f"[SAFETY] Forced SL below current for {symbol}: {new_trailing_stop:.4f} < {current_price:.4f}")
                
                # Minimum trailing distance: 0.2% from current price
                min_sl_distance = current_price * 0.002
                min_sl = current_price - min_sl_distance
                if new_trailing_stop > min_sl:
                    new_trailing_stop = min_sl
                    logger.debug(f"[MIN DISTANCE] Adjusted SL to maintain 0.2% distance for {symbol}")
                
                # Rate-limit: Skip if change is too small (<0.1%)
                if previous_sl is not None:
                    change_pct = (new_trailing_stop - previous_sl) / previous_sl
                    if 0 < change_pct < 0.001:
                        logger.debug(f"[RATE LIMIT] {symbol}: SL change {change_pct*100:.3f}% too small, skipping")
                        return False
                
                # Rule: SL can only go UP (never decrease for LONG)
                if previous_sl is not None and new_trailing_stop <= previous_sl:
                    logger.debug(f"[SL SKIP] {symbol}: LONG SL would decrease from {previous_sl:.4f} to {new_trailing_stop:.4f}, skipping")
                    return False
                    
            else:
                # For SHORT: SL MUST be ABOVE current price
                new_trailing_stop = current_price * (1 + self.trailing_stop_distance_pct)
                
                # SAFETY: Force valid SL if calculated wrong
                if new_trailing_stop <= current_price:
                    new_trailing_stop = current_price * 1.005  # 0.5% above current
                    logger.warning(f"[SAFETY] Forced SL above current for {symbol}: {new_trailing_stop:.4f} > {current_price:.4f}")
                
                # Minimum trailing distance: 0.2% from current price
                min_sl_distance = current_price * 0.002
                min_sl = current_price + min_sl_distance
                if new_trailing_stop < min_sl:
                    new_trailing_stop = min_sl
                    logger.debug(f"[MIN DISTANCE] Adjusted SL to maintain 0.2% distance for {symbol}")
                
                # Rate-limit: Skip if change is too small (<0.1%)
                if previous_sl is not None:
                    change_pct = abs(new_trailing_stop - previous_sl) / previous_sl
                    if change_pct < 0.001:
                        logger.debug(f"[RATE LIMIT] {symbol}: SL change {change_pct*100:.3f}% too small, skipping")
                        return False
                
                # Rule: SL can only go DOWN (never increase for SHORT)
                if previous_sl is not None and new_trailing_stop >= previous_sl:
                    logger.debug(f"[SL SKIP] {symbol}: SHORT SL would increase from {previous_sl:.4f} to {new_trailing_stop:.4f}, skipping")
                    return False
            
            # Log every SL update with full details (safe formatting)
            prev_sl_str = f"{previous_sl:.4f}" if previous_sl is not None else "N/A"
            logger.info(f"[SL UPDATE] {symbol} | Side: {position.direction.upper()} | "
                       f"Current: ${current_price:.4f} | New SL: ${new_trailing_stop:.4f} | "
                       f"Previous SL: ${prev_sl_str} | Profit: {profit_pct*100:.2f}%")
            
            # Update via API
            result = self.api.set_trading_stop(
                symbol=symbol,
                stop_loss=new_trailing_stop
            )
            
            if result.get("retCode") == 0:
                position.trailing_stop = new_trailing_stop
                position.stop_loss = new_trailing_stop
                logger.info(f"[SL SUCCESS] Updated trailing stop for {symbol}: ${new_trailing_stop:.4f}")
                return True
            else:
                error_msg = result.get('retMsg', 'Unknown error')
                logger.error(f"[SL FAILED] {symbol}: {error_msg} | "
                           f"Tried to set {position.direction} SL at ${new_trailing_stop:.4f} "
                           f"with current price ${current_price:.4f}")
                return False
            
        except Exception as e:
            logger.error(f"[SL ERROR] Exception updating trailing stop for {symbol}: {e}")
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
        Smart stop management with breakeven logic ONLY.
        Trailing stop logic is CENTRALIZED in update_trailing_stop().
        
        Strategy:
        - After 1x risk profit: Move SL to breakeven (entry price)
        - Trailing stop is handled separately by update_trailing_stop()
        - After 3x risk profit: Take partial profit (50%)
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            atr: Current ATR value (not used for breakeven, kept for API compatibility)
            
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
                    # Validate: breakeven SL must be below current price for LONG
                    if new_sl >= current_price:
                        logger.warning(f"[BREAKEVEN SKIP] {symbol}: Cannot set breakeven ${new_sl:.4f} >= current ${current_price:.4f}")
                    else:
                        sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                        if sl_result.get("retCode") == 0:
                            position.stop_loss = new_sl
                            logger.info(f"[BREAKEVEN] Moved SL to breakeven for {symbol} at ${new_sl:.4f}")
                            action_taken = True
                        else:
                            logger.error(f"[BREAKEVEN FAILED] {symbol}: {sl_result.get('retMsg')}")
                            
                elif position.direction == "short" and position.stop_loss > position.entry_price:
                    new_sl = position.entry_price
                    # Validate: breakeven SL must be above current price for SHORT
                    if new_sl <= current_price:
                        logger.warning(f"[BREAKEVEN SKIP] {symbol}: Cannot set breakeven ${new_sl:.4f} <= current ${current_price:.4f}")
                    else:
                        sl_result = self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                        if sl_result.get("retCode") == 0:
                            position.stop_loss = new_sl
                            logger.info(f"[BREAKEVEN] Moved SL to breakeven for {symbol} at ${new_sl:.4f}")
                            action_taken = True
                        else:
                            logger.error(f"[BREAKEVEN FAILED] {symbol}: {sl_result.get('retMsg')}")
            
            # Stage 2: Trailing stop is handled by update_trailing_stop() - DO NOT duplicate here
            # The engine calls update_trailing_stop separately after manage_smart_stops
            
            # Stage 3: Take partial profit at 3x risk
            if profit_multiple >= 3.0:
                action_taken = self._take_partial_profit_stage(symbol, current_price, profit_multiple) or action_taken
            
            return action_taken
            
        except Exception as e:
            logger.error(f"[SMART STOP ERROR] {symbol}: {e}")
            return False
    
    def _take_partial_profit_stage(self, symbol: str, current_price: float, profit_multiple: float) -> bool:
        """Separate method for partial profit to keep code clean"""
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            if getattr(position, 'partial_profit_taken', False):
                return False
            
            close_quantity = position.quantity * 0.5
            
            result = self.api.place_order(
                symbol=symbol,
                side="Sell" if position.direction == "long" else "Buy",
                order_type="Market",
                qty=close_quantity
            )
            
            if result.get("retCode") == 0:
                position.quantity -= close_quantity
                position.partial_profit_taken = True
                logger.info(f"[PARTIAL PROFIT] {symbol}: Closed {close_quantity:.4f} at {profit_multiple:.1f}x risk")
                
                # Move SL to lock in profit (1x risk from entry)
                if position.direction == "long":
                    new_sl = position.entry_price - (position.entry_price * self.sl_fixed_pct)
                    # Ensure valid SL
                    if new_sl >= current_price:
                        new_sl = current_price * 0.99  # 1% below current
                else:
                    new_sl = position.entry_price + (position.entry_price * self.sl_fixed_pct)
                    # Ensure valid SL
                    if new_sl <= current_price:
                        new_sl = current_price * 1.01  # 1% above current
                
                self.api.set_trading_stop(symbol=symbol, stop_loss=new_sl)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[PARTIAL PROFIT ERROR] {symbol}: {e}")
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
                        new_sl = position.entry_price - (position.entry_price * self.sl_fixed_pct)
                    else:
                        new_sl = position.entry_price + (position.entry_price * self.sl_fixed_pct)
                    
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
        Apply SL/TP to exchange position using setTradingStop with validation and retry
        """
        try:
            if symbol not in self.positions:
                return False
            
            position = self.positions[symbol]
            
            # Skip if already set
            if position.sl_tp_set:
                return True
            
            # CRITICAL: Check if position actually exists on exchange
            try:
                exchange_pos = self.api.get_position(symbol)
                current_size = float(exchange_pos.get("size", 0))
                if abs(current_size) < 0.0001:  # Use small threshold to handle floating point
                    logger.warning(f"Cannot apply SL/TP to {symbol}: position is zero or closed (size={current_size})")
                    # Mark as set to avoid repeated attempts
                    position.sl_tp_set = True
                    del self.positions[symbol]  # Remove from tracking
                    return False
            except Exception as e:
                logger.debug(f"Could not verify position state for {symbol}: {e}")
                # If we can't verify, try anyway but mark as set to avoid loops
                position.sl_tp_set = True
            
            # Validate entry price
            if not actual_entry_price or actual_entry_price <= 0:
                actual_entry_price = position.entry_price
            
            # Recalculate SL/TP based on actual entry price
            risk_distance = actual_entry_price * self.sl_fixed_pct
            
            if position.direction == "long":
                stop_loss = actual_entry_price - risk_distance
                take_profit = actual_entry_price + (risk_distance * 2)
                if stop_loss >= actual_entry_price:
                    logger.error(f"Invalid SL for long {symbol}: SL={stop_loss:.4f} >= entry={actual_entry_price:.4f}")
                    return False
            else:
                stop_loss = actual_entry_price + risk_distance
                take_profit = actual_entry_price - (risk_distance * 2)
                if stop_loss <= actual_entry_price:
                    logger.error(f"Invalid SL for short {symbol}: SL={stop_loss:.4f} <= entry={actual_entry_price:.4f}")
                    return False
            
            # Apply with retry
            for attempt in range(3):
                try:
                    result = self.api.set_trading_stop(
                        symbol=symbol,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    
                    if result.get("retCode") == 0:
                        position.stop_loss = stop_loss
                        position.take_profit = take_profit
                        position.sl_tp_set = True
                        logger.info(f"✅ SL/TP applied to {symbol}: SL={stop_loss:.4f}, TP={take_profit:.4f}")
                        return True
                    
                    error_msg = str(result.get('retMsg', ''))
                    if 'zero position' in error_msg.lower():
                        logger.warning(f"Position {symbol} closed, skipping SL/TP")
                        position.sl_tp_set = True  # Mark to avoid retries
                        return False
                    
                    logger.warning(f"Attempt {attempt+1}/3 failed for {symbol}: {error_msg}")
                    if attempt < 2:
                        time.sleep(0.5)
                        
                except Exception as e:
                    logger.warning(f"Attempt {attempt+1}/3 error for {symbol}: {e}")
                    if attempt < 2:
                        time.sleep(0.5)
            
            logger.error(f"Failed to apply SL/TP to {symbol} after 3 attempts")
            return False
                
        except Exception as e:
            logger.error(f"Error applying SL/TP for {symbol}: {e}")
            return False
