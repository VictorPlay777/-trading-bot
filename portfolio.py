"""
Portfolio Manager - Tracks positions, PnL, and exposure
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid

from logger import get_logger, log_event, trade_logger
from risk_manager import risk_manager
from config import trading_config, fee_config

logger = get_logger()


class PositionStatus(Enum):
    """Position status"""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class Position:
    """Active position tracking"""
    id: str
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    size: float  # Number of contracts
    notional: float  # Position value
    leverage: int
    status: PositionStatus

    # Timestamps
    opened_at: datetime
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None  # Exit price when closed

    # SL/TP
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    tp1_hit: bool = False

    # Partial exit and trailing stop tracking
    partial_exit_done: bool = False
    partial_exit_size: float = 0.0  # Size that was partially exited
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    
    # Tracking
    entry_reason: str = ""
    exit_reason: str = ""
    
    # PnL tracking
    current_pnl_gross: float = 0.0
    current_pnl_net: float = 0.0
    max_profit: float = 0.0
    max_drawdown: float = 0.0
    
    # Fees
    entry_fee: float = 0.0
    funding_fees: float = 0.0
    exit_fee: float = 0.0
    
    # Market context at entry
    regime_at_entry: str = ""
    rsi_at_entry: float = 0.0
    adx_at_entry: float = 0.0
    atr_at_entry: float = 0.0
    
    @property
    def duration_minutes(self) -> float:
        """Position duration in minutes"""
        end = self.closed_at or datetime.utcnow()
        return (end - self.opened_at).total_seconds() / 60
    
    @property
    def is_long(self) -> bool:
        return self.direction == "long"
    
    @property
    def is_short(self) -> bool:
        return self.direction == "short"
    
    def update_pnl(self, current_price: float):
        """Update current PnL with current price"""
        if self.direction == "long":
            pnl = (current_price - self.entry_price) * self.size * self.leverage
        else:
            pnl = (self.entry_price - current_price) * self.size * self.leverage
        
        # Deduct fees
        total_fees = self.entry_fee + self.funding_fees
        net_pnl = pnl - total_fees
        
        self.current_pnl_gross = pnl
        self.current_pnl_net = net_pnl
        
        # Track max profit/drawdown
        if net_pnl > self.max_profit:
            self.max_profit = net_pnl
        if net_pnl < self.max_drawdown:
            self.max_drawdown = net_pnl


class Portfolio:
    """
    Manages all positions and portfolio state:
    - Position tracking
    - PnL calculation
    - Exposure monitoring
    - Trade logging
    """
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.closed_trades: List[Position] = []
        self._account_balance: float = 0.0
        self._total_pnl_net: float = 0.0
    
    def set_account_balance(self, balance: float):
        """Update account balance"""
        self._account_balance = balance
    
    def get_account_balance(self) -> float:
        """Get current account balance"""
        return self._account_balance
    
    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        size: float,
        notional: float,
        leverage: int,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        entry_reason: str,
        regime: str,
        rsi: float,
        adx: float,
        atr: float
    ) -> Position:
        """Open a new position"""
        # Check if position already exists
        if symbol in self.positions:
            logger.warning(f"Position already exists for {symbol}, not opening new")
            return self.positions[symbol]
        
        # Check position limit
        if len(self.positions) >= trading_config.max_positions:
            logger.warning(f"Max positions ({trading_config.max_positions}) reached")
            raise ValueError("Max positions reached")
        
        # Calculate entry fee
        entry_fee = notional * leverage * fee_config.taker_fee
        
        position = Position(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            size=size,
            notional=notional,
            leverage=leverage,
            status=PositionStatus.OPEN,
            opened_at=datetime.utcnow(),
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            entry_reason=entry_reason,
            regime_at_entry=regime,
            rsi_at_entry=rsi,
            adx_at_entry=adx,
            atr_at_entry=atr,
            entry_fee=entry_fee
        )
        
        self.positions[symbol] = position
        
        log_event("info", f"Position opened: {direction} {size} {symbol} @ {entry_price}",
                  position_id=position.id,
                  symbol=symbol,
                  direction=direction,
                  entry_price=entry_price,
                  size=size,
                  leverage=leverage,
                  sl=stop_loss,
                  tp1=take_profit_1,
                  tp2=take_profit_2)
        
        return position
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str
    ) -> Optional[Position]:
        """Close a position"""
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol} to close")
            return None
        
        position = self.positions[symbol]
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.utcnow()
        position.exit_price = exit_price
        position.exit_reason = exit_reason
        
        # Calculate exit fee
        exit_notional = position.size * exit_price
        position.exit_fee = exit_notional * position.leverage * fee_config.taker_fee
        
        # Final PnL
        if position.direction == "long":
            gross_pnl = (exit_price - position.entry_price) * position.size * position.leverage
        else:
            gross_pnl = (position.entry_price - exit_price) * position.size * position.leverage
        
        total_fees = position.entry_fee + position.exit_fee + position.funding_fees
        net_pnl = gross_pnl - total_fees
        
        position.current_pnl_gross = gross_pnl
        position.current_pnl_net = net_pnl
        
        # Move to closed trades
        self.closed_trades.append(position)
        del self.positions[symbol]
        
        # Update totals
        self._total_pnl_net += net_pnl

        # Update account balance with PnL
        self._account_balance += net_pnl
        
        # Update risk manager
        was_sl = "stop" in exit_reason.lower() or "SL" in exit_reason
        risk_manager.on_trade_closed(
            net_pnl,
            position.duration_minutes,
            was_sl
        )
        
        # Log trade to CSV
        trade_logger.log_trade({
            "timestamp": position.opened_at.isoformat(),
            "trade_id": position.id,
            "symbol": position.symbol,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "size": position.size,
            "leverage": position.leverage,
            "entry_reason": position.entry_reason,
            "exit_reason": exit_reason,
            "sl_price": position.stop_loss,
            "tp_price": position.take_profit_1,
            "pnl_gross": gross_pnl,
            "entry_fee": position.entry_fee,
            "exit_fee": position.exit_fee,
            "funding_fees": position.funding_fees,
            "pnl_net": net_pnl,
            "roi_pct": (net_pnl / position.notional) * 100 if position.notional else 0,
            "regime_at_entry": position.regime_at_entry,
            "rsi_at_entry": position.rsi_at_entry,
            "adx_at_entry": position.adx_at_entry,
            "atr_at_entry": position.atr_at_entry,
            "duration_min": position.duration_minutes
        })
        
        log_event("info", f"Position closed: {exit_reason}, PnL=${net_pnl:.2f}",
                  position_id=position.id,
                  exit_price=exit_price,
                  exit_reason=exit_reason,
                  gross_pnl=gross_pnl,
                  fees=total_fees,
                  net_pnl=net_pnl,
                  duration_min=position.duration_minutes)
        
        return position
    
    def update_positions(self, current_prices: Dict[str, float]):
        """Update all positions with current prices"""
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                position.update_pnl(current_prices[symbol])
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position by symbol"""
        return self.positions.get(symbol)
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self.positions.values())
    
    def get_position_direction(self, symbol: str) -> Optional[str]:
        """Get position direction if exists"""
        pos = self.positions.get(symbol)
        return pos.direction if pos else None
    
    def get_total_exposure(self) -> float:
        """Get total notional exposure"""
        return sum(p.notional * p.leverage for p in self.positions.values())

    def get_total_notional(self) -> float:
        """Get total notional value of open positions (without leverage)"""
        return sum(p.notional for p in self.positions.values())
    
    def get_unrealized_pnl(self) -> float:
        """Get total unrealized PnL"""
        return sum(p.current_pnl_net for p in self.positions.values())
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        return {
            "account_balance": self._account_balance,
            "open_positions": len(self.positions),
            "total_exposure": self.get_total_exposure(),
            "unrealized_pnl": self.get_unrealized_pnl(),
            "total_realized_pnl": self._total_pnl_net,
            "available_margin": self._account_balance - self.get_total_exposure() / trading_config.max_leverage,
            "positions": [
                {
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "entry": p.entry_price,
                    "current_pnl": p.current_pnl_net,
                    "duration_min": p.duration_minutes
                }
                for p in self.positions.values()
            ]
        }
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history"""
        trades = self.closed_trades[-limit:]
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry": t.entry_price,
                "exit": t.exit_price or 0,
                "pnl_net": t.current_pnl_net,
                "duration_min": t.duration_minutes,
                "entry_reason": t.entry_reason,
                "exit_reason": t.exit_reason
            }
            for t in reversed(trades)
        ]


# Global portfolio instance
portfolio = Portfolio()
