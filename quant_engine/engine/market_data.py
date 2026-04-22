import asyncio
import aiohttp
import json
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketDataEngine:
    """
    Market data ingestion using REST API (simpler and more reliable).
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
                
    async def _fetch_all_data(self):
        """Fetch data for all symbols."""
        # Split into batches to avoid rate limits
        batch_size = 20
        for i in range(0, len(self.symbols), batch_size):
            batch = self.symbols[i:i+batch_size]
            await self._fetch_batch(batch)
            
    async def _fetch_batch(self, symbols: List[str]):
        """Fetch data for a batch of symbols."""
        try:
            # Get tickers for batch
            symbols_str = ",".join(symbols)
            async with self.session.get(f"{self.base_url}/market/tickers?category=linear&symbol={symbols_str}") as resp:
                data = await resp.json()
                
            if data.get("retCode") == 0:
                for item in data.get("result", {}).get("list", []):
                    symbol = item.get("symbol")
                    if symbol:
                        # Update price
                        price = float(item.get("lastPrice", 0))
                        self.current_prices[symbol] = price
                        self.price_history[symbol].append(price)
                        
                        # Update volume
                        volume = float(item.get("turnover24h", 0))
                        self.volumes[symbol] = volume
                        
                        self.last_update[symbol] = datetime.now().timestamp()
                        
                        # Trigger callbacks
                        if self.on_trade_callback:
                            await self.on_trade_callback(symbol, [{"p": price, "q": volume}])
                            
        except Exception as e:
            logger.error(f"Error fetching batch: {e}")
                
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        return self.current_prices.get(symbol)
        
    def get_price_history(self, symbol: str) -> List[float]:
        """Get price history for symbol."""
        return list(self.price_history.get(symbol, []))
        
    def get_volume(self, symbol: str) -> Optional[float]:
        """Get volume data for symbol."""
        return self.volumes.get(symbol)
        
    def set_trade_callback(self, callback):
        """Set callback for trade updates."""
        self.on_trade_callback = callback


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
