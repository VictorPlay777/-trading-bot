import asyncio
import websockets
import json
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)


class MarketDataEngine:
    """
    Real-time market data ingestion for 250+ symbols.
    Handles WebSocket connections for orderbook, trades, funding, and volume.
    """
    
    def __init__(self, symbols: List[str], config: dict):
        self.symbols = symbols
        self.config = config
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        
        # Data storage
        self.orderbooks: Dict[str, dict] = defaultdict(dict)
        self.trades: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.funding_rates: Dict[str, float] = {}
        self.volumes: Dict[str, dict] = defaultdict(dict)
        
        # Price tracking
        self.current_prices: Dict[str, float] = {}
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # WebSocket connection
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.reconnect_delay = 5
        self.running = False
        
        # Callbacks
        self.on_trade_callback = None
        self.on_orderbook_callback = None
        
    async def connect(self):
        """Establish WebSocket connection and subscribe to all symbols."""
        self.running = True
        
        while self.running:
            try:
                logger.info(f"Connecting to Bybit WebSocket for {len(self.symbols)} symbols...")
                
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    await self._subscribe(ws)
                    logger.info("WebSocket connected and subscribed")
                    
                    # Process messages
                    async for message in ws:
                        if not self.running:
                            break
                        await self._handle_message(message)
                        
            except Exception as e:
                logger.error(f"WebSocket error: {e}, reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                
    async def _subscribe(self, ws):
        """Subscribe to orderbook, trades, and funding for all symbols."""
        # Split symbols into batches to avoid subscription limits
        batch_size = 50
        for i in range(0, len(self.symbols), batch_size):
            batch = self.symbols[i:i+batch_size]
            
            # Orderbook subscription
            orderbook_subs = [
                {"topic": "orderbook.1." + symbol, "symbol": symbol}
                for symbol in batch
            ]
            
            # Trade subscription
            trade_subs = [
                {"topic": "publicTrade." + symbol, "symbol": symbol}
                for symbol in batch
            ]
            
            # Funding subscription
            funding_subs = [
                {"topic": "tickers." + symbol, "symbol": symbol}
                for symbol in batch
            ]
            
            # Send subscriptions
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": orderbook_subs + trade_subs + funding_subs
            }))
            
            # Small delay between batches
            await asyncio.sleep(0.1)
            
    async def _handle_message(self, message: str):
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            if "topic" in data:
                topic = data["topic"]
                symbol = data.get("symbol", "")
                
                if "orderbook" in topic:
                    await self._process_orderbook(symbol, data)
                elif "publicTrade" in topic:
                    await self._process_trade(symbol, data)
                elif "tickers" in topic:
                    await self._process_ticker(symbol, data)
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    async def _process_orderbook(self, symbol: str, data: dict):
        """Process orderbook update."""
        try:
            if "data" in data and data["data"]:
                ob = data["data"][0]
                
                # Extract bids and asks
                bids = ob.get("b", [])[:10]  # Top 10 bids
                asks = ob.get("a", [])[:10]  # Top 10 asks
                
                if bids and asks:
                    self.orderbooks[symbol] = {
                        "bids": bids,
                        "asks": asks,
                        "timestamp": datetime.now().timestamp()
                    }
                    
                    # Update mid price
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    mid_price = (best_bid + best_ask) / 2
                    
                    self.current_prices[symbol] = mid_price
                    self.price_history[symbol].append(mid_price)
                    
                    if self.on_orderbook_callback:
                        await self.on_orderbook_callback(symbol, self.orderbooks[symbol])
                        
        except Exception as e:
            logger.error(f"Error processing orderbook for {symbol}: {e}")
            
    async def _process_trade(self, symbol: str, data: dict):
        """Process trade update."""
        try:
            if "data" in data and data["data"]:
                trades = data["data"]
                
                for trade in trades:
                    trade_data = {
                        "price": float(trade.get("p", 0)),
                        "size": float(trade.get("q", 0)),
                        "side": trade.get("S", ""),
                        "time": trade.get("T", 0)
                    }
                    
                    self.trades[symbol].append(trade_data)
                    
                    # Update current price
                    self.current_prices[symbol] = trade_data["price"]
                    
                if self.on_trade_callback:
                    await self.on_trade_callback(symbol, trades)
                    
        except Exception as e:
            logger.error(f"Error processing trade for {symbol}: {e}")
            
    async def _process_ticker(self, symbol: str, data: dict):
        """Process ticker update (volume, funding)."""
        try:
            if "data" in data and data["data"]:
                ticker = data["data"][0]
                
                self.volumes[symbol] = {
                    "volume_24h": float(ticker.get("volume24h", 0)),
                    "turnover_24h": float(ticker.get("turnover24h", 0)),
                    "timestamp": datetime.now().timestamp()
                }
                
                funding_rate = ticker.get("fundingRate")
                if funding_rate:
                    self.funding_rates[symbol] = float(funding_rate)
                    
        except Exception as e:
            logger.error(f"Error processing ticker for {symbol}: {e}")
            
    def get_orderbook(self, symbol: str) -> Optional[dict]:
        """Get current orderbook for symbol."""
        return self.orderbooks.get(symbol)
        
    def get_trades(self, symbol: str, limit: int = 100) -> List[dict]:
        """Get recent trades for symbol."""
        trades = list(self.trades.get(symbol, []))
        return trades[-limit:]
        
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        return self.current_prices.get(symbol)
        
    def get_price_history(self, symbol: str) -> List[float]:
        """Get price history for symbol."""
        return list(self.price_history.get(symbol, []))
        
    def get_volume(self, symbol: str) -> Optional[dict]:
        """Get volume data for symbol."""
        return self.volumes.get(symbol)
        
    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get funding rate for symbol."""
        return self.funding_rates.get(symbol)
        
    def get_spread(self, symbol: str) -> Optional[float]:
        """Calculate spread percentage for symbol."""
        ob = self.orderbooks.get(symbol)
        if ob and ob["bids"] and ob["asks"]:
            best_bid = float(ob["bids"][0][0])
            best_ask = float(ob["asks"][0][0])
            spread = (best_ask - best_bid) / best_bid * 100
            return spread
        return None
        
    def set_trade_callback(self, callback):
        """Set callback for trade updates."""
        self.on_trade_callback = callback
        
    def set_orderbook_callback(self, callback):
        """Set callback for orderbook updates."""
        self.on_orderbook_callback = callback
        
    async def stop(self):
        """Stop the market data engine."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Market data engine stopped")


async def get_usdt_futures_symbols(limit: int = 250) -> List[str]:
    """Get list of USDT futures symbols from Bybit."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
                data = await resp.json()
                if data["retCode"] == 0:
                    symbols = [
                        item["symbol"]
                        for item in data["result"]["list"]
                        if "USDT" in item["symbol"]
                    ]
                    return symbols[:limit]
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        return []
