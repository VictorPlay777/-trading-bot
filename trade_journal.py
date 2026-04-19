"""
Trade Journal - Complete trade history with structured storage
"""
import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from enum import Enum

class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"

class TradeType(Enum):
    PROBE = "probe"
    MOMENTUM = "momentum"
    SCOUT = "scout"

@dataclass
class Trade:
    """Single complete trade record"""
    trade_id: str           # Unique ID: T_YYYYMMDD_HHMMSS_symbol
    symbol: str
    direction: str          # long/short
    trade_type: str         # probe/momentum/scout
    
    # Entry
    entry_time: str
    entry_price: float
    entry_fee: float
    position_size: float    # Quantity
    leverage: int
    
    # Exit
    exit_time: str
    exit_price: float
    exit_fee: float
    exit_reason: str        # take_profit / stop_loss / manual / liquidation
    
    # PnL
    gross_pnl: float        # Before fees
    net_pnl: float          # After fees (entry + exit)
    pnl_pct: float          # Percentage
    
    # Risk management
    stop_loss: float
    take_profit: float
    max_profit_pct: float   # Max unrealized profit (for MAE/MFE)
    max_loss_pct: float     # Max unrealized loss
    
    # Session tracking
    session_id: str
    
    @property
    def duration_seconds(self) -> int:
        """Trade duration"""
        try:
            entry = datetime.fromisoformat(self.entry_time)
            exit = datetime.fromisoformat(self.exit_time)
            return int((exit - entry).total_seconds())
        except:
            return 0
    
    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class TradeJournal:
    """
    Central trade storage with:
    - Append-only journal (никогда не перезаписывается)
    - Unique trade IDs
    - Query by date, symbol, type
    - Equity curve calculation
    """
    
    def __init__(self, journal_file: str = "trade_journal.jsonl"):
        self.journal_file = journal_file
        self.trades: List[Trade] = []
        self.load_journal()
    
    def load_journal(self):
        """Load all trades from append-only journal"""
        if os.path.exists(self.journal_file):
            try:
                with open(self.journal_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            self.trades.append(Trade(**data))
                print(f"[JOURNAL] Loaded {len(self.trades)} trades")
            except Exception as e:
                print(f"[JOURNAL] Error loading: {e}")
    
    def record_trade(self, trade: Trade):
        """Append trade to journal (NEVER overwrites)"""
        # Check for duplicates
        if any(t.trade_id == trade.trade_id for t in self.trades):
            print(f"[JOURNAL] Duplicate trade {trade.trade_id} ignored")
            return
        
        self.trades.append(trade)
        
        # Append to file (line-delimited JSON)
        with open(self.journal_file, 'a') as f:
            f.write(json.dumps(trade.to_dict()) + '\n')
        
        print(f"[JOURNAL] Recorded trade {trade.trade_id}: {trade.symbol} {trade.net_pnl:.2f}%")
    
    def get_session_trades(self, session_id: str) -> List[Trade]:
        """Get all trades for specific session"""
        return [t for t in self.trades if t.session_id == session_id]
    
    def get_symbol_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """Get recent trades for symbol"""
        symbol_trades = [t for t in self.trades if t.symbol == symbol]
        return symbol_trades[-limit:]
    
    def calculate_equity_curve(self, session_id: Optional[str] = None) -> List[float]:
        """Calculate equity curve (cumulative PnL)"""
        trades = self.get_session_trades(session_id) if session_id else self.trades
        equity = [0.0]
        for trade in trades:
            equity.append(equity[-1] + trade.net_pnl)
        return equity
    
    def calculate_drawdown(self, equity: List[float]) -> Dict:
        """Calculate max drawdown and duration"""
        peak = equity[0]
        max_dd = 0.0
        dd_start = 0
        max_dd_duration = 0
        
        for i, value in enumerate(equity):
            if value > peak:
                peak = value
                dd_duration = i - dd_start
                max_dd_duration = max(max_dd_duration, dd_duration)
                dd_start = i
            else:
                dd = (peak - value) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
        
        return {
            'max_drawdown_pct': max_dd,
            'max_dd_duration_bars': max_dd_duration
        }
    
    def get_stats(self, session_id: Optional[str] = None) -> Dict:
        """Calculate complete statistics"""
        trades = self.get_session_trades(session_id) if session_id else self.trades
        
        if not trades:
            return {}
        
        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]
        
        equity = self.calculate_equity_curve(session_id)
        drawdown = self.calculate_drawdown(equity)
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': len(wins) / len(trades) if trades else 0,
            'avg_win': sum(t.net_pnl for t in wins) / len(wins) if wins else 0,
            'avg_loss': sum(t.net_pnl for t in losses) / len(losses) if losses else 0,
            'total_pnl': sum(t.net_pnl for t in trades),
            'profit_factor': abs(sum(t.net_pnl for t in wins) / sum(t.net_pnl for t in losses)) if losses and sum(t.net_pnl for t in losses) != 0 else float('inf'),
            'max_drawdown': drawdown['max_drawdown_pct'],
            'avg_trade_duration': sum(t.duration_seconds for t in trades) / len(trades) if trades else 0,
            'best_trade': max(trades, key=lambda t: t.net_pnl).net_pnl if trades else 0,
            'worst_trade': min(trades, key=lambda t: t.net_pnl).net_pnl if trades else 0,
        }


# Global instance
trade_journal = TradeJournal()


def record_position_closed(
    symbol: str,
    direction: str,
    trade_type: str,
    entry_price: float,
    exit_price: float,
    entry_time: str,
    exit_time: str,
    quantity: float,
    leverage: int,
    fees: float,
    stop_loss: float,
    take_profit: float,
    exit_reason: str,
    session_id: str
):
    """Convenience function to record a closed position"""
    
    # Calculate PnL
    if direction == "long":
        gross_pnl = (exit_price - entry_price) / entry_price * 100
    else:
        gross_pnl = (entry_price - exit_price) / entry_price * 100
    
    net_pnl = gross_pnl - fees
    
    # Generate trade ID
    trade_id = f"T_{exit_time.replace(':', '').replace('-', '').replace(' ', '_')}_{symbol}"
    
    trade = Trade(
        trade_id=trade_id,
        symbol=symbol,
        direction=direction,
        trade_type=trade_type,
        entry_time=entry_time,
        entry_price=entry_price,
        entry_fee=fees / 2,  # Approximate
        position_size=quantity,
        leverage=leverage,
        exit_time=exit_time,
        exit_price=exit_price,
        exit_fee=fees / 2,  # Approximate
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        pnl_pct=net_pnl,
        stop_loss=stop_loss,
        take_profit=take_profit,
        max_profit_pct=0,  # Would need to track during position
        max_loss_pct=0,    # Would need to track during position
        session_id=session_id
    )
    
    trade_journal.record_trade(trade)
    return trade


if __name__ == "__main__":
    # Test
    journal = TradeJournal()
    
    # Example trade
    trade = Trade(
        trade_id="T_20260418_143022_BTCUSDT",
        symbol="BTCUSDT",
        direction="long",
        trade_type="momentum",
        entry_time="2026-04-18T14:00:00",
        entry_price=65000.0,
        entry_fee=0.055,
        position_size=0.1,
        leverage=10,
        exit_time="2026-04-18T14:30:00",
        exit_price=65500.0,
        exit_fee=0.055,
        exit_reason="take_profit",
        gross_pnl=0.77,
        net_pnl=0.66,
        pnl_pct=0.66,
        stop_loss=64000.0,
        take_profit=66000.0,
        max_profit_pct=0.9,
        max_loss_pct=-0.2,
        session_id="20260418_143000"
    )
    
    journal.record_trade(trade)
    print(journal.get_stats())
