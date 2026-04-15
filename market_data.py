"""
Market data manager - handles candles, caching, and data preprocessing
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from api_client import BybitClient
from logger import get_logger, log_event
from config import trading_config

logger = get_logger()


@dataclass
class Candle:
    """OHLCV candle data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def body(self) -> float:
        return abs(self.close - self.open)
    
    @property
    def range(self) -> float:
        return self.high - self.low
    
    @property
    def is_bullish(self) -> bool:
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


class MarketDataCache:
    """Cache for market data with automatic refresh"""
    
    def __init__(self, max_cache_minutes: int = 5):
        self._klines_cache: Dict[str, Dict] = {}  # symbol -> {timestamp, data}
        self._price_cache: Dict[str, Dict] = {}
        self._max_age = timedelta(minutes=max_cache_minutes)
    
    def get_cached_klines(self, symbol: str, interval: str) -> Optional[List[Candle]]:
        """Get cached klines if not expired"""
        key = f"{symbol}_{interval}"
        if key in self._klines_cache:
            cached = self._klines_cache[key]
            age = datetime.utcnow() - cached["timestamp"]
            if age < self._max_age:
                return cached["data"]
        return None
    
    def set_klines_cache(self, symbol: str, interval: str, data: List[Candle]):
        """Cache klines data"""
        key = f"{symbol}_{interval}"
        self._klines_cache[key] = {
            "timestamp": datetime.utcnow(),
            "data": data
        }
    
    def clear_cache(self, symbol: Optional[str] = None):
        """Clear cache for symbol or all"""
        if symbol:
            keys_to_remove = [k for k in self._klines_cache if k.startswith(symbol)]
            for key in keys_to_remove:
                del self._klines_cache[key]
        else:
            self._klines_cache.clear()


class MarketDataManager:
    """Manages all market data operations"""
    
    def __init__(self, api_client: BybitClient):
        self.api = api_client
        self.cache = MarketDataCache()
        self._last_prices: Dict[str, float] = {}
    
    def get_klines(
        self,
        symbol: str = None,
        interval: str = None,
        limit: int = 200,
        use_cache: bool = True
    ) -> List[Candle]:
        """Get OHLCV candles"""
        symbol = symbol or trading_config.symbol
        interval = interval or trading_config.timeframe
        
        # Try cache first
        if use_cache:
            cached = self.cache.get_cached_klines(symbol, interval)
            if cached:
                return cached
        
        # Fetch from API
        try:
            klines = self.api.get_klines(symbol, interval, limit)
            
            # Convert to Candle objects (Bybit returns [timestamp, open, high, low, close, volume, turnover])
            candles = []
            for k in reversed(klines):  # API returns newest first, reverse to get oldest first
                candle = Candle(
                    timestamp=datetime.fromtimestamp(int(k[0]) / 1000),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5])
                )
                candles.append(candle)
            
            # Update cache
            self.cache.set_klines_cache(symbol, interval, candles)
            
            # Update last price
            if candles:
                self._last_prices[symbol] = candles[-1].close
            
            log_event("debug", f"Fetched {len(candles)} candles for {symbol}", 
                      symbol=symbol, interval=interval, count=len(candles))
            
            return candles
            
        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            raise
    
    def get_latest_price(self, symbol: str = None) -> float:
        """Get latest price"""
        symbol = symbol or trading_config.symbol
        
        # Try cache first
        cached = self.cache.get_cached_klines(symbol, trading_config.timeframe)
        if cached:
            return cached[-1].close
        
        # Fetch from API
        try:
            price = self.api.get_latest_price(symbol)
            self._last_prices[symbol] = price
            return price
        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            # Return last known price if available
            return self._last_prices.get(symbol, 0.0)
    
    def get_dataframe(
        self,
        symbol: str = None,
        interval: str = None,
        limit: int = 200
    ) -> pd.DataFrame:
        """Get candles as pandas DataFrame"""
        candles = self.get_klines(symbol, interval, limit)
        
        data = {
            'timestamp': [c.timestamp for c in candles],
            'open': [c.open for c in candles],
            'high': [c.high for c in candles],
            'low': [c.low for c in candles],
            'close': [c.close for c in candles],
            'volume': [c.volume for c in candles]
        }
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    def get_atr(self, candles: List[Candle], period: int = 14) -> float:
        """Calculate Average True Range from candles"""
        if len(candles) < period + 1:
            return 0.0
        
        tr_values = []
        for i in range(1, len(candles)):
            high_low = candles[i].high - candles[i].low
            high_close = abs(candles[i].high - candles[i-1].close)
            low_close = abs(candles[i].low - candles[i-1].close)
            tr = max(high_low, high_close, low_close)
            tr_values.append(tr)
        
        # Use Wilder's smoothing
        atr = np.mean(tr_values[-period:])
        return atr
    
    def refresh_cache(self, symbol: str = None):
        """Force refresh cache"""
        symbol = symbol or trading_config.symbol
        self.cache.clear_cache(symbol)
        self.get_klines(symbol, use_cache=False)
        log_event("info", f"Cache refreshed for {symbol}", symbol=symbol)
    
    def get_market_structure(
        self,
        symbol: str = None,
        lookback: int = 50
    ) -> Dict[str, Any]:
        """Get current market structure info"""
        candles = self.get_klines(symbol, limit=lookback)
        
        if len(candles) < 20:
            return {"error": "Insufficient data"}
        
        latest = candles[-1]
        
        # Calculate recent volatility
        returns = [abs(candles[i].close - candles[i-1].close) / candles[i-1].close 
                   for i in range(1, len(candles))]
        avg_volatility = np.mean(returns[-20:]) if len(returns) >= 20 else np.mean(returns)
        
        return {
            "latest_price": latest.close,
            "daily_range": latest.high - latest.low,
            "atr": self.get_atr(candles),
            "avg_volatility_20": avg_volatility,
            "trend_direction": "up" if candles[-1].close > candles[-20].close else "down",
            "volume_profile": sum(c.volume for c in candles[-10:]) / 10
        }
