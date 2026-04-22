import asyncio
import logging
import yaml
from datetime import datetime
import sys
import os

# Add engine directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine'))

from market_data import MarketDataEngine, get_usdt_futures_symbols
from signal_engine import SignalEngine
from scoring import ScoringEngine
from portfolio import PortfolioManager
from survival import SurvivalEngine
from execution import ExecutionEngine
from risk import RiskEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('quant_engine.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class QuantFundEngine:
    """
    Main engine that coordinates all components.
    Real-time crypto quant fund for Bybit futures.
    """
    
    def __init__(self, config_path: str, api_key: str, api_secret: str, testnet: bool = True):
        self.config = self._load_config(config_path)
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Initialize engines
        self.market_data: MarketDataEngine = None
        self.signal_engine: SignalEngine = SignalEngine(self.config)
        self.scoring_engine: ScoringEngine = ScoringEngine(self.config)
        self.portfolio_manager: PortfolioManager = PortfolioManager(self.config, self.scoring_engine)
        self.survival_engine: SurvivalEngine = SurvivalEngine(self.config)
        self.execution_engine: ExecutionEngine = ExecutionEngine(self.config, api_key, api_secret, testnet)
        self.risk_engine: RiskEngine = RiskEngine(self.config)
        
        # State
        self.symbols: list = []
        self.running = False
        
        # Callbacks
        self._setup_callbacks()
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
            
    def _setup_callbacks(self):
        """Setup callbacks between engines."""
        # Portfolio rebalance callback
        self.portfolio_manager.set_rebalance_callback(self._on_rebalance)
        
        # Market data callbacks
        self._setup_market_data_callbacks()
        
    def _setup_market_data_callbacks(self):
        """Setup market data callbacks for real-time processing."""
        async def on_trade(symbol, trades):
            """Handle trade updates."""
            for trade in trades:
                price = float(trade.get("p", 0))
                volume = float(trade.get("q", 0))
                
                # Update signal engine
                self.signal_engine.update_price(symbol, price, volume)
                
                # Update scoring engine
                self.scoring_engine.update_volume_score(symbol, volume)
                
                # Update scoring with price history
                price_history = self.market_data.get_price_history(symbol)
                if len(price_history) >= 20:
                    self.scoring_engine.update_volatility_score(symbol, price_history)
                    
        async def on_orderbook(symbol, orderbook):
            """Handle orderbook updates."""
            price = self.market_data.get_current_price(symbol)
            if price:
                self.signal_engine.update_price(symbol, price)
                
        # These will be set when market_data is initialized
        self.on_trade_callback = on_trade
        self.on_orderbook_callback = on_orderbook
        
    async def _on_rebalance(self, allocations: dict):
        """Handle portfolio rebalance."""
        logger.info(f"Rebalance triggered: {len(allocations)} allocations")
        
        # Log top allocations
        top_allocations = sorted(allocations.items(), key=lambda x: x[1], reverse=True)[:10]
        for symbol, allocation in top_allocations:
            logger.info(f"  {symbol}: ${allocation:,.2f}")
            
    async def initialize(self):
        """Initialize all engines."""
        logger.info("Initializing Quant Fund Engine...")
        
        # Get symbols
        universe_size = self.config.get("initial_universe_size", 250)
        logger.info(f"Fetching {universe_size} USDT futures symbols...")
        self.symbols = await get_usdt_futures_symbols(universe_size)
        logger.info(f"Loaded {len(self.symbols)} symbols")
        
        # Initialize market data engine
        logger.info("Initializing market data engine...")
        self.market_data = MarketDataEngine(self.symbols, self.config)
        self.market_data.set_trade_callback(self.on_trade_callback)
        self.market_data.set_orderbook_callback(self.on_orderbook_callback)
        
        # Initialize execution engine
        logger.info("Initializing execution engine...")
        await self.execution_engine.start()
        
        # Set initial capital in risk engine
        initial_capital = 100000.0  # Default, can be fetched from API
        self.risk_engine.set_initial_capital(initial_capital)
        self.portfolio_manager.set_total_capital(initial_capital)
        
        logger.info("Initialization complete")
        
    async def run(self):
        """Main trading loop."""
        self.running = True
        logger.info("Starting Quant Fund Engine...")
        
        # Start market data ingestion
        market_data_task = asyncio.create_task(self.market_data.connect())
        
        # Main loop
        while self.running:
            try:
                # Check emergency stop
                if self.risk_engine.is_emergency_stop():
                    logger.critical("Emergency stop triggered, shutting down...")
                    break
                    
                # Update survival engine
                self.survival_engine.check_blacklist_expiry()
                self.survival_engine.apply_decay()
                
                # Generate signals for all symbols
                for symbol in self.symbols:
                    if self.survival_engine.is_blacklisted(symbol):
                        continue
                        
                    # Generate signal
                    signal = self.signal_engine.generate_signals(symbol)
                    
                    # Update momentum score in scoring engine
                    if signal and signal.get("combined"):
                        strength = signal["combined"].get("strength", 0)
                        self.scoring_engine.update_momentum_score(symbol, strength)
                        
                    # Calculate health score
                    health_score = self.scoring_engine.calculate_health_score(symbol)
                    
                # Rebalance portfolio
                health_scores = self.scoring_engine.get_all_scores()
                await self.portfolio_manager.rebalance(health_scores)
                
                # Execute trades based on signals and allocations
                await self._execute_trades()
                
                # Log status
                self._log_status()
                
                # Sleep for next iteration
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
                
        # Cleanup
        await self.shutdown()
        
    async def _execute_trades(self):
        """Execute trades based on signals and allocations with data level awareness."""
        allocations = self.portfolio_manager.get_all_allocations()
        
        # Get startup throttle (20-30% first 60 seconds)
        startup_throttle = self.risk_engine.get_startup_throttle()
        
        for symbol, allocation in allocations.items():
            if self.survival_engine.is_blacklisted(symbol):
                continue
            
            # Check symbol data readiness
            from engine.market_data import DataLevel
            data_level = self.market_data.get_data_level(symbol)
            
            # Skip if not at least RAW level (basic price data)
            if not self.market_data.is_ready(symbol, DataLevel.RAW):
                continue
            
            # Get signal based on data level
            signal = self.signal_engine.get_current_signal(symbol)
            
            # Fallback strategy for RAW level (no historical data)
            if not signal or not signal.get("combined"):
                if data_level == DataLevel.RAW:
                    current_price = self.market_data.get_current_price(symbol)
                    volume = self.market_data.get_volume(symbol) or 0
                    signal = self.signal_engine.generate_fallback_signal(symbol, current_price, volume)
                    
                    if signal:
                        logger.info(f"[FALLBACK] Using fallback signal for {symbol}")
            
            if not signal or not signal.get("combined"):
                continue
                
            direction = signal["combined"]["direction"]
            confidence = signal["combined"]["confidence"]
            
            # Lower confidence threshold for fallback/startup
            min_confidence = 0.2 if data_level == DataLevel.RAW else 0.5
            if confidence < min_confidence:
                continue
                
            # Check risk limits
            if not self.risk_engine.check_position_size(symbol, allocation):
                continue
                
            # Get current position
            position = await self.execution_engine.get_position(symbol)
            
            # Calculate TP/SL
            current_price = self.market_data.get_current_price(symbol)
            atr = self.signal_engine.get_atr(symbol)
            tp, sl = self.execution_engine.calculate_tp_sl(symbol, current_price, direction, atr)
            
            # Calculate quantity with startup throttle
            leverage_multiplier = self.risk_engine.get_leverage_multiplier()
            effective_allocation = allocation * leverage_multiplier * startup_throttle
            qty = effective_allocation / current_price if current_price > 0 else 0
            
            # Execute trade
            side = "Buy" if direction == "long" else "Sell"
            
            # Check if we already have a position in this direction
            if position and position["side"].lower() == direction.lower():
                continue  # Already positioned
                
            # Place order
            result = await self.execution_engine.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                tp=tp,
                sl=sl
            )
            
            if result.get("retCode") == 0:
                logger.info(f"Trade executed: {symbol} {side} {qty:.4f} @ {current_price:.4f} TP={tp:.4f} SL={sl:.4f}")
                
    def _log_status(self):
        """Log current status."""
        risk_summary = self.risk_engine.get_risk_summary()
        portfolio_summary = self.portfolio_manager.get_allocation_summary()
        survival_summary = self.survival_engine.get_survival_summary()
        
        logger.info(
            f"Status | Capital: ${risk_summary['current_capital']:,.2f} | "
            f"Drawdown: {risk_summary['drawdown_pct']:.2f}% | "
            f"Positions: {portfolio_summary['num_positions']} | "
            f"Blacklisted: {survival_summary['blacklisted_count']}"
        )
        
    async def shutdown(self):
        """Shutdown all engines."""
        logger.info("Shutting down Quant Fund Engine...")
        self.running = False
        
        if self.market_data:
            await self.market_data.stop()
            
        if self.execution_engine:
            await self.execution_engine.stop()
            
        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    # Configuration
    config_path = "config.yaml"
    
    # API credentials from Genius bot
    api_key = "qltUum7PztwhAE6sU3"
    api_secret = "iVYTFKUgy9HLqNWIcSpMHprYx1Ohn7Cv2yxZ"
    testnet = True  # Using testnet
    
    # Create engine
    engine = QuantFundEngine(config_path, api_key, api_secret, testnet)
    
    try:
        # Initialize
        await engine.initialize()
        
        # Run
        await engine.run()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
