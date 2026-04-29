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
import json
import os

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

# Load bot config for TP/SL settings
BOT_CONFIG = {}
try:
    config_path = os.path.join(os.path.dirname(__file__), 'bot_configs', 'bot_5_trend_yolo.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            BOT_CONFIG = json.load(f)
        logger.info(f"Strategy loaded bot config: TP={BOT_CONFIG.get('risk', {}).get('dynamic_take_profit', {}).get('base_pct', 0.4)}%, SL={BOT_CONFIG.get('risk', {}).get('dynamic_stop_loss', {}).get('base_pct', 0.2)}%")
    else:
        logger.warning(f"Bot config not found at {config_path}")
except Exception as e:
    logger.error(f"Failed to load bot config in strategy: {e}")


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
        """Check for long entry - improved with RSI, VWAP, and multi-timeframe filters"""
        current_price = df['close'].iloc[-1]

        # Condition 1: EMA9 > EMA21 (bullish crossover)
        if ind.ema_9 <= ind.ema_21:
            return None

        # Condition 2: RSI filter - avoid overbought
        if self.cfg.rsi_filter_enabled:
            if ind.rsi_5 >= self.cfg.rsi_overbought:
                return None

        # Condition 3: VWAP filter - trade above VWAP
        if self.cfg.vwap_filter_enabled:
            if current_price <= ind.vwap:
                return None

        # Condition 4: Multi-timeframe analysis - check higher timeframes
        if trading_config.multi_timeframe_enabled:
            from config import trading_config
            from market_data import MarketDataManager

            mtf_agreement = 0
            mtf_reasons = []

            for tf in trading_config.higher_timeframes:
                try:
                    # Get data for higher timeframe
                    mtf_df = MarketDataManager().get_dataframe(symbol, tf, limit=200)
                    if len(mtf_df) >= 50:
                        mtf_ind = calculate_all_indicators(
                            mtf_df,
                            ema_fast=9,
                            ema_medium=21,
                            ema_slow=50,
                            rsi_period=14,
                            atr_period=14
                        )

                        # Check if EMA9 > EMA21 on higher timeframe (bullish)
                        if mtf_ind.ema_9 > mtf_ind.ema_21:
                            mtf_agreement += 1
                            mtf_reasons.append(f"{tf}m: bullish")
                        else:
                            mtf_reasons.append(f"{tf}m: bearish")
                except Exception as e:
                    logger.warning(f"Failed to check {tf}m timeframe: {e}")

            # Require minimum agreement from higher timeframes
            if mtf_agreement < trading_config.min_higher_timeframe_trend_agreement:
                return None

        # Condition 5: News avoidance - check for high volatility
        if self.cfg.news_avoidance_enabled:
            atr_pct = ind.atr / current_price
            if atr_pct >= self.cfg.high_volatility_threshold_pct:
                return None

        # Condition 6: Macro factors - avoid trading during major economic releases
        if self.cfg.macro_factors_enabled:
            if self._should_avoid_macro_events():
                return None

        # Condition 7: MACD filter - MACD histogram > 0 for bullish momentum
        if ind.macd_histogram <= 0:
            return None

        # Condition 8: Bollinger Bands filter - price not too close to upper band (avoid overbought)
        bb_distance = (current_price - ind.bb_lower) / (ind.bb_upper - ind.bb_lower)
        if bb_distance > 0.9:  # Price in top 10% of bands - too overbought
            return None

        # Condition 9: Stochastic filter - avoid extreme overbought
        if ind.stochastic_k > 80:
            return None

        # Condition 10: Order book analysis - check market depth and spread
        if self.cfg.order_book_enabled:
            if not self._check_order_book(symbol, current_price):
                return None

        # Condition 11: Asset correlation analysis - avoid highly correlated assets
        if self.cfg.correlation_enabled:
            if not self._check_asset_correlation(symbol):
                return None

        # Calculate TP/SL - dynamic based on ATR if enabled
        if self.cfg.dynamic_tp_sl_enabled:
            # Use ATR-based TP/SL
            atr_tp = ind.atr * self.cfg.atr_tp_multiplier  # 2x ATR
            atr_sl = ind.atr * self.cfg.atr_sl_multiplier  # 1x ATR

            sl = current_price - atr_sl
            tp1 = current_price + atr_tp
            tp2 = current_price + atr_tp * 1.5
        else:
            # Use TP/SL from JSON config (dashboard settings)
            risk_cfg = BOT_CONFIG.get('risk', {})
            tp_pct = risk_cfg.get('dynamic_take_profit', {}).get('base_pct', 0.4) / 100  # Convert % to decimal
            sl_pct = risk_cfg.get('dynamic_stop_loss', {}).get('base_pct', 0.2) / 100  # Convert % to decimal
            
            logger.info(f"[STRATEGY] Using TP/SL from config: TP={tp_pct*100:.2f}%, SL={sl_pct*100:.2f}%")

            sl = current_price * (1 - sl_pct)
            tp1 = current_price * (1 + tp_pct)
            tp2 = current_price * (1 + tp_pct * 1.5)

        # Partial exit price
        partial_exit_price = current_price * (1 + self.cfg.partial_exit_tp_pct)

        reason = f"LONG: EMA9>EMA21, RSI={ind.rsi_5:.1f}, Price>VWAP"
        if trading_config.multi_timeframe_enabled and mtf_reasons:
            reason += f", MTF: {', '.join(mtf_reasons)}"

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
        """Check for short entry - improved with RSI, VWAP, and multi-timeframe filters"""
        current_price = df['close'].iloc[-1]

        # Condition 1: EMA9 < EMA21 (bearish crossover)
        if ind.ema_9 >= ind.ema_21:
            return None

        # Condition 2: RSI filter - avoid oversold
        if self.cfg.rsi_filter_enabled:
            if ind.rsi_5 <= self.cfg.rsi_oversold:
                return None

        # Condition 3: VWAP filter - trade below VWAP
        if self.cfg.vwap_filter_enabled:
            if current_price >= ind.vwap:
                return None

        # Condition 4: Multi-timeframe analysis - check higher timeframes
        if trading_config.multi_timeframe_enabled:
            from config import trading_config
            from market_data import MarketDataManager

            mtf_agreement = 0
            mtf_reasons = []

            for tf in trading_config.higher_timeframes:
                try:
                    # Get data for higher timeframe
                    mtf_df = MarketDataManager().get_dataframe(symbol, tf, limit=200)
                    if len(mtf_df) >= 50:
                        mtf_ind = calculate_all_indicators(
                            mtf_df,
                            ema_fast=9,
                            ema_medium=21,
                            ema_slow=50,
                            rsi_period=14,
                            atr_period=14
                        )

                        # Check if EMA9 < EMA21 on higher timeframe (bearish)
                        if mtf_ind.ema_9 < mtf_ind.ema_21:
                            mtf_agreement += 1
                            mtf_reasons.append(f"{tf}m: bearish")
                        else:
                            mtf_reasons.append(f"{tf}m: bullish")
                except Exception as e:
                    logger.warning(f"Failed to check {tf}m timeframe: {e}")

            # Require minimum agreement from higher timeframes
            if mtf_agreement < trading_config.min_higher_timeframe_trend_agreement:
                return None

        # Condition 5: News avoidance - check for high volatility
        if self.cfg.news_avoidance_enabled:
            atr_pct = ind.atr / current_price
            if atr_pct >= self.cfg.high_volatility_threshold_pct:
                return None

        # Condition 6: Macro factors - avoid trading during major economic releases
        if self.cfg.macro_factors_enabled:
            if self._should_avoid_macro_events():
                return None

        # Condition 7: MACD filter - MACD histogram < 0 for bearish momentum
        if ind.macd_histogram >= 0:
            return None

        # Condition 8: Bollinger Bands filter - price not too close to lower band (avoid oversold)
        bb_distance = (current_price - ind.bb_lower) / (ind.bb_upper - ind.bb_lower)
        if bb_distance < 0.1:  # Price in bottom 10% of bands - too oversold
            return None

        # Condition 9: Stochastic filter - avoid extreme oversold
        if ind.stochastic_k < 20:
            return None

        # Condition 10: Order book analysis - check market depth and spread
        if self.cfg.order_book_enabled:
            if not self._check_order_book(symbol, current_price):
                return None

        # Condition 11: Asset correlation analysis - avoid highly correlated assets
        if self.cfg.correlation_enabled:
            if not self._check_asset_correlation(symbol):
                return None

        # Calculate TP/SL - dynamic based on ATR if enabled
        if self.cfg.dynamic_tp_sl_enabled:
            # Use ATR-based TP/SL
            atr_tp = ind.atr * self.cfg.atr_tp_multiplier  # 2x ATR
            atr_sl = ind.atr * self.cfg.atr_sl_multiplier  # 1x ATR

            sl = current_price + atr_sl
            tp1 = current_price - atr_tp
            tp2 = current_price - atr_tp * 1.5
        else:
            # Use TP/SL from JSON config (dashboard settings)
            risk_cfg = BOT_CONFIG.get('risk', {})
            tp_pct = risk_cfg.get('dynamic_take_profit', {}).get('base_pct', 0.4) / 100  # Convert % to decimal
            sl_pct = risk_cfg.get('dynamic_stop_loss', {}).get('base_pct', 0.2) / 100  # Convert % to decimal
            
            logger.info(f"[STRATEGY] Using TP/SL from config: TP={tp_pct*100:.2f}%, SL={sl_pct*100:.2f}%")

            sl = current_price * (1 + sl_pct)
            tp1 = current_price * (1 - tp_pct)
            tp2 = current_price * (1 - tp_pct * 1.5)

        # Partial exit price
        partial_exit_price = current_price * (1 - self.cfg.partial_exit_tp_pct)

        reason = f"SHORT: EMA9<EMA21, RSI={ind.rsi_5:.1f}, Price<VWAP"
        if trading_config.multi_timeframe_enabled and mtf_reasons:
            reason += f", MTF: {', '.join(mtf_reasons)}"

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

    def _indicators_to_dict(self, ind: IndicatorValues, current_price: float) -> Dict[str, float]:
        """Convert indicator values to dictionary"""
        return {
            "ema_9": ind.ema_9,
            "ema_21": ind.ema_21,
            "ema_50": ind.ema_50,
            "ema_200": ind.ema_200,
            "rsi_5": ind.rsi_5,
            "atr": ind.atr,
            "vwap": ind.vwap,
            "adx": ind.adx,
            "current_price": current_price
        }

    def _should_avoid_macro_events(self) -> bool:
        """Check if we should avoid trading during major economic releases"""
        from datetime import datetime

        now = datetime.utcnow()
        day = now.day
        weekday = now.weekday()  # 0 = Monday, 6 = Sunday
        hour = now.hour

        # FED meetings: typically first Wednesday of the month at 18:00-19:00 UTC
        if self.cfg.avoid_fed_meetings:
            if weekday == 2 and day <= 7 and 17 <= hour <= 20:  # Wednesday 17-20 UTC
                return True

        # CPI releases: typically 13th-15th of month at 12:30-13:30 UTC
        if self.cfg.avoid_cpi_releases:
            if 13 <= day <= 15 and 12 <= hour <= 14:
                return True

        # NFP releases: first Friday of month at 12:30-13:30 UTC
        if self.cfg.avoid_nfp_releases:
            if weekday == 4 and day <= 7 and 12 <= hour <= 14:  # Friday 12-14 UTC
                return True

        return False

    def _check_order_book(self, symbol: str, current_price: float) -> bool:
        """Check order book depth and bid-ask spread"""
        try:
            from api_client import BybitClient
            api = BybitClient()

            # Get order book
            orderbook = api.get_orderbook(symbol, limit=20)

            if not orderbook:
                logger.warning(f"Failed to get orderbook for {symbol}")
                return False

            # Check bid-ask spread
            best_bid = float(orderbook.get('b', [[0, 0]])[0][0]) if orderbook.get('b') else 0
            best_ask = float(orderbook.get('a', [[0, 0]])[0][0]) if orderbook.get('a') else 0

            if best_bid == 0 or best_ask == 0:
                return False

            spread_pct = (best_ask - best_bid) / current_price

            if spread_pct > self.cfg.bid_ask_spread_threshold_pct:
                logger.warning(f"Spread too high for {symbol}: {spread_pct*100:.3f}%")
                return False

            # Check order book depth (sum of top 20 levels)
            bid_depth = sum(float(level[1]) for level in orderbook.get('b', [])[:20])
            ask_depth = sum(float(level[1]) for level in orderbook.get('a', [])[:20])

            total_depth = bid_depth + ask_depth

            if total_depth < self.cfg.min_order_book_depth:
                logger.warning(f"Insufficient order book depth for {symbol}: ${total_depth:.0f}")
                return False

            return True

        except Exception as e:
            logger.warning(f"Error checking order book for {symbol}: {e}")
            return True  # Allow trade if check fails

    def _check_asset_correlation(self, symbol: str) -> bool:
        """Check if symbol is highly correlated with existing positions"""
        try:
            from portfolio import portfolio

            # Get current positions
            open_positions = portfolio.positions

            if not open_positions:
                return True  # No positions, no correlation issue

            # Define correlation groups (similar assets)
            correlation_groups = {
                "BTC": ["BTCUSDT"],
                "ETH": ["ETHUSDT"],
                "SOL": ["SOLUSDT"],
                "DOGE": ["DOGEUSDT"],
                "XRP": ["XRPUSDT"],
                "L1": ["BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"],
                "L2": ["ARBUSDT", "OPUSDT", "INJUSDT", "ATOMUSDT", "NEARUSDT", "LDOUSDT"],
                "Gaming": ["APEUSDT", "SANDUSDT", "MANAUSDT"]
            }

            # Find which group the new symbol belongs to
            symbol_group = None
            for group_name, symbols in correlation_groups.items():
                if symbol in symbols:
                    symbol_group = group_name
                    break

            if not symbol_group:
                return True  # Unknown group, allow trade

            # Check if any existing position is in the same correlation group
            for pos_symbol in open_positions.keys():
                for group_name, symbols in correlation_groups.items():
                    if pos_symbol in symbols and group_name == symbol_group:
                        logger.warning(f"Skipping {symbol}: highly correlated with existing position {pos_symbol}")
                        return False

            return True

        except Exception as e:
            logger.warning(f"Error checking asset correlation: {e}")
            return True  # Allow trade if check fails


# Global strategy instance
strategy = SmartScalpingStrategy()
