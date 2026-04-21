"""
Learning Module - Adaptive signal weights based on trade statistics
"""
import logging
import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Signal types for learning"""
    EMA = "ema"
    RSI = "rsi"
    VOLUME = "volume"
    ATR = "atr"
    MOMENTUM = "momentum"


@dataclass
class TradeRecord:
    """Trade record for learning"""
    symbol: str
    trade_type: str  # "probe", "scout", "momentum"
    direction: str  # "long" or "short"
    signals_used: List[str]  # List of signal types used
    signal_weights: Dict[str, float]  # Weights at time of trade
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    duration_seconds: int


class LearningModule:
    """
    Adaptive learning system that adjusts signal weights based on trade results
    
    Stores:
    - Trade type (probe/scout/momentum)
    - Signals used
    - Result (PnL)
    - Symbol
    
    Signal weights:
    - EMA, RSI, Volume, ATR, Momentum
    - Initial = 1.0
    
    Updates:
    - Profit -> increase weights of used signals
    - Loss -> decrease weights of used signals
    
    Adaptation:
    - Strengthen working signals
    - Weaken failing signals
    - Adjust allocation by symbol
    """
    
    def __init__(self, config):
        self.cfg = config
        self.signal_weights: Dict[str, float] = {
            SignalType.EMA.value: 1.0,
            SignalType.RSI.value: 1.0,
            SignalType.VOLUME.value: 1.0,
            SignalType.ATR.value: 1.0,
            SignalType.MOMENTUM.value: 1.0
        }
        
        # Symbol performance tracking
        self.symbol_performance: Dict[str, Dict] = {}
        
        # Trade history - increased to 1000 for better analysis
        self.trade_history: List[TradeRecord] = []
        self.max_history_size = 1000  # Keep last 1000 trades instead of 100
        
        # Symbol risk adjustment - reduce position size for poor performers instead of blocking
        self.symbol_risk_multiplier: Dict[str, float] = {}  # symbol -> position size multiplier
        self.min_win_rate_for_full_size = 0.40  # Full position size at 40%+ win rate
        self.min_win_rate_for_reduced = 0.25  # Reduced position size below 25% win rate
        self.risk_adjustment_min_trades = 8  # Need at least 8 trades before adjustment
        
        # Learning parameters
        self.learning_rate = 0.1  # How much to adjust weights
        self.min_weight = 0.1  # Minimum weight
        self.max_weight = 2.0  # Maximum weight
        self.history_file = "learning_history.json"
        
        # Load previous learning data
        self._load_learning_data()
    
    def record_trade(
        self,
        symbol: str,
        trade_type: str,
        direction: str,
        signals_used: List[str],
        entry_price: float,
        exit_price: float,
        entry_time: datetime,
        exit_time: datetime
    ) -> None:
        """
        Record a trade for learning
        
        Args:
            symbol: Trading symbol
            trade_type: Type of trade (probe/scout/momentum)
            direction: Trade direction (long/short)
            signals_used: List of signal types used
            entry_price: Entry price
            exit_price: Exit price
            entry_time: Entry time
            exit_time: Exit time
        """
        try:
            # Calculate PnL
            if direction == "long":
                pnl = (exit_price - entry_price) * 100  # Simplified (should use quantity)
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl = (entry_price - exit_price) * 100
                pnl_pct = (entry_price - exit_price) / entry_price
            
            # Calculate duration
            duration_seconds = int((exit_time - entry_time).total_seconds())
            
            # Get current signal weights
            signal_weights = {sig: self.signal_weights.get(sig, 1.0) for sig in signals_used}
            
            # Create trade record
            trade_record = TradeRecord(
                symbol=symbol,
                trade_type=trade_type,
                direction=direction,
                signals_used=signals_used,
                signal_weights=signal_weights,
                entry_price=entry_price,
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                entry_time=entry_time,
                exit_time=exit_time,
                duration_seconds=duration_seconds
            )
            
            # Add to history
            self.trade_history.append(trade_record)
            
            # Update signal weights
            self._update_weights(trade_record)
            
            # Update symbol performance
            self._update_symbol_performance(trade_record)
            
            # Adjust risk based on symbol performance (learn instead of block)
            self._adjust_symbol_risk(symbol)
            
            # Save learning data
            self._save_learning_data()
            
            logger.info(f"Recorded trade: {trade_type} {direction} {symbol}, PnL: {pnl_pct*100:.2f}%")
            
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
    
    def _update_weights(self, trade_record: TradeRecord) -> None:
        """Update signal weights based on trade result"""
        try:
            # Profit -> increase weights
            if trade_record.pnl_pct > 0:
                for signal in trade_record.signals_used:
                    if signal in self.signal_weights:
                        self.signal_weights[signal] = min(
                            self.signal_weights[signal] + self.learning_rate,
                            self.max_weight
                        )
                        logger.debug(f"Increased {signal} weight to {self.signal_weights[signal]:.2f}")
            
            # Loss -> decrease weights
            else:
                for signal in trade_record.signals_used:
                    if signal in self.signal_weights:
                        self.signal_weights[signal] = max(
                            self.signal_weights[signal] - self.learning_rate,
                            self.min_weight
                        )
                        logger.debug(f"Decreased {signal} weight to {self.signal_weights[signal]:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating weights: {e}")
    
    def _update_symbol_performance(self, trade_record: TradeRecord) -> None:
        """Update symbol performance statistics"""
        try:
            symbol = trade_record.symbol
            
            if symbol not in self.symbol_performance:
                self.symbol_performance[symbol] = {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "total_pnl": 0.0,
                    "avg_pnl_pct": 0.0
                }
            
            perf = self.symbol_performance[symbol]
            perf["total_trades"] += 1
            
            if trade_record.pnl_pct > 0:
                perf["winning_trades"] += 1
            else:
                perf["losing_trades"] += 1
            
            perf["total_pnl"] += trade_record.pnl_pct
            perf["avg_pnl_pct"] = perf["total_pnl"] / perf["total_trades"]
            
        except Exception as e:
            logger.error(f"Error updating symbol performance: {e}")
    
    def _adjust_symbol_risk(self, symbol: str) -> None:
        """Adjust position size multiplier based on symbol performance - LEARN instead of blocking"""
        try:
            if symbol not in self.symbol_performance:
                self.symbol_risk_multiplier[symbol] = 1.0  # Default full size
                return
            
            perf = self.symbol_performance[symbol]
            total_trades = perf.get("total_trades", 0)
            winning_trades = perf.get("winning_trades", 0)
            
            # Need minimum trades before adjustment
            if total_trades < self.risk_adjustment_min_trades:
                self.symbol_risk_multiplier[symbol] = 1.0
                return
            
            # Calculate win rate
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
            
            # Dynamic position size based on performance
            if win_rate >= self.min_win_rate_for_full_size:
                # Good performance - full size
                self.symbol_risk_multiplier[symbol] = 1.0
                logger.info(f"📈 {symbol}: Good performance {win_rate*100:.1f}% win rate, full position size")
            elif win_rate >= self.min_win_rate_for_reduced:
                # Medium performance - reduced size to learn safely
                multiplier = 0.5 + (win_rate - self.min_win_rate_for_reduced) / (self.min_win_rate_for_full_size - self.min_win_rate_for_reduced) * 0.5
                self.symbol_risk_multiplier[symbol] = round(multiplier, 2)
                logger.info(f"⚠️ {symbol}: Medium performance {win_rate*100:.1f}% win rate, position size reduced to {multiplier*100:.0f}%")
            else:
                # Poor performance - minimal size to learn with minimal risk
                self.symbol_risk_multiplier[symbol] = 0.2  # 20% of normal size
                logger.warning(f"� {symbol}: Poor performance {win_rate*100:.1f}% win rate, learning mode: 20% position size. Keep trading to improve strategy!")
        
        except Exception as e:
            logger.error(f"Error adjusting risk for {symbol}: {e}")
    
    def get_position_size_multiplier(self, symbol: str) -> float:
        """Get position size multiplier for a symbol (0.2 to 1.0)"""
        return self.symbol_risk_multiplier.get(symbol, 1.0)
    
    def get_signal_weight(self, signal_type: str) -> float:
        """Get current weight for a signal type"""
        return self.signal_weights.get(signal_type, 1.0)
    
    def get_symbol_performance(self, symbol: str) -> Optional[Dict]:
        """Get performance statistics for a symbol"""
        return self.symbol_performance.get(symbol)
    
    def get_best_performing_symbols(self, top_n: int = 5) -> List[str]:
        """Get top N performing symbols by average PnL"""
        try:
            sorted_symbols = sorted(
                self.symbol_performance.items(),
                key=lambda x: x[1]["avg_pnl_pct"],
                reverse=True
            )
            return [symbol for symbol, _ in sorted_symbols[:top_n]]
        except Exception as e:
            logger.error(f"Error getting best performing symbols: {e}")
            return []
    
    def get_trade_statistics(self) -> Dict:
        """Get overall trade statistics"""
        try:
            if not self.trade_history:
                return {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "avg_pnl_pct": 0.0
                }
            
            total_trades = len(self.trade_history)
            winning_trades = sum(1 for t in self.trade_history if t.pnl_pct > 0)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
            avg_pnl_pct = sum(t.pnl_pct for t in self.trade_history) / total_trades if total_trades > 0 else 0.0
            
            return {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "avg_pnl_pct": avg_pnl_pct
            }
        except Exception as e:
            logger.error(f"Error getting trade statistics: {e}")
            return {}
    
    def _save_learning_data(self) -> None:
        """Save learning data to file"""
        try:
            data = {
                "signal_weights": self.signal_weights,
                "symbol_performance": self.symbol_performance,
                "trade_history": [asdict(t) for t in self.trade_history[-self.max_history_size:]],  # Keep last 1000 trades
                "symbol_risk_multiplier": self.symbol_risk_multiplier,
                "config": {
                    "min_win_rate_for_full_size": self.min_win_rate_for_full_size,
                    "min_win_rate_for_reduced": self.min_win_rate_for_reduced,
                    "risk_adjustment_min_trades": self.risk_adjustment_min_trades
                }
            }
            
            with open(self.history_file, 'w') as f:
                json.dump(data, f, default=str, indent=2)
            
        except Exception as e:
            logger.error(f"Error saving learning data: {e}")
    
    def _load_learning_data(self) -> None:
        """Load learning data from file"""
        try:
            if not os.path.exists(self.history_file):
                return
            
            with open(self.history_file, 'r') as f:
                data = json.load(f)
            
            self.signal_weights = data.get("signal_weights", self.signal_weights)
            self.symbol_performance = data.get("symbol_performance", {})
            self.symbol_risk_multiplier = data.get("symbol_risk_multiplier", {})
            
            # Load trade history (convert back to TradeRecord objects)
            trade_data = data.get("trade_history", [])
            for t in trade_data:
                try:
                    t["entry_time"] = datetime.fromisoformat(t["entry_time"])
                    t["exit_time"] = datetime.fromisoformat(t["exit_time"])
                    self.trade_history.append(TradeRecord(**t))
                except Exception as e:
                    logger.warning(f"Error loading trade record: {e}")
            
            adjusted_count = sum(1 for v in self.symbol_risk_multiplier.values() if v < 1.0)
            logger.info(f"Loaded learning data: {len(self.trade_history)} trades, {adjusted_count} symbols with reduced position size")
            
        except Exception as e:
            logger.error(f"Error loading learning data: {e}")
