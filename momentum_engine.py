"""
Momentum Engine - Detects sharp market movements
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class MomentumSignal:
    """Momentum signal data"""
    symbol: str
    direction: str  # "long" or "short"
    strength: float  # 0.0 to 1.0
    price_move_pct: float
    volume_spike_ratio: float
    atr_surge_pct: float
    timestamp: datetime
    reason: str


class MomentumEngine:
    """
    Detects sharp market movements for momentum trading
    
    Logic:
    - Percentage price change over short period
    - Volume spike
    - ATR surge (volatility increase)
    
    Conditions for momentum:
    - Price move > threshold (e.g., 0.5-1%)
    - Volume spike > average * multiplier
    """
    
    def __init__(self, config):
        self.cfg = config
        self.price_move_threshold_pct = 0.005  # 0.5% minimum price move
        self.volume_spike_multiplier = 2.0  # Volume must be 2x average
        self.atr_surge_threshold = 1.5  # ATR must be 1.5x recent average
        self.lookback_periods = 5  # Look back 5 periods for momentum detection
        self.volume_ma_period = 20  # 20-period volume MA
        
    def detect_momentum(self, df: pd.DataFrame, symbol: str) -> Optional[MomentumSignal]:
        """
        Detect momentum signal from market data
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            
        Returns:
            MomentumSignal if momentum detected, None otherwise
        """
        if len(df) < max(self.lookback_periods, self.volume_ma_period) + 1:
            return None
            
        try:
            # Calculate price move
            current_price = df['close'].iloc[-1]
            price_n_periods_ago = df['close'].iloc[-self.lookback_periods - 1]
            price_move_pct = abs(current_price - price_n_periods_ago) / price_n_periods_ago
            
            # Calculate volume spike
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[-self.volume_ma_period:].mean()
            volume_spike_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Calculate ATR surge
            atr_period = 14
            recent_atr = self._calculate_atr(df, atr_period)
            if recent_atr is None:
                return None
                
            # Compare recent ATR to average ATR over longer period
            atr_lookback = 50
            if len(df) >= atr_lookback + atr_period:
                avg_atr = self._calculate_average_atr(df, atr_period, atr_lookback)
                atr_surge_ratio = recent_atr / avg_atr if avg_atr > 0 else 1.0
            else:
                atr_surge_ratio = 1.0
            
            # Determine direction
            if current_price > price_n_periods_ago:
                direction = "long"
            else:
                direction = "short"
            
            # Calculate momentum strength (0.0 to 1.0)
            strength = self._calculate_strength(
                price_move_pct, 
                volume_spike_ratio, 
                atr_surge_ratio
            )
            
            # Check if momentum conditions are met
            if (price_move_pct >= self.price_move_threshold_pct and
                volume_spike_ratio >= self.volume_spike_multiplier):
                
                reason = (f"Momentum detected: {price_move_pct*100:.2f}% price move, "
                         f"{volume_spike_ratio:.2f}x volume, "
                         f"{atr_surge_ratio:.2f}x ATR")
                
                return MomentumSignal(
                    symbol=symbol,
                    direction=direction,
                    strength=strength,
                    price_move_pct=price_move_pct,
                    volume_spike_ratio=volume_spike_ratio,
                    atr_surge_pct=atr_surge_ratio,
                    timestamp=datetime.utcnow(),
                    reason=reason
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting momentum for {symbol}: {e}")
            return None
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Calculate ATR (Average True Range)"""
        if len(df) < period + 1:
            return None
            
        try:
            high = df['high'].iloc[-period:]
            low = df['low'].iloc[-period:]
            close = df['close'].iloc[-period-1:-1]
            
            true_range = pd.concat([
                high - low,
                (high - close).abs(),
                (low - close).abs()
            ], axis=1).max(axis=1)
            
            atr = true_range.rolling(window=period).mean().iloc[-1]
            return atr
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None
    
    def _calculate_average_atr(self, df: pd.DataFrame, atr_period: int, lookback: int) -> float:
        """Calculate average ATR over lookback period"""
        atr_values = []
        
        for i in range(atr_period, min(atr_period + lookback, len(df))):
            subset = df.iloc[:i]
            atr = self._calculate_atr(subset, atr_period)
            if atr is not None:
                atr_values.append(atr)
        
        return np.mean(atr_values) if atr_values else 1.0
    
    def _calculate_strength(self, price_move: float, volume_spike: float, atr_surge: float) -> float:
        """Calculate momentum strength (0.0 to 1.0)"""
        # Normalize each component
        price_strength = min(price_move / self.price_move_threshold_pct, 2.0) / 2.0
        volume_strength = min(volume_spike / self.volume_spike_multiplier, 3.0) / 3.0
        atr_strength = min(atr_surge / self.atr_surge_threshold, 2.0) / 2.0
        
        # Weighted average (price move is most important)
        strength = (price_strength * 0.5 + 
                    volume_strength * 0.3 + 
                    atr_strength * 0.2)
        
        return min(max(strength, 0.0), 1.0)
