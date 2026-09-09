"""
Professional MAE/MFE Tracker - Track maximum adverse and favorable excursions
"""
import time
from typing import Dict, Any, Optional
from loguru import logger


class MAEMFETracker:
    """Track maximum adverse and favorable excursions for positions"""
    
    def __init__(self):
        # Active position tracking: {symbol: {"entry_price": float, "side": str, "entry_time": float, "max_favorable": float, "max_adverse": float}}
        self._active_positions: Dict[str, Dict[str, Any]] = {}
    
    def register_position(self, symbol: str, entry_price: float, side: str, entry_time: float):
        """Register a new position for tracking"""
        self._active_positions[symbol] = {
            "entry_price": entry_price,
            "side": side,
            "entry_time": entry_time,
            "max_favorable": 0.0,
            "max_adverse": 0.0
        }
        logger.debug(f"[MAE_MFE] Registered position {symbol} at {entry_price}")
    
    def update_position(self, symbol: str, current_price: float):
        """Update MAE/MFE for a position based on current price"""
        if symbol not in self._active_positions:
            return
        
        position = self._active_positions[symbol]
        entry_price = position["entry_price"]
        side = position["side"]
        
        # Calculate price movement
        if side == "long":
            price_move = current_price - entry_price
        else:  # short
            price_move = entry_price - current_price
        
        # Update maximums
        if price_move > position["max_favorable"]:
            position["max_favorable"] = price_move
        
        if price_move < position["max_adverse"]:
            position["max_adverse"] = price_move
    
    def close_position(self, symbol: str, exit_price: float) -> Dict[str, float]:
        """Close position and return final MAE/MFE metrics"""
        if symbol not in self._active_positions:
            logger.warning(f"[MAE_MFE] Position {symbol} not found in tracker")
            return self._get_empty_metrics()
        
        position = self._active_positions[symbol]
        entry_price = position["entry_price"]
        side = position["side"]
        
        # Final update with exit price
        self.update_position(symbol, exit_price)
        
        # Calculate final metrics
        max_favorable = position["max_favorable"]
        max_adverse = position["max_adverse"]
        
        # Calculate percentages
        mae_pct = (max_adverse / entry_price) * 100 if entry_price > 0 else 0.0
        mfe_pct = (max_favorable / entry_price) * 100 if entry_price > 0 else 0.0
        
        # Calculate R-multiples (assuming risk = 0.5 * ATR, we'll use entry price * 0.005 as proxy)
        risk_amount = entry_price * 0.005  # 0.5% as proxy for risk
        mae_r = max_adverse / risk_amount if risk_amount > 0 else 0.0
        mfe_r = max_favorable / risk_amount if risk_amount > 0 else 0.0
        
        # Remove from tracking
        del self._active_positions[symbol]
        
        metrics = {
            "mae": max_adverse,
            "mae_pct": mae_pct,
            "mae_r": mae_r,
            "mfe": max_favorable,
            "mfe_pct": mfe_pct,
            "mfe_r": mfe_r
        }
        
        logger.debug(f"[MAE_MFE] Closed position {symbol} - MAE: {mae_pct:.2f}%, MFE: {mfe_pct:.2f}%")
        return metrics
    
    def _get_empty_metrics(self) -> Dict[str, float]:
        """Return empty metrics when position not found"""
        return {
            "mae": 0.0,
            "mae_pct": 0.0,
            "mae_r": 0.0,
            "mfe": 0.0,
            "mfe_pct": 0.0,
            "mfe_r": 0.0
        }
    
    def get_active_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all currently tracked positions"""
        return self._active_positions.copy()