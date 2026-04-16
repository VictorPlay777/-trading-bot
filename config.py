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
    """Trading parameters - Professional mode"""
    # Bot name
    bot_name: str = "Pro Trading Bot"  # Default bot name

    # Symbol settings
    symbol: str = "BTCUSDT"
    symbols: List[str] = None  # For multi-symbol trading
    category: str = "linear"  # Linear futures (with leverage and funding fees)

    # Timeframes
    timeframe: str = "1"  # Default timeframe (for backward compatibility)
    main_timeframe: str = "1"  # 1 minute for entries
    context_timeframe: str = "5"  # 5 minutes for trend context
    higher_timeframes: List[str] = None  # Higher timeframes for trend confirmation (15m, 1h)

    # Multi-timeframe analysis settings
    multi_timeframe_enabled: bool = True  # Enable multi-timeframe analysis
    min_higher_timeframe_trend_agreement: int = 1  # Minimum number of higher timeframes that must agree

    # Position limits - professional mode
    max_positions: int = 8  # Max 8 positions (focused trading)
    max_daily_trades: int = 50  # Max 50 trades per day (avoid overtrading)

    # Template/preset selection (persistent)
    selected_template: str = "professional"  # Default: professional mode

    # Leverage (for futures) - professional mode with conservative leverage
    max_leverage: int = 20  # Max 20x leverage (professional)
    default_leverage: int = 10  # Default 10x leverage
    min_leverage: int = 5  # Min 5x leverage
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

        if self.higher_timeframes is None:
            self.higher_timeframes = ["15", "60"]  # 15m and 1h for trend confirmation

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

    # RSI settings - improved entry logic
    rsi_period: int = 14  # RSI(14) for better signal
    rsi_oversold: int = 30  # More extreme oversold
    rsi_overbought: int = 70  # More extreme overbought
    rsi_filter_enabled: bool = True  # Enable RSI filter

    # ATR settings (volatility filter)
    atr_period: int = 14
    min_atr_pct: float = 0.001  # 0.1% minimum ATR (avoid flat)
    max_atr_pct: float = 0.05  # 5% maximum ATR (avoid chaos)

    # News avoidance settings
    news_avoidance_enabled: bool = True  # Avoid trading during high volatility (news)
    high_volatility_threshold_pct: float = 0.03  # 3% ATR = high volatility (likely news)
    news_hours_utc: List[int] = None  # Hours to avoid (UTC) - major news releases

    # Macro factors settings
    macro_factors_enabled: bool = True  # Enable macro factors filtering
    avoid_fed_meetings: bool = True  # Avoid trading during FED meetings
    avoid_cpi_releases: bool = True  # Avoid trading during CPI releases
    avoid_nfp_releases: bool = True  # Avoid trading during Non-Farm Payroll releases

    # ATR filter for market conditions (anti-sideways)
    atr_filter_enabled: bool = True
    atr_min_threshold_pct: float = 0.002  # 0.2% minimum ATR to trade
    atr_timeframe: str = "5"  # 5m timeframe for ATR filter

    # ADX filter for trend strength - Professional mode (strict)
    adx_filter_enabled: bool = True
    adx_min_threshold: float = 25.0  # ADX < 25 = no trading (only strong trends)
    adx_reverse_threshold: float = 30.0  # ADX > 30 = allow reversal
    adx_period: int = 14
    adx_timeframe: str = "5"  # 5m timeframe for ADX filter

    # EMA trend confirmation - Professional mode (strict)
    ema_filter_enabled: bool = True
    ema_fast_period: int = 50
    ema_slow_period: int = 200
    ema_min_distance_pct: float = 0.01  # 1% minimum distance between EMAs (stronger trend)
    ema_timeframe: str = "5"  # 5m timeframe for EMA filter

    # Volume filter
    volume_filter_enabled: bool = True
    volume_ma_period: int = 20
    volume_min_ratio: float = 1.2  # Current volume must be 1.2x MA volume
    volume_timeframe: str = "5"  # 5m timeframe for volume filter

    # Dynamic TP/SL based on ATR
    dynamic_tp_sl_enabled: bool = True  # Enabled for professional trading
    atr_tp_multiplier: float = 2.0  # TP = 2x ATR
    atr_sl_multiplier: float = 1.0  # SL = 1x ATR
    tp_atr_multiplier: float = 1.5  # TP = ATR * 1.5
    sl_atr_multiplier: float = 0.7  # SL = ATR * 0.7

    # TP/SL settings - percentage-based (decimal format for API) - Professional mode
    tp_pct: float = 0.02  # 2% take profit (professional)
    sl_pct: float = 0.01  # 1% stop loss (professional)

    # Legacy ROI-based settings (deprecated, kept for compatibility)
    tp_roi_pct: float = 0.30  # 30% ROI for take profit (0.6% price with 50x leverage)
    sl_roi_pct: float = 0.10  # 10% ROI for stop loss (0.2% price with 50x leverage)

    # TP/SL settings - price-based (not ROI) - Professional mode
    tp_min_pct: float = 0.01  # 1% minimum TP
    tp_max_pct: float = 0.05  # 5% maximum TP
    sl_min_pct: float = 0.005  # 0.5% minimum SL
    sl_max_pct: float = 0.02  # 2% maximum SL

    # Partial exit settings - Professional mode
    partial_exit_pct: float = 0.5  # 50% partial exit
    partial_exit_tp_pct: float = 0.01  # 1% TP for partial exit
    partial_exit_enabled: bool = True  # Enable partial exit at 1R

    # Trailing stop settings - Professional mode
    trailing_stop_enabled: bool = True  # Enable trailing stop
    trailing_stop_activation_pct: float = 0.015  # Activate trailing stop at 1.5% profit (1.5R)
    trailing_stop_distance_pct: float = 0.005  # Trailing stop distance 0.5% (0.5R)

    # Micro-movement detection
    min_price_change_pct: float = 0.001  # 0.1% minimum price movement

    # Commission check
    min_profit_multiple: float = 2.0  # Profit must be ≥ 2× commission

    # VWAP settings - improved entry logic
    vwap_period: int = 20
    vwap_filter_enabled: bool = True  # Enable VWAP filter

    def update_from_dict(self, data: dict):
        """Update config from dictionary (for API updates)"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    # Confirmation lookback
    confirmation_lookback: int = 2


@dataclass
class RiskConfig:
    """Risk management parameters - Professional mode"""
    # Risk management - professional trading (testing mode - no daily limits)
    risk_per_trade_pct: float = 0.01  # 1% risk per trade ($10k on $1M account)
    max_risk_per_trade_pct: float = 0.02  # 2% maximum risk per trade
    max_daily_loss_pct: float = 1.0  # 100% max daily loss (disabled for testing)
    max_consecutive_losses: int = 9999  # Unlimited consecutive losses (disabled for testing)
    atr_position_scaling: bool = True  # Scale position size by ATR
    max_atr_pct_for_full_size: float = 0.02  # 2% ATR for full position size
    auto_reverse_on_sl: bool = True  # Auto-reverse position on SL closure
    auto_reopen_on_tp: bool = True  # Auto-reopen position on TP closure

    # Position sizing - professional mode (Kelly criterion)
    min_position_size_usd: float = 10000.0  # Minimum position size ($10k USDT)
    max_position_size_usd: float = 200000.0  # Maximum position size ($200k USDT)
    max_position_pct_of_balance: float = 0.05  # Max 5% of balance per position (Kelly criterion)
    kelly_criterion_enabled: bool = True  # Enable Kelly criterion for position sizing
    half_kelly: bool = True  # Use half-Kelly for safety (more conservative)

    # Loss streak protection (disabled for testing)
    max_consecutive_sl: int = 9999  # Unlimited (disabled for testing)
    loss_streak_pause_minutes: int = 0  # No pause (disabled for testing)

    # Trading psychology protection
    fomo_protection_enabled: bool = True  # Prevent FOMO trading
    min_time_between_trades_sec: int = 60  # Minimum time between trades (prevent overtrading)
    revenge_trading_protection: bool = True  # Prevent revenge trading after losses
    max_trades_per_hour: int = 5  # Max trades per hour (prevent overtrading)

    # Order book analysis
    order_book_enabled: bool = True  # Enable order book depth analysis
    min_order_book_depth: float = 100000.0  # Minimum order book depth ($100k)
    bid_ask_spread_threshold_pct: float = 0.001  # 0.1% max spread (avoid illiquid markets)

    # Asset correlation analysis
    correlation_enabled: bool = True  # Enable correlation analysis
    max_correlation_threshold: float = 0.8  # Max correlation to avoid (0.8 = 80%)
    correlation_lookback_days: int = 30  # Days to calculate correlation

    # Risk Parity position sizing
    risk_parity_enabled: bool = True  # Enable Risk Parity position sizing
    risk_parity_lookback_days: int = 30  # Days to calculate volatility for Risk Parity

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
