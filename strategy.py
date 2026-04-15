"""
Smart Scalping Strategy - Entry/Exit Logic
PURE SIGNAL LAYER - No API calls, deterministic, testable
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
import pandas as pd
import numpy as np

from indicators import (
    calculate_all_indicators,
    IndicatorValues,
    calculate_ema
)
from regime_detector import (
    RegimeDetector,
    RegimeAnalysis,
    MarketRegime,
    regime_detector
)
from config import strategy_config, trading_config, regime_config, risk_config, fee_config
from logger import get_logger, log_event

logger = get_logger()


class SignalType(Enum):
    """Signal types"""
    LONG_ENTRY = "long_entry"
    SHORT_ENTRY = "short_entry"
    HOLD = "hold"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


@dataclass
class Signal:
    """Trading signal"""
    signal_type: SignalType
    symbol: str
    timestamp: datetime
    price: float
    confidence: float  # 0.0 to 1.0
    reason: str
    indicators: Dict[str, Any]
    regime: str

    # SL/TP levels (for entry signals)
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None

    # Partial exit info
    partial_exit_pct: Optional[float] = None
    partial_exit_price: Optional[float] = None

    @property
    def is_entry(self) -> bool:
        return self.signal_type in (SignalType.LONG_ENTRY, SignalType.SHORT_ENTRY)

    @property
    def direction(self) -> str:
        if self.signal_type == SignalType.LONG_ENTRY:
            return "long"
        elif self.signal_type == SignalType.SHORT_ENTRY:
            return "short"
        return "none"


class SmartScalpingStrategy:
    """
    Smart Scalping Strategy - 24/7 aggressive scalping with intelligent filtering:
    - EMA9/21 crossover for micro-impulse detection
    - VWAP filter for price context
    - RSI(5) for fast momentum confirmation
    - Micro-movement detection (≥0.1%)
    - ATR volatility filter (avoid flat and chaos)
    - 5m EMA50 trend context
    - Commission check (profit ≥ 2× commission)
    - Dynamic TP/SL based on volatility
    - Partial exit at small profit
    """

    def __init__(self):
        self.cfg = strategy_config
        self.regime_detector = regime_detector
        self._last_signal_time: Optional[datetime] = None
        self._min_signal_interval_minutes = 1  # Fast scalping - 1 min between signals
    
    def generate_signal(
        self,
        df: pd.DataFrame,
        current_position: Optional[str] = None,
        regime_analysis: Optional[RegimeAnalysis] = None
    ) -> Signal:
        """
        Generate trading signal from price data using smart scalping logic

        Args:
            df: Price DataFrame with OHLCV
            current_position: "long", "short", or None
            regime_analysis: Pre-computed regime analysis (optional)

        Returns:
            Signal object
        """
        symbol = trading_config.symbol
        current_price = df['close'].iloc[-1]
        timestamp = df.index[-1] if hasattr(df.index[-1], 'strftime') else datetime.utcnow()

        # Read config values dynamically (for real-time updates)
        cfg = strategy_config  # Use module-level config directly

        # Use provided regime analysis or compute it
        if regime_analysis is None:
            regime_analysis = self.regime_detector.analyze(df)

        # Get indicators
        indicators = calculate_all_indicators(
            df,
            ema_fast=cfg.ema_fast_period,
            ema_medium=cfg.ema_medium_period,
            ema_slow=cfg.ema_slow_period,
            rsi_period=cfg.rsi_period,
            atr_period=cfg.atr_period
        )

        # Get regime analysis
        if regime_analysis is None:
            regime_analysis = self.regime_detector.analyze(df, indicators)

        regime = regime_analysis.regime

        # Default signal
        default_signal = Signal(
            signal_type=SignalType.HOLD,
            symbol=symbol,
            timestamp=timestamp,
            price=current_price,
            confidence=0.0,
            reason="No valid setup",
            indicators=self._indicators_to_dict(indicators, current_price),
            regime=regime.value
        )

        # Check if already in position - no manual exits, only TP/SL
        if current_position:
            default_signal.reason = f"In {current_position} position - holding for TP/SL"
            return default_signal

        # Check for LONG entry
        long_signal = self._check_long_entry(df, indicators, regime_analysis, symbol, timestamp)
        if long_signal:
            return long_signal

        # Check for SHORT entry
        short_signal = self._check_short_entry(df, indicators, regime_analysis, symbol, timestamp)
        if short_signal:
            return short_signal

        default_signal.reason = "No valid setup"
        return default_signal

    def _check_long_entry(
        self,
        df: pd.DataFrame,
        ind: IndicatorValues,
        regime: RegimeAnalysis,
        symbol: str,
        timestamp: datetime
    ) -> Optional[Signal]:
        """Check for long entry - simplified: only EMA crossover"""
        current_price = df['close'].iloc[-1]

        # ONLY Condition: EMA9 > EMA21 (bullish crossover)
        if ind.ema_9 <= ind.ema_21:
            return None

        # Calculate TP/SL - price-based from config (convert percentage to absolute price)
        tp_pct = strategy_config.tp_pct  # 0.6%
        sl_pct = strategy_config.sl_pct  # 0.2%

        # Calculate absolute price levels
        sl = current_price * (1 - sl_pct)
        tp1 = current_price * (1 + tp_pct)
        tp2 = current_price * (1 + tp_pct * 1.5)

        # Partial exit price
        partial_exit_price = current_price * (1 + self.cfg.partial_exit_tp_pct)

        reason = f"LONG: EMA9>EMA21"

        return Signal(
            signal_type=SignalType.LONG_ENTRY,
            symbol=symbol,
            timestamp=timestamp,
            price=current_price,
            confidence=0.7,
            reason=reason,
            indicators=self._indicators_to_dict(ind, current_price),
            regime=regime.regime.value,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            partial_exit_pct=self.cfg.partial_exit_pct,
            partial_exit_price=partial_exit_price
        )

    def _check_short_entry(
        self,
        df: pd.DataFrame,
        ind: IndicatorValues,
        regime: RegimeAnalysis,
        symbol: str,
        timestamp: datetime
    ) -> Optional[Signal]:
        """Check for short entry - simplified: only EMA crossover"""
        current_price = df['close'].iloc[-1]

        # ONLY Condition: EMA9 < EMA21 (bearish crossover)
        if ind.ema_9 >= ind.ema_21:
            return None

        # Calculate TP/SL - price-based from config (convert percentage to absolute price)
        tp_pct = strategy_config.tp_pct  # 0.6%
        sl_pct = strategy_config.sl_pct  # 0.2%

        # Calculate absolute price levels
        sl = current_price * (1 + sl_pct)
        tp1 = current_price * (1 - tp_pct)
        tp2 = current_price * (1 - tp_pct * 1.5)

        # Partial exit price
        partial_exit_price = current_price * (1 - self.cfg.partial_exit_tp_pct)

        reason = f"SHORT: EMA9<EMA21"

        return Signal(
            signal_type=SignalType.SHORT_ENTRY,
            symbol=symbol,
            timestamp=timestamp,
            price=current_price,
            confidence=0.7,
            reason=reason,
            indicators=self._indicators_to_dict(ind, current_price),
            regime=regime.regime.value,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            partial_exit_pct=self.cfg.partial_exit_pct,
            partial_exit_price=partial_exit_price
        )

    def _indicators_to_dict(self, ind: IndicatorValues, price: float) -> Dict[str, Any]:
        """Convert indicators to dictionary"""
        return {
            "ema9": round(ind.ema_9, 2),
            "ema21": round(ind.ema_21, 2),
            "ema50": round(ind.ema_50, 2),
            "rsi5": round(ind.rsi_5, 2),
            "vwap": round(ind.vwap, 2),
            "atr": round(ind.atr, 4),
            "price": round(price, 2)
        }


# Global strategy instance
strategy = SmartScalpingStrategy()
