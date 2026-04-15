"""
Market Regime Detector - Trend vs Chop classification
Critical filter before any trade
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np

from indicators import (
    calculate_all_indicators, 
    get_ema_alignment, 
    detect_whipsaw,
    IndicatorValues
)
from logger import get_logger, log_event
from config import regime_config, trading_config

logger = get_logger()


class MarketRegime(Enum):
    """Market regime types"""
    TREND_BULLISH = "trend_bullish"
    TREND_BEARISH = "trend_bearish"
    CHOP = "chop"
    UNKNOWN = "unknown"


@dataclass
class RegimeAnalysis:
    """Complete regime analysis result"""
    regime: MarketRegime
    confidence: float  # 0.0 to 1.0
    adx: float
    is_trending: bool
    ema_aligned_bullish: bool
    ema_aligned_bearish: bool
    is_whipsawing: bool
    volatility_normal: bool
    details: Dict[str, Any]
    
    @property
    def can_trade(self) -> bool:
        """Whether trading is allowed in this regime"""
        return self.regime in (MarketRegime.TREND_BULLISH, MarketRegime.TREND_BEARISH)
    
    @property
    def trend_direction(self) -> str:
        """Get trend direction if trending"""
        if self.regime == MarketRegime.TREND_BULLISH:
            return "long"
        elif self.regime == MarketRegime.TREND_BEARISH:
            return "short"
        return "none"


class RegimeDetector:
    """
    Detects market regime using multiple factors:
    - ADX strength
    - EMA alignment
    - Whipsaw detection
    - Volatility checks
    """
    
    def __init__(self):
        self.cfg = regime_config
        self._regime_history: list = []
        self._max_history = 100
    
    def analyze(self, df, indicators: Optional[IndicatorValues] = None) -> RegimeAnalysis:
        """
        Analyze market regime from price data
        """
        if indicators is None:
            indicators = calculate_all_indicators(df)
        
        closes = df['close'].values
        current_price = closes[-1]
        
        # 1. Check ADX for trend strength
        adx = indicators.adx
        is_trending = adx > self.cfg.adx_trend_threshold
        is_chop = adx < self.cfg.adx_chop_threshold
        
        # 2. Check EMA alignment
        ema_align = get_ema_alignment(
            indicators.ema_fast,
            indicators.ema_medium,
            indicators.ema_slow,
            current_price
        )
        
        # 3. Detect whipsaw (chop indicator)
        is_whipsawing = detect_whipsaw(
            closes,
            ema_fast_period=self.cfg.ema_fast,
            lookback=self.cfg.chop_lookback
        )
        
        # 4. Check volatility (from indicators)
        volatility_normal = indicators.volatility_pct < 5.0  # Less than 5% volatility
        
        # Determine regime
        regime = MarketRegime.UNKNOWN
        confidence = 0.0
        
        # Trend mode requires multiple confirmations
        if is_trending and not is_whipsawing:
            if ema_align["bullish_aligned"]:
                regime = MarketRegime.TREND_BULLISH
                # Confidence based on ADX and trend strength
                confidence = min(1.0, adx / 50.0 + ema_align["trend_strength"] / 10.0)
            elif ema_align["bearish_aligned"]:
                regime = MarketRegime.TREND_BEARISH
                confidence = min(1.0, adx / 50.0 + ema_align["trend_strength"] / 10.0)
            else:
                # ADX high but EMAs not aligned - possible transition
                if adx > 30:
                    if indicators.plus_di > indicators.minus_di:
                        regime = MarketRegime.TREND_BULLISH
                        confidence = 0.5
                    else:
                        regime = MarketRegime.TREND_BEARISH
                        confidence = 0.5
                else:
                    regime = MarketRegime.CHOP
                    confidence = 1.0 - (adx / self.cfg.adx_trend_threshold)
        else:
            # Not trending or whipsawing
            regime = MarketRegime.CHOP
            confidence = 1.0 - (adx / self.cfg.adx_trend_threshold) if adx < self.cfg.adx_trend_threshold else 0.5
        
        # Store history
        self._regime_history.append({
            "regime": regime,
            "confidence": confidence,
            "adx": adx
        })
        if len(self._regime_history) > self._max_history:
            self._regime_history.pop(0)
        
        analysis = RegimeAnalysis(
            regime=regime,
            confidence=confidence,
            adx=adx,
            is_trending=is_trending,
            ema_aligned_bullish=ema_align["bullish_aligned"],
            ema_aligned_bearish=ema_align["bearish_aligned"],
            is_whipsawing=is_whipsawing,
            volatility_normal=volatility_normal,
            details={
                "ema20": indicators.ema_fast,
                "ema50": indicators.ema_medium,
                "ema200": indicators.ema_slow,
                "price": current_price,
                "plus_di": indicators.plus_di,
                "minus_di": indicators.minus_di,
                "rsi": indicators.rsi,
                "atr": indicators.atr,
                "adx": indicators.adx
            }
        )
        
        # Log regime detection
        log_event("info", f"Regime: {regime.value} (conf: {confidence:.2f}, ADX: {adx:.1f})",
                  regime=regime.value,
                  confidence=confidence,
                  adx=adx,
                  is_whipsawing=is_whipsawing,
                  can_trade=analysis.can_trade)
        
        return analysis
    
    def is_stable_regime(self, min_bars: int = 3) -> bool:
        """
        Check if current regime has been stable for minimum bars
        Avoids trading on regime transitions
        """
        if len(self._regime_history) < min_bars:
            return False
        
        recent_regimes = [h["regime"] for h in self._regime_history[-min_bars:]]
        return len(set(recent_regimes)) == 1  # All same regime
    
    def get_regime_duration(self) -> int:
        """Get how long current regime has persisted"""
        if not self._regime_history:
            return 0
        
        current_regime = self._regime_history[-1]["regime"]
        duration = 0
        
        for h in reversed(self._regime_history):
            if h["regime"] == current_regime:
                duration += 1
            else:
                break
        
        return duration
    
    def get_adx_trend(self) -> str:
        """Get ADX direction - strengthening or weakening trend"""
        if len(self._regime_history) < 5:
            return "unknown"
        
        recent_adx = [h["adx"] for h in self._regime_history[-5:]]
        
        if len(recent_adx) < 2:
            return "unknown"
        
        # Simple linear regression slope
        x = np.arange(len(recent_adx))
        slope = np.polyfit(x, recent_adx, 1)[0]
        
        if slope > 0.5:
            return "strengthening"
        elif slope < -0.5:
            return "weakening"
        return "stable"


# Global detector instance
regime_detector = RegimeDetector()
