import asyncio
import aiohttp
import json
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DataLevel(Enum):
    """Data readiness level for progressive strategy switching."""
    RAW = 0      # Only live price + volume + orderbook
    BASIC = 1     # Add short EMA / momentum
    FULL = 2      # ATR, volatility filters, full strategy


class MarketDataEngine:
    """
    Market data ingestion using REST API (simpler and more reliable).
    Supports progressive data loading with data levels.
    """
    
    def __init__(self, symbols: List[str], config: dict):
        self.symbols = symbols
        self.config = config
        self.base_url = "https://api.bybit.com/v5"
        
        # Data storage
        self.current_prices: Dict[str, float] = {}
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.volumes: Dict[str, float] = {}
        self.last_update: Dict[str, float] = {}
        
        # Data levels - track readiness per symbol
        self.data_levels: Dict[str, DataLevel] = {}
        self.ema_short: Dict[str, float] = {}  # 9-period EMA
        self.momentum: Dict[str, float] = {}    # Short-term momentum
        self.atr: Dict[str, float] = {}         # ATR for FULL level
        
        # REST API session
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.update_interval = 1  # Update every second
        
        # Callbacks
        self.on_trade_callback = None
        self.on_orderbook_callback = None
        
    async def start(self):
        """Initialize HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def stop(self):
        """Stop the market data engine."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("Market data engine stopped")
        
    async def connect(self):
        """Start periodic data fetching."""
        self.running = True
        await self.start()
        
        logger.info(f"Starting REST API data fetching for {len(self.symbols)} symbols...")
        
        while self.running:
            try:
                await self._fetch_all_data()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                await asyncio.sleep(5)
                
    async def _fetch_all_data(self, symbols_subset: List[str] = None):
        """Fetch data for symbols (or all if subset not provided)."""
        symbols_to_fetch = symbols_subset if symbols_subset else self.symbols
        # Split into batches to avoid rate limits
        batch_size = 20
        for i in range(0, len(symbols_to_fetch), batch_size):
            batch = symbols_to_fetch[i:i+batch_size]
            await self._fetch_batch(batch)
            
    async def _fetch_batch(self, symbols: List[str]):
        """Fetch historical candles for a batch of symbols."""
        try:
            # Fetch historical klines for each symbol in batch
            for symbol in symbols:
                async with self.session.get(f"{self.base_url}/market/kline?category=linear&symbol={symbol}&interval=1&limit=100") as resp:
                    data = await resp.json()
                
                if data.get("retCode") == 0:
                    candles = data.get("result", {}).get("list", [])
                    logger.info(f"[DATA] {symbol} fetched: {len(candles)} candles")
                    
                    if candles:
                        # Store candles in reverse order (oldest first)
                        for candle in reversed(candles):
                            price = float(candle[4])  # Close price
                            self.current_prices[symbol] = price
                            self.price_history[symbol].append(price)
                        
                        # Update volume from latest candle
                        volume = float(candles[0][5])  # Volume from latest candle
                        self.volumes[symbol] = volume
                        
                        self.last_update[symbol] = datetime.now().timestamp()
                        
                        logger.info(f"[DATA] {symbol} appended: buffer size = {len(self.price_history[symbol])}")
                        
                        # Update data level
                        self._update_data_level(symbol)
                else:
                    logger.warning(f"[DATA] {symbol} API error: {data.get('retMsg')}")
                            
        except Exception as e:
            logger.error(f"Error fetching batch: {e}")
    
    def _update_data_level(self, symbol: str):
        """Update data level based on available data."""
        price_history = list(self.price_history.get(symbol, []))
        
        # RAW level: just need current price
        if symbol not in self.data_levels:
            self.data_levels[symbol] = DataLevel.RAW
            
        # BASIC level: need 10+ candles for EMA
        if len(price_history) >= 10:
            self.data_levels[symbol] = DataLevel.BASIC
            # Calculate 9-period EMA
            prices = price_history[-9:]
            if prices:
                self.ema_short[symbol] = sum(prices) / len(prices)
                # Calculate momentum (price change %)
                if len(prices) >= 2:
                    self.momentum[symbol] = (prices[-1] - prices[0]) / prices[0] * 100
                    
        # FULL level: need 50+ candles for ATR
        if len(price_history) >= 50:
            self.data_levels[symbol] = DataLevel.FULL
            # Calculate ATR (simplified)
            if len(price_history) >= 2:
                tr_values = []
                for i in range(1, min(15, len(price_history))):
                    high = price_history[i]
                    low = price_history[i-1]
                    tr = abs(high - low)
                    tr_values.append(tr)
                if tr_values:
                    self.atr[symbol] = sum(tr_values) / len(tr_values)
                
    def is_ready(self, symbol: str, min_level: DataLevel = DataLevel.RAW) -> bool:
        """Check if symbol has reached minimum data level."""
        current_level = self.data_levels.get(symbol, DataLevel.RAW)
        return current_level.value >= min_level.value
                
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        return self.current_prices.get(symbol)
        
    def get_price_history(self, symbol: str) -> List[float]:
        """Get price history for symbol."""
        return list(self.price_history.get(symbol, []))
        
    def get_volume(self, symbol: str) -> Optional[float]:
        """Get volume data for symbol."""
        return self.volumes.get(symbol)
    
    def get_data_level(self, symbol: str) -> DataLevel:
        """Get current data level for symbol."""
        return self.data_levels.get(symbol, DataLevel.RAW)
    
    def get_ema(self, symbol: str) -> Optional[float]:
        """Get short EMA for symbol (BASIC+ level)."""
        return self.ema_short.get(symbol)
    
    def get_momentum(self, symbol: str) -> Optional[float]:
        """Get momentum for symbol (BASIC+ level)."""
        return self.momentum.get(symbol)
    
    def get_atr(self, symbol: str) -> Optional[float]:
        """Get ATR for symbol (FULL level)."""
        return self.atr.get(symbol)
        
    def set_trade_callback(self, callback):
        """Set callback for trade updates."""
        self.on_trade_callback = callback
        
    def set_orderbook_callback(self, callback):
        """Set callback for orderbook updates."""
        self.on_orderbook_callback = callback


async def get_usdt_futures_symbols(limit: int = 250, min_volume_24h: float = 1000000) -> List[str]:
    """
    Get list of USDT futures symbols from Bybit with volume filtering.
    Uses robust implementation from existing codebase.
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Get instruments info
            async with session.get("https://api.bybit.com/v5/market/instruments-info?category=linear") as resp:
                instruments_data = await resp.json()
                
            if instruments_data.get("retCode") != 0:
                logger.error(f"Error getting instruments: {instruments_data.get('retMsg')}")
                return []
                
            instruments = instruments_data.get("result", {}).get("list", [])
            logger.debug(f"Got {len(instruments)} instruments from API")
            
            # Get tickers for volume info
            async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
                tickers_data = await resp.json()
                
            if tickers_data.get("retCode") != 0:
                logger.error(f"Error getting tickers: {tickers_data.get('retMsg')}")
                return []
                
            tickers = tickers_data.get("result", {}).get("list", [])
            logger.debug(f"Got {len(tickers)} tickers")
            
            ticker_map = {t.get("symbol"): t for t in tickers if isinstance(t, dict) and t.get("symbol")}
            
            symbols = []
            for instrument in instruments:
                if not isinstance(instrument, dict):
                    continue
                    
                symbol = instrument.get("symbol", "")
                
                # Skip non-perpetual and inverse contracts
                if not symbol or not symbol.endswith("USDT"):
                    continue
                    
                # Check status
                status = instrument.get("status", "")
                if status != "Trading":
                    continue
                    
                # Check volume
                ticker = ticker_map.get(symbol, {})
                volume_24h = float(ticker.get("turnover24h", 0))
                
                if volume_24h >= min_volume_24h:
                    symbols.append(symbol)
            
            logger.info(f"Found {len(symbols)} active trading symbols with volume >= ${min_volume_24h:,.0f}")
            return sorted(symbols)[:limit]
            
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []
