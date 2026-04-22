import logging
from typing import Dict, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Risk management engine.
    Handles global drawdown protection and dynamic leverage scaling.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.risk_config = config.get("risk_engine", {})
        
        # Risk settings
        self.global_drawdown_cutoff = self.risk_config.get("global_drawdown_cutoff", -0.08)
        self.leverage_scaling = self.risk_config.get("leverage_scaling", True)
        self.max_leverage = self.risk_config.get("max_leverage", 5)
        
        # State tracking
        self.initial_capital = 100000.0
        self.current_capital = 100000.0
        self.peak_capital = 100000.0
        self.drawdown = 0.0
        
        # PnL history
        self.pnl_history: deque = deque(maxlen=100)
        self.total_pnl = 0.0
        self.trade_count = 0
        
        # Emergency stop
        self.emergency_stop_triggered = False
        
        # Leverage multiplier
        self.current_leverage_multiplier = 1.0
        
    def set_initial_capital(self, capital: float):
        """Set initial capital for drawdown calculation."""
        self.initial_capital = capital
        self.current_capital = capital
        self.peak_capital = capital
        logger.info(f"Initial capital set to ${capital:,.2f}")
        
    def update_capital(self, capital: float):
        """Update current capital and calculate drawdown."""
        self.current_capital = capital
        
        # Update peak
        if capital > self.peak_capital:
            self.peak_capital = capital
            
        # Calculate drawdown
        self.drawdown = (capital - self.peak_capital) / self.peak_capital if self.peak_capital > 0 else 0
        
        # Check emergency stop
        if self.drawdown <= self.global_drawdown_cutoff:
            self.emergency_stop_triggered = True
            logger.critical(f"EMERGENCY STOP TRIGGERED: Drawdown {self.drawdown:.2%} exceeds cutoff {self.global_drawdown_cutoff:.2%}")
            
    def record_pnl(self, pnl: float):
        """Record trade PnL."""
        self.pnl_history.append(pnl)
        self.total_pnl += pnl
        self.trade_count += 1
        
        # Update capital
        self.update_capital(self.current_capital + pnl)
        
        # Update leverage scaling
        if self.leverage_scaling:
            self._update_leverage_scaling()
            
    def _update_leverage_scaling(self):
        """Update leverage multiplier based on performance."""
        if self.trade_count < 10:
            return  # Need minimum trades
            
        # Calculate recent performance
        recent_pnl = sum(list(self.pnl_history)[-20:])
        wins = sum(1 for p in list(self.pnl_history)[-20:] if p > 0)
        win_rate = wins / min(20, len(self.pnl_history))
        
        # Scale leverage based on performance
        if recent_pnl > 0 and win_rate > 0.6:
            # Good performance - increase leverage
            self.current_leverage_multiplier = min(self.current_leverage_multiplier * 1.1, self.max_leverage)
        elif recent_pnl < 0 or win_rate < 0.4:
            # Poor performance - decrease leverage
            self.current_leverage_multiplier = max(self.current_leverage_multiplier * 0.9, 1.0)
            
    def get_leverage_multiplier(self) -> float:
        """Get current leverage multiplier."""
        return self.current_leverage_multiplier
        
    def is_emergency_stop(self) -> bool:
        """Check if emergency stop is triggered."""
        return self.emergency_stop_triggered
        
    def reset_emergency_stop(self):
        """Reset emergency stop flag (use with caution)."""
        self.emergency_stop_triggered = False
        logger.warning("Emergency stop flag reset")
        
    def get_drawdown(self) -> float:
        """Get current drawdown."""
        return self.drawdown
        
    def get_risk_summary(self) -> dict:
        """Get summary of risk metrics."""
        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "drawdown": self.drawdown,
            "drawdown_pct": self.drawdown * 100,
            "total_pnl": self.total_pnl,
            "trade_count": self.trade_count,
            "leverage_multiplier": self.current_leverage_multiplier,
            "emergency_stop": self.emergency_stop_triggered
        }
        
    def check_position_size(self, symbol: str, allocation: float) -> bool:
        """Check if position size is within risk limits."""
        # Position size as percentage of capital
        position_pct = allocation / self.current_capital if self.current_capital > 0 else 0
        
        # Max position size is 25% of capital (configurable)
        max_position_pct = 0.25
        
        if position_pct > max_position_pct:
            logger.warning(f"Position size {position_pct:.2%} exceeds max {max_position_pct:.2%} for {symbol}")
            return False
            
        return True
