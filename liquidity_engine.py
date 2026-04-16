"""
Liquidity Engine - Detects liquidity traps and filters bad entries
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class LiquidityAnalysis:
    """Liquidity analysis result"""
    symbol: str
    has_trap: bool  # True if liquidity trap detected
    trap_type: Optional[str]  # "breakout_fake", "stop_sweep", "reversal_trap"
    trap_confidence: float  # 0.0 to 1.0
    breakout_valid: bool  # True if breakout is genuine
    entry_quality: str  # "excellent", "good", "poor", "avoid"
    reason: str
    timestamp: datetime


class LiquidityEngine:
    """
    Liquidity Trap Detection and Smart Entry Filtering
    
    Detects:
    - Liquidity traps (fake breakouts)
    - Stop sweeps
    - Reversal traps
    
    Filters:
    - Bad entries on obvious levels
    - Entries during liquidity sweeps
    - Entries without volume confirmation
    """
    
    def __init__(self, config):
        self.cfg = config
        
        # Trap detection parameters
        self.breakout_threshold_pct = 0.003  # 0.3% minimum for breakout
        self.reversal_threshold_pct = 0.002  # 0.2% reversal to detect fake breakout
        self.volume_spike_multiplier = 2.0  # Volume must be 2x average for trap
        self.trap_lookback_periods = 10  # Look back 10 periods for trap detection
        
        # Smart entry filter parameters
        self.min_pullback_pct = 0.001  # 0.1% minimum pullback for good entry
        self.max_impulse_length_pct = 0.02  # 2% max impulse before avoiding (anti-FOMO)
        self.volume_confirmation_periods = 3  # Need 3 periods of volume confirmation
        
    def analyze_liquidity(self, df: pd.DataFrame, symbol: str) -> Optional[LiquidityAnalysis]:
        """
        Analyze liquidity conditions for entry
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            
        Returns:
            LiquidityAnalysis with trap detection and entry quality
        """
        if len(df) < self.trap_lookback_periods + 20:
            return None
            
        try:
            # Detect liquidity traps
            has_trap, trap_type, trap_confidence = self._detect_liquidity_trap(df)
            
            # Check if breakout is valid
            breakout_valid = self._validate_breakout(df)
            
            # Determine entry quality
            entry_quality = self._assess_entry_quality(df, has_trap, breakout_valid)
            
            reason = self._generate_reason(has_trap, trap_type, breakout_valid, entry_quality)
            
            return LiquidityAnalysis(
                symbol=symbol,
                has_trap=has_trap,
                trap_type=trap_type,
                trap_confidence=trap_confidence,
                breakout_valid=breakout_valid,
                entry_quality=entry_quality,
                reason=reason,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error analyzing liquidity for {symbol}: {e}")
            return None
    
    def _detect_liquidity_trap(self, df: pd.DataFrame) -> Tuple[bool, Optional[str], float]:
        """Detect liquidity trap patterns"""
        try:
            recent_closes = df['close'].iloc[-self.trap_lookback_periods:]
            recent_volumes = df['volume'].iloc[-self.trap_lookback_periods:]
            
            if len(recent_closes) < self.trap_lookback_periods:
                return False, None, 0.0
            
            # Calculate price movement
            price_change = (recent_closes.iloc[-1] - recent_closes.iloc[0]) / recent_closes.iloc[0]
            
            # Calculate volume spike
            avg_volume = df['volume'].iloc[-20:].mean()
            current_volume = recent_volumes.iloc[-1]
            volume_spike = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Check for fake breakout pattern
            # Sharp move up then quick reversal
            if price_change > self.breakout_threshold_pct:
                # Check for reversal in recent periods
                max_price = recent_closes.max()
                current_price = recent_closes.iloc[-1]
                reversal_pct = (max_price - current_price) / max_price
                
                if reversal_pct > self.reversal_threshold_pct and volume_spike > self.volume_spike_multiplier:
                    return True, "breakout_fake", 0.8
            
            # Check for stop sweep pattern
            # Sharp move through key level then reversal
            lows = df['low'].iloc[-self.trap_lookback_periods:]
            highs = df['high'].iloc[-self.trap_lookback_periods:]
            
            if len(lows) >= 3:
                # Stop sweep: price pushes through recent low then reverses
                if lows.iloc[-1] < lows.iloc[:-1].min() and recent_closes.iloc[-1] > recent_closes.iloc[-2]:
                    if volume_spike > self.volume_spike_multiplier:
                        return True, "stop_sweep", 0.7
            
            return False, None, 0.0
            
        except Exception as e:
            logger.error(f"Error detecting liquidity trap: {e}")
            return False, None, 0.0
    
    def _validate_breakout(self, df: pd.DataFrame) -> bool:
        """Check if breakout is valid (not a trap)"""
        try:
            recent_closes = df['close'].iloc[-10:]
            
            if len(recent_closes) < 5:
                return True  # Can't determine, assume valid
            
            # Check for sustained movement
            price_change = (recent_closes.iloc[-1] - recent_closes.iloc[0]) / recent_closes.iloc[0]
            
            # Check for volume confirmation
            recent_volumes = df['volume'].iloc[-self.volume_confirmation_periods:]
            avg_volume = df['volume'].iloc[-20:].mean()
            
            if len(recent_volumes) < self.volume_confirmation_periods:
                return True
            
            volume_confirmed = all(vol > avg_volume * 1.2 for vol in recent_volumes)
            
            # Valid if: sustained movement + volume confirmation
            return abs(price_change) > self.breakout_threshold_pct and volume_confirmed
            
        except Exception as e:
            logger.error(f"Error validating breakout: {e}")
            return True
    
    def _assess_entry_quality(self, df: pd.DataFrame, has_trap: bool, breakout_valid: bool) -> str:
        """Assess entry quality based on market conditions"""
        try:
            if has_trap:
                return "avoid"
            
            if not breakout_valid:
                return "poor"
            
            # Check for pullback (good entry)
            recent_closes = df['close'].iloc[-5:]
            if len(recent_closes) >= 2:
                pullback = abs(recent_closes.iloc[-1] - recent_closes.max()) / recent_closes.max()
                if pullback > self.min_pullback_pct:
                    return "excellent"
            
            # Check if impulse is too long (anti-FOMO)
            recent_closes = df['close'].iloc[-20:]
            if len(recent_closes) >= 10:
                impulse_pct = abs(recent_closes.iloc[-1] - recent_closes.iloc[-10]) / recent_closes.iloc[-10]
                if impulse_pct > self.max_impulse_length_pct:
                    return "poor"
            
            return "good"
            
        except Exception as e:
            logger.error(f"Error assessing entry quality: {e}")
            return "good"
    
    def _generate_reason(self, has_trap: bool, trap_type: Optional[str], 
                        breakout_valid: bool, entry_quality: str) -> str:
        """Generate human-readable reason for analysis"""
        parts = []
        
        if has_trap and trap_type:
            parts.append(f"Liquidity trap detected ({trap_type})")
        
        if not breakout_valid:
            parts.append("Breakout not confirmed")
        
        parts.append(f"Entry quality: {entry_quality}")
        
        return ", ".join(parts) if parts else "Normal market conditions"
