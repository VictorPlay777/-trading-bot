"""
Technical indicators - EMA, RSI, ATR, ADX, volatility
Pure calculation functions - no side effects
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class IndicatorValues:
    """Container for calculated indicator values"""
    ema_fast: float = 0.0
    ema_medium: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 50.0
    atr: float = 0.0
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    volatility_pct: float = 0.0
    # Smart scalping indicators
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    stochastic_k: float = 50.0
    stochastic_d: float = 50.0
    volume_ratio: float = 1.0
    # New smart scalping indicators
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    rsi_5: float = 50.0
    vwap: float = 0.0


def calculate_ema(prices: np.ndarray, period: int) -> float:
    """Calculate EMA for given price series"""
    if len(prices) < period:
        return prices[-1] if len(prices) > 0 else 0.0
    
    multiplier = 2.0 / (period + 1)
    ema = prices[0]
    
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def calculate_ema_series(prices: np.ndarray, period: int) -> np.ndarray:
    """Calculate full EMA series"""
    if len(prices) < period:
        return prices.copy()
    
    multiplier = 2.0 / (period + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    
    for i in range(1, len(prices)):
        ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
    
    return ema


def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate RSI for given price series"""
    if len(prices) < period + 1:
        return 50.0
    
    # Calculate price changes
    deltas = np.diff(prices)
    
    # Separate gains and losses
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    # Calculate average gains and losses using Wilder's smoothing
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    return rsi


def calculate_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14
) -> Tuple[float, np.ndarray]:
    """Calculate ATR and TR series"""
    if len(highs) < period + 1:
        return 0.0, np.array([])
    
    # Calculate True Range
    tr1 = highs[1:] - lows[1:]  # Current high - current low
    tr2 = np.abs(highs[1:] - closes[:-1])  # Current high - previous close
    tr3 = np.abs(lows[1:] - closes[:-1])  # Current low - previous close
    
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    
    # Calculate ATR using Wilder's smoothing
    atr = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
    
    return atr, tr


def calculate_adx(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14
) -> Tuple[float, float, float]:
    """
    Calculate ADX, +DI, and -DI
    Returns: (adx, plus_di, minus_di)
    """
    if len(highs) < period * 2 + 1:
        return 0.0, 0.0, 0.0
    
    # Calculate directional movements
    plus_dm = np.zeros(len(highs) - 1)
    minus_dm = np.zeros(len(highs) - 1)
    
    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]
        
        if high_diff > low_diff and high_diff > 0:
            plus_dm[i-1] = high_diff
        if low_diff > high_diff and low_diff > 0:
            minus_dm[i-1] = low_diff
    
    # Calculate ATR
    atr, _ = calculate_atr(highs, lows, closes, period)
    
    if atr == 0:
        return 0.0, 0.0, 0.0
    
    # Calculate True Range for smoothing
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    
    # Smooth TR, +DM, -DM using Wilder's method
    smoothed_tr = np.zeros(len(tr))
    smoothed_plus_dm = np.zeros(len(plus_dm))
    smoothed_minus_dm = np.zeros(len(minus_dm))
    
    smoothed_tr[period-1] = np.sum(tr[:period])
    smoothed_plus_dm[period-1] = np.sum(plus_dm[:period])
    smoothed_minus_dm[period-1] = np.sum(minus_dm[:period])
    
    for i in range(period, len(tr)):
        smoothed_tr[i] = smoothed_tr[i-1] - (smoothed_tr[i-1] / period) + tr[i]
        smoothed_plus_dm[i] = smoothed_plus_dm[i-1] - (smoothed_plus_dm[i-1] / period) + plus_dm[i]
        smoothed_minus_dm[i] = smoothed_minus_dm[i-1] - (smoothed_minus_dm[i-1] / period) + minus_dm[i]
    
    # Calculate +DI and -DI (add epsilon to avoid division by zero)
    epsilon = 1e-10
    plus_di = 100 * smoothed_plus_dm / (smoothed_tr + epsilon)
    minus_di = 100 * smoothed_minus_dm / (smoothed_tr + epsilon)
    
    # Calculate DX and ADX
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    
    # Smooth DX to get ADX
    adx = np.mean(dx[period-1:2*period-1])
    for i in range(2*period-1, len(dx)):
        adx = (adx * (period - 1) + dx[i]) / period
    
    return adx, plus_di[-1] if len(plus_di) > 0 else 0.0, minus_di[-1] if len(minus_di) > 0 else 0.0


def calculate_volatility_percentile(
    closes: np.ndarray,
    lookback: int = 50,
    percentile: int = 80
) -> Tuple[float, float, bool]:
    """
    Calculate current volatility percentile
    Returns: (current_vol, threshold, is_extreme)
    """
    if len(closes) < lookback + 1:
        return 0.0, 0.0, False
    
    # Calculate rolling volatility (standard deviation of returns)
    returns = np.diff(closes) / closes[:-1]
    
    # Current volatility (last 5 periods)
    current_vol = np.std(returns[-5:]) if len(returns) >= 5 else np.std(returns)
    
    # Historical volatility distribution
    rolling_vols = []
    for i in range(lookback, len(returns)):
        vol = np.std(returns[i-lookback:i])
        rolling_vols.append(vol)
    
    if not rolling_vols:
        return current_vol, 0.0, False
    
    threshold = np.percentile(rolling_vols, percentile)
    is_extreme = current_vol > threshold
    
    return current_vol, threshold, is_extreme


def calculate_macd(
    prices: np.ndarray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[float, float, float]:
    """
    Calculate MACD, Signal, and Histogram
    Returns: (macd, signal, histogram)
    """
    if len(prices) < slow_period + signal_period:
        return 0.0, 0.0, 0.0

    # Calculate EMAs
    ema_fast = calculate_ema_series(prices, fast_period)
    ema_slow = calculate_ema_series(prices, slow_period)

    # MACD line
    macd = ema_fast - ema_slow

    # Signal line (EMA of MACD)
    signal = calculate_ema_series(macd, signal_period)

    # Histogram
    histogram = macd - signal

    return macd[-1], signal[-1], histogram[-1]


def calculate_bollinger_bands(
    prices: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[float, float, float, float]:
    """
    Calculate Bollinger Bands
    Returns: (upper, middle, lower, width)
    """
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1], 0.0

    # Middle band (SMA)
    middle = np.mean(prices[-period:])

    # Standard deviation
    std = np.std(prices[-period:])

    # Upper and lower bands
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    # Band width (percentage)
    width = (upper - lower) / middle * 100

    return upper, middle, lower, width


def calculate_stochastic(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    k_period: int = 14,
    d_period: int = 3
) -> Tuple[float, float]:
    """
    Calculate Stochastic Oscillator
    Returns: (%K, %D)
    """
    if len(closes) < k_period:
        return 50.0, 50.0

    # Calculate %K
    lowest_low = np.min(lows[-k_period:])
    highest_high = np.max(highs[-k_period:])

    if highest_high == lowest_low:
        k = 50.0
    else:
        k = 100 * (closes[-1] - lowest_low) / (highest_high - lowest_low)

    # Calculate %D (SMA of %K)
    # We need historical %K values, so we'll use a simplified version
    d = k  # Simplified - in production, use full %K series

    return k, d


def calculate_vwap(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int = 14
) -> float:
    """
    Calculate Volume Weighted Average Price (VWAP)
    Returns: VWAP value
    """
    if len(closes) < period or len(volumes) < period:
        return closes[-1] if len(closes) > 0 else 0.0

    # Calculate typical price: (high + low + close) / 3
    typical_prices = (highs[-period:] + lows[-period:] + closes[-period:]) / 3

    # Calculate VWAP: sum(typical_price * volume) / sum(volume)
    vwap = np.sum(typical_prices * volumes[-period:]) / np.sum(volumes[-period:])

    return vwap


def calculate_all_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_medium: int = 50,
    ema_slow: int = 200,
    rsi_period: int = 14,
    atr_period: int = 14,
    adx_period: int = 14,
    ema_9: int = 9,
    ema_21: int = 21,
    ema_50: int = 50,
    rsi_5_period: int = 5,
    vwap_period: int = 14
) -> IndicatorValues:
    """Calculate all indicators from DataFrame"""
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values

    values = IndicatorValues()

    # EMAs (legacy)
    values.ema_fast = calculate_ema(closes, ema_fast)
    values.ema_medium = calculate_ema(closes, ema_medium)
    values.ema_slow = calculate_ema(closes, ema_slow)

    # EMAs (smart scalping)
    values.ema_9 = calculate_ema(closes, ema_9)
    values.ema_21 = calculate_ema(closes, ema_21)
    values.ema_50 = calculate_ema(closes, ema_50)

    # RSI (legacy)
    values.rsi = calculate_rsi(closes, rsi_period)

    # RSI (smart scalping)
    values.rsi_5 = calculate_rsi(closes, rsi_5_period)

    # ATR
    values.atr, _ = calculate_atr(highs, lows, closes, atr_period)

    # ADX
    values.adx, values.plus_di, values.minus_di = calculate_adx(
        highs, lows, closes, adx_period
    )

    # Volatility
    vol, threshold, _ = calculate_volatility_percentile(closes)
    values.volatility_pct = vol * 100  # As percentage

    # Smart scalping indicators
    # MACD
    values.macd, values.macd_signal, values.macd_histogram = calculate_macd(closes)

    # Bollinger Bands
    values.bb_upper, values.bb_middle, values.bb_lower, values.bb_width = calculate_bollinger_bands(closes)

    # Stochastic
    values.stochastic_k, values.stochastic_d = calculate_stochastic(highs, lows, closes)

    # VWAP (if volume column exists)
    if 'volume' in df.columns:
        volumes = df['volume'].values
        values.vwap = calculate_vwap(highs, lows, closes, volumes, vwap_period)

        # Volume ratio
        if len(volumes) > 20:
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:])
            values.volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    else:
        # Fallback if no volume data
        values.vwap = closes[-1]

    return values


def get_ema_alignment(
    ema_fast: float,
    ema_medium: float,
    ema_slow: float,
    price: float
) -> Dict[str, any]:
    """
    Check EMA alignment for trend confirmation
    Returns alignment info
    """
    bullish_alignment = ema_fast > ema_medium > ema_slow and price > ema_slow
    bearish_alignment = ema_fast < ema_medium < ema_slow and price < ema_slow
    
    return {
        "bullish_aligned": bullish_alignment,
        "bearish_aligned": bearish_alignment,
        "above_ema200": price > ema_slow,
        "ema20_above_50": ema_fast > ema_medium,
        "trend_strength": abs(ema_fast - ema_medium) / ema_medium * 100
    }


def detect_whipsaw(
    prices: np.ndarray,
    ema_fast_period: int = 20,
    lookback: int = 20,
    threshold: int = 4
) -> bool:
    """
    Detect if market is whipsawing around EMA
    (frequent crosses indicating chop)
    """
    if len(prices) < lookback + ema_fast_period:
        return False
    
    ema_series = calculate_ema_series(prices, ema_fast_period)
    
    # Count EMA crosses in lookback period
    crosses = 0
    above_ema = prices[0] > ema_series[0]
    
    for i in range(1, min(lookback, len(prices))):
        current_above = prices[i] > ema_series[i]
        if current_above != above_ema:
            crosses += 1
            above_ema = current_above
    
    return crosses >= threshold
