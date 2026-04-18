"""
Trade Model - Position → Trade architecture
CRITICAL: Statistics calculated from TRADES (executions), not positions
"""
import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from enum import Enum
import uuid

class TradeSide(Enum):
    LONG = "long"
    SHORT = "short"

class TradeType(Enum):
    PROBE = "probe"
    MOMENTUM = "momentum"
    SCOUT = "scout"

@dataclass
class TradeLeg:
    """
    Single execution (entry OR exit)
    
    1 Position = multiple Entry legs + multiple Exit legs
    """
    leg_id: str
    trade_id: str  # Link to parent trade
    
    # Execution details
    timestamp: str
    side: str  # "entry" or "exit"
    qty: float
    price: float
    fee: float
    
    # Metadata
    order_id: Optional[str] = None
    is_partial: bool = False


@dataclass
class Trade:
    """
    Complete trade = Entry → Exit
    
    Can be:
    - Simple: 1 entry → 1 exit
    - Complex: multiple entries (pyramiding) → multiple exits (partial close)
    """
    trade_id: str  # Unique: T_YYYYMMDD_HHMMSS_uuidsuffix
    position_id: str  # Links to parent position
    
    # Trade identification
    symbol: str
    side: TradeSide  # long/short
    trade_type: TradeType  # probe/momentum/scout
    
    # Session tracking
    session_id: str
    
    # Quantities (can differ for partial closes!)
    entry_qty: float
    exit_qty: float  # May be less than entry (partial close)
    
    # Prices
    entry_price: float  # Weighted average if multiple entries
    exit_price: float   # Weighted average if multiple exits
    
    # Fees (actual from exchange!)
    entry_fee: float
    exit_fee: float
    total_fee: float
    
    # PnL
    gross_pnl: float  # Before fees
    net_pnl: float    # After fees
    pnl_pct: float    # Percentage return
    
    # Risk management
    stop_loss: float
    take_profit: float
    
    # Status
    is_win: bool
    exit_reason: str  # "tp", "sl", "manual", "liquidation", "partial"
    
    # Timing
    entry_time: str
    exit_time: str
    duration_sec: int
    
    # Legs (for audit/debug)
    entry_legs: List[TradeLeg] = field(default_factory=list)
    exit_legs: List[TradeLeg] = field(default_factory=list)
    
    # Extended metrics (populated during position tracking)
    max_profit_pct: float = 0.0   # MAE (Maximum Adverse Excursion would be negative)
    max_drawdown_pct: float = 0.0  # Worst unrealized loss during trade
    
    @property
    def is_partial_close(self) -> bool:
        """Was this a partial close?"""
        return self.exit_qty < self.entry_qty
    
    @property
    def remaining_qty(self) -> float:
        """Quantity still open (for partial closes)"""
        return self.entry_qty - self.exit_qty


@dataclass
class Position:
    """
    Position = collection of Trades
    
    Tracks:
    - All entry legs (with pyramiding)
    - All exit legs (with partial closes)
    - Current status
    """
    position_id: str  # P_YYYYMMDD_HHMMSS_uuidsuffix
    
    symbol: str
    side: TradeSide
    trade_type: TradeType
    
    session_id: str
    
    # Current state
    total_entry_qty: float = 0.0
    total_exit_qty: float = 0.0
    avg_entry_price: float = 0.0
    avg_exit_price: float = 0.0
    
    # Completed trades (closed legs)
    completed_trades: List[Trade] = field(default_factory=list)
    
    # Open entry legs (waiting for exit)
    open_entry_legs: List[TradeLeg] = field(default_factory=list)
    
    # Risk levels
    stop_loss: float = 0.0
    take_profit: float = 0.0
    
    # Status
    status: str = "open"  # open, partially_closed, closed
    
    # Timing
    open_time: str = ""
    close_time: Optional[str] = None
    
    # Metadata
    leverage: int = 1
    
    @property
    def current_qty(self) -> float:
        """Current open quantity"""
        return self.total_entry_qty - self.total_exit_qty
    
    @property
    def is_fully_closed(self) -> bool:
        """Is position completely closed?"""
        return self.current_qty <= 0.001  # Min qty threshold
    
    @property
    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized PnL at current price"""
        if self.current_qty <= 0:
            return 0.0
        
        if self.side == TradeSide.LONG:
            return (current_price - self.avg_entry_price) / self.avg_entry_price * 100
        else:
            return (self.avg_entry_price - current_price) / self.avg_entry_price * 100
    
    def add_entry(self, qty: float, price: float, fee: float, timestamp: str, order_id: Optional[str] = None) -> TradeLeg:
        """Add entry leg (pyramiding)"""
        leg = TradeLeg(
            leg_id=f"L_{uuid.uuid4().hex[:8]}",
            trade_id="",  # Will be set when matched with exit
            timestamp=timestamp,
            side="entry",
            qty=qty,
            price=price,
            fee=fee,
            order_id=order_id,
            is_partial=False
        )
        
        self.open_entry_legs.append(leg)
        
        # Recalculate average entry price
        total_value = (self.avg_entry_price * self.total_entry_qty) + (price * qty)
        self.total_entry_qty += qty
        self.avg_entry_price = total_value / self.total_entry_qty if self.total_entry_qty > 0 else 0
        
        self.status = "open"
        if not self.open_time:
            self.open_time = timestamp
        
        return leg
    
    def close_quantity(self, qty: float, exit_price: float, exit_fee: float, 
                      timestamp: str, reason: str, order_id: Optional[str] = None) -> Optional[Trade]:
        """
        Close portion of position (partial or full)
        
        Returns: Completed Trade object
        """
        if qty > self.current_qty:
            qty = self.current_qty  # Can't close more than we have
        
        if qty <= 0:
            return None
        
        # Match with earliest entry legs (FIFO)
        remaining_to_close = qty
        matched_entries: List[TradeLeg] = []
        
        while remaining_to_close > 0 and self.open_entry_legs:
            entry_leg = self.open_entry_legs[0]
            
            if entry_leg.qty <= remaining_to_close:
                # Use entire entry leg
                matched_entries.append(entry_leg)
                remaining_to_close -= entry_leg.qty
                self.open_entry_legs.pop(0)
            else:
                # Split entry leg (partial)
                partial_entry = TradeLeg(
                    leg_id=entry_leg.leg_id,
                    trade_id="",
                    timestamp=entry_leg.timestamp,
                    side="entry",
                    qty=remaining_to_close,
                    price=entry_leg.price,
                    fee=entry_leg.fee * (remaining_to_close / entry_leg.qty),  # Proportional fee
                    order_id=entry_leg.order_id,
                    is_partial=True
                )
                matched_entries.append(partial_entry)
                entry_leg.qty -= remaining_to_close
                entry_leg.fee -= partial_entry.fee
                remaining_to_close = 0
        
        # Calculate trade metrics
        entry_qty = sum(e.qty for e in matched_entries)
        entry_price = sum(e.qty * e.price for e in matched_entries) / entry_qty if entry_qty > 0 else 0
        entry_fee = sum(e.fee for e in matched_entries)
        entry_time = min(e.timestamp for e in matched_entries)
        
        # Calculate PnL
        if self.side == TradeSide.LONG:
            gross_pnl = (exit_price - entry_price) / entry_price * 100
        else:
            gross_pnl = (entry_price - exit_price) / entry_price * 100
        
        total_fee = entry_fee + exit_fee
        net_pnl = gross_pnl - (total_fee / entry_price * 100)  # Convert fee to %
        
        # Create Trade record
        trade = Trade(
            trade_id=f"T_{timestamp.replace(':', '').replace('-', '').replace(' ', '_')}_{self.symbol}_{uuid.uuid4().hex[:4]}",
            position_id=self.position_id,
            symbol=self.symbol,
            side=self.side,
            trade_type=self.trade_type,
            session_id=self.session_id,
            entry_qty=entry_qty,
            exit_qty=entry_qty,  # Same for this matched portion
            entry_price=entry_price,
            exit_price=exit_price,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            total_fee=total_fee,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            pnl_pct=net_pnl,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            is_win=net_pnl > 0,
            exit_reason=reason if not self.is_fully_closed else reason,
            entry_time=entry_time,
            exit_time=timestamp,
            duration_sec=(datetime.fromisoformat(timestamp) - datetime.fromisoformat(entry_time)).seconds,
            entry_legs=matched_entries,
            exit_legs=[TradeLeg(
                leg_id=f"L_{uuid.uuid4().hex[:8]}",
                trade_id="",
                timestamp=timestamp,
                side="exit",
                qty=qty,
                price=exit_price,
                fee=exit_fee,
                order_id=order_id,
                is_partial=self.current_qty > qty
            )]
        )
        
        # Update position state
        self.total_exit_qty += entry_qty
        self.completed_trades.append(trade)
        
        # Update status
        if self.is_fully_closed:
            self.status = "closed"
            self.close_time = timestamp
        else:
            self.status = "partially_closed"
        
        return trade


class TradeJournal:
    """
    Central trade storage
    - Append-only JSONL
    - Position → Trade mapping
    - Statistics calculated from trades (not positions!)
    """
    
    def __init__(self, journal_file: str = "trade_journal.jsonl"):
        self.journal_file = journal_file
        self.positions: Dict[str, Position] = {}  # Active positions
        self.trades: List[Trade] = []  # All completed trades
        self.load_journal()
    
    def load_journal(self):
        """Load trades from append-only journal"""
        if not os.path.exists(self.journal_file):
            return
        
        try:
            with open(self.journal_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get('type') == 'trade':
                            self.trades.append(Trade(**data['data']))
                        elif data.get('type') == 'position_update':
                            # Reconstruct position state if needed
                            pass
            print(f"[JOURNAL] Loaded {len(self.trades)} trades")
        except Exception as e:
            print(f"[JOURNAL] Error loading: {e}")
    
    def open_position(self, symbol: str, side: TradeSide, trade_type: TradeType,
                     qty: float, price: float, fee: float, timestamp: str,
                     stop_loss: float, take_profit: float, leverage: int,
                     session_id: str, order_id: Optional[str] = None) -> Position:
        """Open new position"""
        
        position = Position(
            position_id=f"P_{timestamp.replace(':', '').replace('-', '').replace(' ', '_')}_{symbol}_{uuid.uuid4().hex[:4]}",
            symbol=symbol,
            side=side,
            trade_type=trade_type,
            session_id=session_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage
        )
        
        position.add_entry(qty, price, fee, timestamp, order_id)
        
        self.positions[symbol] = position
        
        # Log position open
        self._append_to_journal({
            'type': 'position_open',
            'timestamp': timestamp,
            'data': asdict(position)
        })
        
        return position
    
    def close_position(self, symbol: str, qty: Optional[float] = None,
                      exit_price: float = 0, exit_fee: float = 0,
                      timestamp: str = '', reason: str = "",
                      order_id: Optional[str] = None) -> List[Trade]:
        """
        Close position (partial or full)
        
        Returns: List of completed Trade objects
        """
        position = self.positions.get(symbol)
        if not position:
            return []
        
        # Close all or specified quantity
        close_qty = qty if qty else position.current_qty
        
        trades = []
        while close_qty > 0 and position.current_qty > 0:
            trade = position.close_quantity(
                qty=min(close_qty, position.current_qty),
                exit_price=exit_price,
                exit_fee=exit_fee * (min(close_qty, position.current_qty) / position.total_entry_qty),
                timestamp=timestamp,
                reason=reason,
                order_id=order_id
            )
            
            if trade:
                trades.append(trade)
                self.trades.append(trade)
                
                # Append to journal
                self._append_to_journal({
                    'type': 'trade',
                    'timestamp': timestamp,
                    'data': asdict(trade)
                })
                
                close_qty -= trade.exit_qty
        
        # Remove from active if fully closed
        if position.is_fully_closed:
            del self.positions[symbol]
        
        return trades
    
    def _append_to_journal(self, record: dict):
        """Append record to journal file"""
        with open(self.journal_file, 'a') as f:
            f.write(json.dumps(record) + '\n')
    
    def get_stats(self, session_id: Optional[str] = None, 
                  symbol: Optional[str] = None) -> Dict:
        """
        Calculate statistics from TRADES (not positions!)
        """
        trades = self.trades
        
        if session_id:
            trades = [t for t in trades if t.session_id == session_id]
        
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]
        
        if not trades:
            return {}
        
        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]
        
        # Calculate equity curve
        equity = [0.0]
        for trade in trades:
            equity.append(equity[-1] + trade.net_pnl)
        
        # Calculate drawdown
        max_dd = 0.0
        peak = equity[0]
        for val in equity:
            if val > peak:
                peak = val
            dd = peak - val
            max_dd = max(max_dd, dd)
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': len(wins) / len(trades) if trades else 0,
            'gross_profit': sum(t.gross_pnl for t in wins),
            'gross_loss': sum(t.gross_pnl for t in losses),
            'net_pnl': sum(t.net_pnl for t in trades),
            'avg_win': sum(t.net_pnl for t in wins) / len(wins) if wins else 0,
            'avg_loss': sum(t.net_pnl for t in losses) / len(losses) if losses else 0,
            'profit_factor': abs(sum(t.net_pnl for t in wins) / sum(t.net_pnl for t in losses)) if losses and sum(t.net_pnl for t in losses) != 0 else float('inf'),
            'max_drawdown_pct': max_dd,
            'avg_duration_sec': sum(t.duration_sec for t in trades) / len(trades) if trades else 0,
            'partial_closes': len([t for t in trades if t.is_partial_close]),
        }


# Global instance
journal = TradeJournal()
