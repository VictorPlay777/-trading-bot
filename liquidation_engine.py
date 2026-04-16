"""
Liquidation Engine - Hunts for liquidation cascades and overextended markets
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class LiquidationSignal:
    """Liquidation cascade signal"""
    symbol: str
    direction: str  # "short" (hunt longs) or "long" (hunt shorts)
    strength: float  # 0.0 to 1.0
    market_state: str  # "LONG_OVERHEATED", "SHORT_OVERHEATED", "NEUTRAL"
    rsi_value: float
    ema_deviation_pct: float
    momentum_acceleration: float
    timestamp: datetime
    reason: str


class LiquidationEngine:
    """
    Liquidation Cascade Hunting
    
    Detects:
    - Overextended markets (long overheated / short overheated)
    - Liquidity imbalance
    - Cascade setup (parabolic moves, exhaustion)
    
    Hunts:
    - Reversals after long squeezes
    - Reversals after short squeezes
    - Counter-trend entries at exhaustion points
    """
    
    def __init__(self, config):
        self.cfg = config
        
        # Overextended detection parameters
        self.rsi_overbought_threshold = 70  # RSI > 70 = long overheated
        self.rsi_oversold_threshold = 30  # RSI < 30 = short overheated
        self.rsi_extreme_threshold = 80  # RSI > 80 = extreme long overheated
        self.rsi_extreme_oversold = 20  # RSI < 20 = extreme short overheated
        
        # EMA deviation parameters
        self.ema_fast_period = 50
        self.ema_slow_period = 200
        self.ema_deviation_threshold_pct = 0.02  # 2% deviation from EMA
        self.ema_extreme_deviation_pct = 0.05  # 5% extreme deviation
        
        # Momentum acceleration parameters
        self.momentum_lookback = 5
        self.acceleration_threshold = 1.5  # Momentum must be 1.5x recent average
        
        # Volume parameters
        self.volume_ma_period = 20
        self.volume_spike_multiplier = 2.0
        
    def detect_liquidation_opportunity(self, df: pd.DataFrame, symbol: str) -> Optional[LiquidationSignal]:
        """
        Detect liquidation cascade opportunity
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            
        Returns:
            LiquidationSignal if cascade setup detected, None otherwise
        """
        if len(df) < max(self.ema_slow_period, 50) + 1:
            return None
            
        try:
            # 1. Detect overextended market
            market_state, rsi_val, ema_dev = self._detect_overextended_market(df)
            
            if market_state == "NEUTRAL":
                return None
            
            # 2. Detect liquidity imbalance
            has_imbalance = self._detect_liquidity_imbalance(df)
            
            # 3. Detect cascade setup (acceleration)
            acceleration = self._detect_momentum_acceleration(df)
            
            # 4. Determine if cascade is ready
            cascade_ready = False
            direction = ""
            reason = ""
            
            if market_state == "LONG_OVERHEATED":
                # Hunt longs - look for short entry after exhaustion
                if rsi_val >= self.rsi_extreme_threshold and acceleration > self.acceleration_threshold:
                    cascade_ready = True
                    direction = "short"
                    reason = f"Longs overheated: RSI {rsi_val:.1f}, EMA deviation {ema_dev*100:.1f}%, acceleration {acceleration:.2f}x"
                elif rsi_val >= self.rsi_overbought_threshold and has_imbalance:
                    cascade_ready = True
                    direction = "short"
                    reason = f"Longs overheated with liquidity imbalance: RSI {rsi_val:.1f}"
            
            elif market_state == "SHORT_OVERHEATED":
                # Hunt shorts - look for long entry after exhaustion
                if rsi_val <= self.rsi_extreme_oversold and acceleration > self.acceleration_threshold:
                    cascade_ready = True
                    direction = "long"
                    reason = f"Shorts overheated: RSI {rsi_val:.1f}, EMA deviation {ema_dev*100:.1f}%, acceleration {acceleration:.2f}x"
                elif rsi_val <= self.rsi_oversold_threshold and has_imbalance:
                    cascade_ready = True
                    direction = "long"
                    reason = f"Shorts overheated with liquidity imbalance: RSI {rsi_val:.1f}"
            
            if not cascade_ready:
                return None
            
            # Calculate signal strength
            strength = self._calculate_strength(rsi_val, ema_dev, acceleration, market_state)
            
            return LiquidationSignal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                market_state=market_state,
                rsi_value=rsi_val,
                ema_deviation_pct=ema_dev,
                momentum_acceleration=acceleration,
                timestamp=datetime.utcnow(),
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Error detecting liquidation opportunity for {symbol}: {e}")
            return None
    
    def _detect_overextended_market(self, df: pd.DataFrame) -> Tuple[str, float, float]:
        """
        Detect if market is overextended
        
        Returns:
            (market_state, rsi_value, ema_deviation_pct)
            market_state: "LONG_OVERHEATED", "SHORT_OVERHEATED", "NEUTRAL"
        """
        try:
            # Calculate RSI
            rsi = self._calculate_rsi(df, 14)
            
            # Calculate EMA deviation
            ema_fast = df['close'].ewm(span=self.ema_fast_period).mean().iloc[-1]
            ema_slow = df['close'].ewm(span=self.ema_slow_period).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            if ema_slow > 0:
                ema_deviation = (current_price - ema_slow) / ema_slow
            else:
                ema_deviation = 0.0
            
            # Determine market state
            if rsi >= self.rsi_overbought_threshold and ema_deviation > self.ema_deviation_threshold_pct:
                return "LONG_OVERHEATED", rsi, ema_deviation
            elif rsi <= self.rsi_oversold_threshold and ema_deviation < -self.ema_deviation_threshold_pct:
                return "SHORT_OVERHEATED", rsi, ema_deviation
            else:
                return "NEUTRAL", rsi, ema_deviation
            
        except Exception as e:
            logger.error(f"Error detecting overextended market: {e}")
            return "NEUTRAL", 50.0, 0.0
    
    def _detect_liquidity_imbalance(self, df: pd.DataFrame) -> bool:
        """Detect liquidity imbalance (one-sided flow without normal pullbacks)"""
        try:
            # Check for strong trend with low retracement
            recent_closes = df['close'].iloc[-20:]
            
            # Calculate trend strength
            if len(recent_closes) < 2:
                return False
            
            trend_direction = "up" if recent_closes.iloc[-1] > recent_closes.iloc[0] else "down"
            
            # Count pullbacks (moves against trend)
            pullbacks = 0
            for i in range(1, len(recent_closes)):
                if trend_direction == "up" and recent_closes.iloc[i] < recent_closes.iloc[i-1]:
                    pullbacks += 1
                elif trend_direction == "down" and recent_closes.iloc[i] > recent_closes.iloc[i-1]:
                    pullbacks += 1
            
            # If very few pullbacks, likely liquidity imbalance
            pullback_ratio = pullbacks / len(recent_closes)
            
            # Volume spike check
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[-self.volume_ma_period:].mean()
            volume_spike = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Imbalance if: low pullbacks + volume spike
            return pullback_ratio < 0.3 and volume_spike > self.volume_spike_multiplier
            
        except Exception as e:
            logger.error(f"Error detecting liquidity imbalance: {e}")
            return False
    
    def _detect_momentum_acceleration(self, df: pd.DataFrame) -> float:
        """Detect if momentum is accelerating (parabolic move)"""
        try:
            if len(df) < self.momentum_lookback * 2:
                return 0.0
            
            # Calculate recent momentum
            recent_returns = df['close'].pct_change().iloc[-self.momentum_lookback:]
            recent_momentum = recent_returns.abs().mean()
            
            # Calculate earlier momentum for comparison
            earlier_returns = df['close'].pct_change().iloc[-self.momentum_lookback*2:-self.momentum_lookback]
            earlier_momentum = earlier_returns.abs().mean() if len(earlier_returns) > 0 else 0.0
            
            # Acceleration ratio
            if earlier_momentum > 0:
                acceleration = recent_momentum / earlier_momentum
            else:
                acceleration = 1.0
            
            return acceleration
            
        except Exception as e:
            logger.error(f"Error detecting momentum acceleration: {e}")
            return 0.0
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> float:
        """Calculate RSI"""
        try:
            if len(df) < period + 1:
                return 50.0
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 50.0
    
    def _calculate_strength(self, rsi: float, ema_dev: float, acceleration: float, market_state: str) -> float:
        """Calculate signal strength (0.0 to 1.0)"""
        try:
            # Normalize RSI deviation from neutral (50)
            if market_state == "LONG_OVERHEATED":
                rsi_strength = (rsi - 50) / 50  # 50 to 100 -> 0 to 1
            else:  # SHORT_OVERHEATED
                rsi_strength = (50 - rsi) / 50  # 0 to 50 -> 0 to 1
            
            # Normalize EMA deviation
            ema_strength = min(abs(ema_dev) / self.ema_extreme_deviation_pct, 1.0)
            
            # Normalize acceleration
            acc_strength = min(acceleration / 3.0, 1.0)  # Cap at 3x
            
            # Weighted average
            strength = (rsi_strength * 0.5 + 
                       ema_strength * 0.3 + 
                       acc_strength * 0.2)
            
            return min(max(strength, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating strength: {e}")
            return 0.5
