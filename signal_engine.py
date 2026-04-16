"""
Signal Engine - Classical filtering for SCOUT and NORMAL trades
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Trading signal data"""
    symbol: str
    direction: str  # "long" or "short"
    strength: float  # 0.0 to 1.0
    ema_signal: float  # -1.0 to 1.0 (negative = bearish, positive = bullish)
    rsi_signal: float  # -1.0 to 1.0
    volume_signal: float  # -1.0 to 1.0
    atr_signal: float  # -1.0 to 1.0
    timestamp: datetime
    reason: str


class SignalEngine:
    """
    Classical filtering for SCOUT and NORMAL trades
    
    Filters:
    - EMA 50 / EMA 200 (trend)
    - RSI (momentum / reversal)
    - Volume spike
    - ATR (volatility)
    
    Used only for SCOUT and NORMAL trades (not MOMENTUM)
    """
    
    def __init__(self, config):
        self.cfg = config
        
        # EMA settings
        self.ema_fast_period = 50
        self.ema_slow_period = 200
        self.ema_min_distance_pct = 0.005  # 0.5% minimum distance
        
        # RSI settings
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        # Volume settings
        self.volume_ma_period = 20
        self.volume_min_ratio = 1.5  # Volume must be 1.5x average
        
        # ATR settings
        self.atr_period = 14
        self.atr_min_threshold_pct = 0.001  # 0.1% minimum ATR
        
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """
        Generate trading signal from market data
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            
        Returns:
            Signal if conditions met, None otherwise
        """
        if len(df) < max(self.ema_slow_period, self.rsi_period, self.volume_ma_period, self.atr_period) + 1:
            return None
            
        try:
            # Calculate indicators
            ema_signal, ema_reason = self._check_ema_trend(df)
            rsi_signal, rsi_reason = self._check_rsi(df)
            volume_signal, volume_reason = self._check_volume(df)
            atr_signal, atr_reason = self._check_atr(df)
            
            # Calculate overall strength
            strength = self._calculate_strength(ema_signal, rsi_signal, volume_signal, atr_signal)
            
            # Determine direction based on weighted signals
            weighted_score = (ema_signal * 0.4 + 
                           rsi_signal * 0.3 + 
                           volume_signal * 0.2 + 
                           atr_signal * 0.1)
            
            if abs(weighted_score) < 0.3:  # Minimum threshold for signal
                return None
                
            direction = "long" if weighted_score > 0 else "short"
            
            reason = f"Signal: {ema_reason}, {rsi_reason}, {volume_reason}, {atr_reason}"
            
            return Signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                ema_signal=ema_signal,
                rsi_signal=rsi_signal,
                volume_signal=volume_signal,
                atr_signal=atr_signal,
                timestamp=datetime.utcnow(),
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None
    
    def _check_ema_trend(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Check EMA 50/200 trend"""
        try:
            ema_fast = df['close'].ewm(span=self.ema_fast_period).mean().iloc[-1]
            ema_slow = df['close'].ewm(span=self.ema_slow_period).mean().iloc[-1]
            ema_fast_prev = df['close'].ewm(span=self.ema_fast_period).mean().iloc[-2]
            ema_slow_prev = df['close'].ewm(span=self.ema_slow_period).mean().iloc[-2]
            
            # Check if EMAs are separated enough
            distance_pct = abs(ema_fast - ema_slow) / ema_slow
            if distance_pct < self.ema_min_distance_pct:
                return 0.0, "EMAs too close"
            
            # Bullish: EMA 50 > EMA 200 and both rising
            if ema_fast > ema_slow and ema_fast > ema_fast_prev and ema_slow > ema_slow_prev:
                return 1.0, "Bullish EMA crossover"
            
            # Bearish: EMA 50 < EMA 200 and both falling
            if ema_fast < ema_slow and ema_fast < ema_fast_prev and ema_slow < ema_slow_prev:
                return -1.0, "Bearish EMA crossover"
            
            # Neutral trend
            return 0.0, "No clear EMA trend"
            
        except Exception as e:
            logger.error(f"Error checking EMA trend: {e}")
            return 0.0, "EMA error"
    
    def _check_rsi(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Check RSI for momentum/reversal"""
        try:
            rsi = self._calculate_rsi(df, self.rsi_period)
            
            if rsi is None:
                return 0.0, "RSI calculation error"
            
            # Oversold - bullish signal
            if rsi < self.rsi_oversold:
                return 1.0, f"RSI oversold ({rsi:.1f})"
            
            # Overbought - bearish signal
            if rsi > self.rsi_overbought:
                return -1.0, f"RSI overbought ({rsi:.1f})"
            
            # Neutral
            return 0.0, f"RSI neutral ({rsi:.1f})"
            
        except Exception as e:
            logger.error(f"Error checking RSI: {e}")
            return 0.0, "RSI error"
    
    def _check_volume(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Check volume spike"""
        try:
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[-self.volume_ma_period:].mean()
            
            if avg_volume == 0:
                return 0.0, "No volume data"
            
            volume_ratio = current_volume / avg_volume
            
            # Volume spike supports the direction
            if volume_ratio >= self.volume_min_ratio:
                return 0.5, f"Volume spike ({volume_ratio:.2f}x)"
            
            # Low volume - weak signal
            return -0.3, f"Low volume ({volume_ratio:.2f}x)"
            
        except Exception as e:
            logger.error(f"Error checking volume: {e}")
            return 0.0, "Volume error"
    
    def _check_atr(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Check ATR for volatility"""
        try:
            atr = self._calculate_atr(df, self.atr_period)
            
            if atr is None:
                return 0.0, "ATR calculation error"
            
            current_price = df['close'].iloc[-1]
            atr_pct = atr / current_price
            
            # Sufficient volatility - good for trading
            if atr_pct >= self.atr_min_threshold_pct:
                return 0.5, f"Good volatility (ATR {atr_pct*100:.2f}%)"
            
            # Low volatility - avoid sideways
            return -0.5, f"Low volatility (ATR {atr_pct*100:.2f}%)"
            
        except Exception as e:
            logger.error(f"Error checking ATR: {e}")
            return 0.0, "ATR error"
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Calculate RSI"""
        if len(df) < period + 1:
            return None
            
        try:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Calculate ATR"""
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
    
    def _calculate_strength(self, ema: float, rsi: float, volume: float, atr: float) -> float:
        """Calculate overall signal strength (0.0 to 1.0)"""
        # Normalize each component to 0.0-1.0 range
        ema_strength = (ema + 1.0) / 2.0  # -1 to 1 -> 0 to 1
        rsi_strength = (rsi + 1.0) / 2.0  # -1 to 1 -> 0 to 1
        volume_strength = (volume + 1.0) / 2.0  # -1 to 1 -> 0 to 1
        atr_strength = (atr + 1.0) / 2.0  # -1 to 1 -> 0 to 1
        
        # Weighted average
        strength = (ema_strength * 0.4 + 
                   rsi_strength * 0.3 + 
                   volume_strength * 0.2 + 
                   atr_strength * 0.1)
        
        return min(max(strength, 0.0), 1.0)
