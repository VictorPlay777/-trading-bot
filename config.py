"""
Centralized configuration for Bybit Futures Trading Bot
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class APIConfig:
    """Bybit API configuration"""
    key: str = os.getenv("BYBIT_API_KEY", "rRsm08OPN027nk5hgF")
    secret: str = os.getenv("BYBIT_API_SECRET", "GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA")
    base_url: str = os.getenv("BYBIT_BASE_URL", "https://api-demo.bybit.com")
    recv_window: int = 30000  # 30 seconds to fix timestamp sync issues
    testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"


@dataclass
class TradingConfig:
    """Trading parameters"""
    # Bot name
    bot_name: str = "ChatGPT Bot"  # Default bot name

    # Symbol settings
    symbol: str = "BTCUSDT"
    symbols: List[str] = None  # For multi-symbol trading
    category: str = "linear"  # Linear futures (with leverage and funding fees)

    # Timeframes
    timeframe: str = "1"  # Default timeframe (for backward compatibility)
    main_timeframe: str = "1"  # 1 minute for entries
    context_timeframe: str = "5"  # 5 minutes for trend context

    # Position limits
    max_positions: int = 20  # Max 20 positions for 20 coins (mad mode)
    max_daily_trades: int = 999999  # Unlimited trades

    # Template/preset selection (persistent)
    selected_template: str = "mad"  # Default: mad mode

    # Leverage (for futures) - mad mode with max leverage
    max_leverage: int = 100  # Max 100x leverage (mad mode)
    default_leverage: int = 50  # Default 50x leverage
    min_leverage: int = 10  # Min 10x leverage
    leverage_scaling: bool = True  # Scale leverage based on volatility

    # Symbol-specific max leverage (Bybit limits)
    symbol_max_leverage: Dict[str, int] = None

    # Demo account reset settings
    default_demo_balance: float = 2000000.0  # 2M USDT default
    balance_reset_increment: float = 100000.0  # Bybit allows 100k increments

    def update_from_dict(self, data: dict):
        """Update config from dictionary (for API updates)"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT",
                "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
                "ARBUSDT", "OPUSDT", "INJUSDT", "ATOMUSDT",
                "NEARUSDT", "LDOUSDT", "APEUSDT", "SANDUSDT", "MANAUSDT"
            ]  # 18 volatile futures pairs (removed MATICUSDT - closed contract)

        if self.symbol_max_leverage is None:
            self.symbol_max_leverage = {
                "BTCUSDT": 100,
                "ETHUSDT": 100,
                "SOLUSDT": 100,
                "DOGEUSDT": 75,
                "XRPUSDT": 75,
                "BNBUSDT": 75,
                "ADAUSDT": 75,
                "AVAXUSDT": 75,
                "LINKUSDT": 75,
                "DOTUSDT": 75,
                "ARBUSDT": 75,
                "OPUSDT": 75,
                "INJUSDT": 75,
                "ATOMUSDT": 75,
                "NEARUSDT": 75,
                "LDOUSDT": 75,
                "APEUSDT": 75,
                "SANDUSDT": 75,
                "MANAUSDT": 25,  # Max 25x due to risk limit
            }


@dataclass
class RegimeConfig:
    """Market regime detection parameters"""
    # ADX thresholds (lowered for ultra-aggressive trading)
    adx_trend_threshold: float = 5.0  # Very low - trade even in weak trends
    adx_chop_threshold: float = 3.0
    adx_period: int = 14
    
    # EMA periods
    ema_fast: int = 20
    ema_medium: int = 50
    ema_slow: int = 200
    
    # Trend confirmation
    min_trend_bars: int = 3  # Bars required for trend confirmation
    chop_lookback: int = 20  # Bars to check for whipsaw


@dataclass
class StrategyConfig:
    """Strategy parameters - Smart Scalping"""
    # General strategy settings
    max_long_positions: int = 3
    max_short_positions: int = 3

    # EMA settings - smart scalping
    ema_fast_period: int = 9  # EMA9 (micro-impulse)
    ema_medium_period: int = 21  # EMA21 (entry trigger)
    ema_slow_period: int = 50  # EMA50 (5m context)

    # RSI settings - smart scalping
    rsi_period: int = 5  # RSI(5) for fast reaction
    rsi_oversold: int = 40
    rsi_overbought: int = 60

    # ATR settings (volatility filter)
    atr_period: int = 14
    min_atr_pct: float = 0.001  # 0.1% minimum ATR (avoid flat)
    max_atr_pct: float = 0.05  # 5% maximum ATR (avoid chaos)

    # ATR filter for market conditions (anti-sideways)
    atr_filter_enabled: bool = True
    atr_min_threshold_pct: float = 0.002  # 0.2% minimum ATR to trade
    atr_timeframe: str = "5"  # 5m timeframe for ATR filter

    # ADX filter for trend strength
    adx_filter_enabled: bool = True
    adx_min_threshold: float = 20.0  # ADX < 20 = no trading (flat market)
    adx_reverse_threshold: float = 25.0  # ADX > 25 = allow reversal
    adx_period: int = 14
    adx_timeframe: str = "5"  # 5m timeframe for ADX filter

    # EMA trend confirmation
    ema_filter_enabled: bool = True
    ema_fast_period: int = 50
    ema_slow_period: int = 200
    ema_min_distance_pct: float = 0.005  # 0.5% minimum distance between EMAs
    ema_timeframe: str = "5"  # 5m timeframe for EMA filter

    # Volume filter
    volume_filter_enabled: bool = True
    volume_ma_period: int = 20
    volume_min_ratio: float = 1.2  # Current volume must be 1.2x MA volume
    volume_timeframe: str = "5"  # 5m timeframe for volume filter

    # Dynamic TP/SL based on ATR
    dynamic_tp_sl_enabled: bool = False  # Disabled by default, use fixed TP/SL
    tp_atr_multiplier: float = 1.5  # TP = ATR * 1.5
    sl_atr_multiplier: float = 0.7  # SL = ATR * 0.7

    # TP/SL settings - percentage-based (decimal format for API)
    tp_pct: float = 0.004  # 0.4% take profit
    sl_pct: float = 0.0015  # 0.15% stop loss

    # Legacy ROI-based settings (deprecated, kept for compatibility)
    tp_roi_pct: float = 0.30  # 30% ROI for take profit (0.6% price with 50x leverage)
    sl_roi_pct: float = 0.10  # 10% ROI for stop loss (0.2% price with 50x leverage)

    # TP/SL settings - price-based (not ROI)
    tp_min_pct: float = 0.002  # 0.2% minimum TP
    tp_max_pct: float = 0.008  # 0.8% maximum TP
    sl_min_pct: float = 0.0025  # 0.25% minimum SL
    sl_max_pct: float = 0.005  # 0.5% maximum SL

    # Partial exit settings
    partial_exit_pct: float = 0.5  # 50% partial exit
    partial_exit_tp_pct: float = 0.0025  # 0.25% TP for partial exit

    # Micro-movement detection
    min_price_change_pct: float = 0.001  # 0.1% minimum price movement

    # Commission check
    min_profit_multiple: float = 2.0  # Profit must be ≥ 2× commission

    # VWAP settings
    vwap_period: int = 20

    def update_from_dict(self, data: dict):
        """Update config from dictionary (for API updates)"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    # Confirmation lookback
    confirmation_lookback: int = 2


@dataclass
class RiskConfig:
    """Risk management parameters"""
    # Risk management - smart scalping
    risk_per_trade_pct: float = 1.0  # 100% risk per trade (disabled, TP/SL controls risk)
    max_risk_per_trade_pct: float = 1.0  # 100% maximum risk per trade (disabled)
    max_daily_loss_pct: float = 1.0  # 100% max daily loss (disabled, won't trigger)
    max_consecutive_losses: int = 9999  # Very high limit (effectively disabled)
    atr_position_scaling: bool = True  # Scale position size by ATR
    max_atr_pct_for_full_size: float = 0.02  # 2% ATR for full position size
    auto_reverse_on_sl: bool = True  # Auto-reverse position on SL closure
    auto_reopen_on_tp: bool = True  # Auto-reopen position on TP closure

    # Position sizing
    min_position_size_usd: float = 100000.0  # Minimum position size (100k USDT) for mad mode
    max_position_size_usd: float = 5000000.0  # Maximum position size (5M USDT)
    max_position_pct_of_balance: float = 0.5  # Max 50% of balance per position

    # Loss streak protection
    max_consecutive_sl: int = 3  # Pause after 3 consecutive SLs
    loss_streak_pause_minutes: int = 30  # Pause for 30 minutes after loss streak

    def update_from_dict(self, data: dict):
        """Update config from dictionary (for API updates)"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class FeeConfig:
    """Fee structure - realistic model"""
    maker_fee: float = 0.0002  # 0.02% per side
    taker_fee: float = 0.00055  # 0.055% per side
    round_trip_maker: float = 0.0004  # 0.04% round trip
    round_trip_taker: float = 0.0011  # 0.11% round trip
    funding_interval_hours: int = 8
    estimated_funding_8h: float = 0.0001  # 0.01% per 8h (conservative)


@dataclass
class ExecutionConfig:
    """Execution parameters"""
    order_timeout_sec: int = 30
    max_retries: int = 3
    retry_delay_sec: float = 1.0

    # Order type preferences
    entry_order_type: str = "Market"  # Market for quick entry
    exit_order_type: str = "Limit"   # Limit for better exit

    # Confirmation
    require_position_confirmation: bool = True
    confirmation_timeout_sec: int = 5

    # Trade delay to reduce overtrading
    min_trade_delay_sec: int = 10  # Minimum 10 seconds between trades


@dataclass
class LoggingConfig:
    """Logging configuration"""
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: str = "logs"
    max_log_size_mb: int = 10
    backup_count: int = 5
    
    # Trade log CSV
    trade_log_csv: str = "logs/trades.csv"


# Global config instances
api_config = APIConfig()
trading_config = TradingConfig()
regime_config = RegimeConfig()
strategy_config = StrategyConfig()
risk_config = RiskConfig()
fee_config = FeeConfig()
execution_config = ExecutionConfig()
logging_config = LoggingConfig()
