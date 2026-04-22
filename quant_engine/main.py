import asyncio
import logging
import yaml
from datetime import datetime
import os
from enum import Enum

from quant_engine.engine.market_data import MarketDataEngine, get_usdt_futures_symbols
from quant_engine.engine.signal_engine import SignalEngine
from quant_engine.engine.scoring import ScoringEngine
from quant_engine.engine.portfolio import PortfolioManager
from quant_engine.engine.survival import SurvivalEngine
from quant_engine.engine.execution import ExecutionEngine
from quant_engine.engine.risk import RiskEngine
from quant_engine.engine.market_data import DataLevel

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")


class SystemState(Enum):
    """System state machine for bootstrap lifecycle."""
    INIT = 0          # Load config, initialize engines, start data collectors
    WARMUP = 1        # Collect historical candles, NO signals, NO trading
    SHADOW = 2        # Run signals for validation, NO execution
    LIVE = 3          # Full trading mode with execution

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "quant_engine", "quant_engine.log")),
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
        
        # System state
        self.state = SystemState.INIT
        self.state_start_time = datetime.now()
        
        # Warmup configuration
        self.warmup_min_candles = 100  # Minimum candles for MA/EMA
        self.warmup_min_atr = 50      # Minimum candles for ATR/volatility
        self.warmup_timeout = 300     # Maximum warmup time (seconds)
        
        # INIT configuration
        self.init_timeout = 60        # Maximum INIT time (seconds)
        self.init_min_candles = 50    # Minimum candles to exit INIT
        self.init_min_coverage = 0.7  # Minimum 70% symbols coverage to exit INIT
        self.init_top_symbols = 20    # Only fetch top N symbols initially for fast startup
        self.candles_collected = {}   # Track candles per symbol
        
        # Shadow mode configuration
        self.shadow_min_signals = 0.1  # Minimum 10% of symbols must produce signals
        self.shadow_duration = 60      # Minimum shadow mode duration (seconds)
        
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
        self.indicators_ready = False
        
        # Callbacks
        self._setup_callbacks()
    
    async def _handle_state_transition(self):
        """Handle state transitions based on conditions."""
        elapsed_in_state = 0
        if self.state_start_time:
            elapsed_in_state = (datetime.now() - self.state_start_time).total_seconds()
        
        # INIT -> WARMUP
        if self.state == SystemState.INIT:
            # Check INIT exit conditions
            if self._check_init_complete() or elapsed_in_state > self.init_timeout:
                logger.info(f"INIT complete ({elapsed_in_state:.1f}s), transitioning to WARMUP")
                self._transition_to(SystemState.WARMUP)
        
        # WARMUP -> SHADOW
        elif self.state == SystemState.WARMUP:
            if self._check_warmup_complete() or elapsed_in_state > self.warmup_timeout:
                logger.info("Warmup complete, transitioning to SHADOW mode")
                self._transition_to(SystemState.SHADOW)
        
        # SHADOW -> LIVE
        elif self.state == SystemState.SHADOW:
            if elapsed_in_state > self.shadow_duration and self._check_shadow_valid():
                logger.info("Shadow validation passed, transitioning to LIVE mode")
                self._transition_to(SystemState.LIVE)
    
    def _transition_to(self, new_state: SystemState):
        """Transition to new state with logging."""
        old_state = self.state
        self.state = new_state
        self.state_start_time = datetime.now()
        logger.info(f"State transition: {old_state.name} -> {new_state.name}")
    
    def _check_init_complete(self) -> bool:
        """Check if INIT has collected enough data for top symbols to proceed."""
        if not self.market_data:
            return False
        
        # Only check top symbols for fast startup
        top_symbols = self.symbols[:self.init_top_symbols]
        
        # Check actual market data price history
        symbols_with_data = 0
        for symbol in top_symbols:
            price_history = self.market_data.get_price_history(symbol)
            candle_count = len(price_history)
            
            if candle_count >= self.init_min_candles:
                symbols_with_data += 1
        
        # Exit conditions:
        # 1. All top symbols have minimum candles
        if symbols_with_data >= len(top_symbols):
            return True
        
        # 2. Minimum coverage (70% of top symbols with 50+ candles)
        coverage = symbols_with_data / len(top_symbols) if top_symbols else 0
        if coverage >= self.init_min_coverage:
            logger.info(f"INIT: {symbols_with_data}/{len(top_symbols)} top symbols with {self.init_min_candles}+ candles")
            return True
        
        return False
    
    def _check_warmup_complete(self) -> bool:
        """Check if warmup has collected enough data."""
        if not self.market_data:
            return False
        
        # Check if all symbols have minimum required candles
        for symbol in self.symbols:
            price_history = self.market_data.get_price_history(symbol)
            if len(price_history) < self.warmup_min_candles:
                return False
            if len(price_history) < self.warmup_min_atr:
                return False
        
        self.indicators_ready = True
        return True
    
    def _check_shadow_valid(self) -> bool:
        """Check if shadow mode produced valid signal distribution."""
        signal_count = 0
        for symbol in self.symbols:
            signal = self.signal_engine.get_current_signal(symbol)
            if signal and signal.get("combined"):
                signal_count += 1
        
        signal_ratio = signal_count / len(self.symbols) if self.symbols else 0
        return signal_ratio >= self.shadow_min_signals
    
    async def _handle_init(self):
        """Handle INIT state - collect initial data for top symbols only (fast startup)."""
        # Fetch data only for top symbols during INIT
        if not hasattr(self, '_init_fetch_done'):
            top_symbols = self.symbols[:self.init_top_symbols]
            logger.info(f"INIT: Fetching data for top {len(top_symbols)} symbols only")
            await self.market_data._fetch_all_data(top_symbols)
            self._init_fetch_done = True
        
        # Log progress
        elapsed = (datetime.now() - self.state_start_time).total_seconds()
        if int(elapsed) % 5 == 0 and int(elapsed) > 0:
            top_symbols = self.symbols[:self.init_top_symbols]
            symbols_with_data = sum(1 for s in top_symbols if len(self.market_data.get_price_history(s)) >= self.init_min_candles)
            logger.info(f"INIT: {symbols_with_data}/{len(top_symbols)} top symbols with {self.init_min_candles}+ candles ({elapsed:.0f}s elapsed)")
    
    async def _handle_warmup(self):
        """Handle WARMUP state - collect historical candles for remaining symbols, NO signals."""
        # Fetch remaining symbols in background
        if not hasattr(self, '_warmup_fetch_done'):
            remaining_symbols = self.symbols[self.init_top_symbols:]
            if remaining_symbols:
                logger.info(f"WARMUP: Fetching data for remaining {len(remaining_symbols)} symbols")
                await self.market_data._fetch_all_data(remaining_symbols)
            self._warmup_fetch_done = True
            
            # Enable auto-fetch for continuous updates
            self.market_data.auto_fetch = True
            logger.info("WARMUP: Enabled auto-fetch for continuous data updates")
        
        # Update market data only, NO signal computation
        for symbol in self.symbols:
            current_price = self.market_data.get_current_price(symbol)
            volume = self.market_data.get_volume(symbol)
            if current_price:
                # Update price history but DO NOT compute signals
                self.signal_engine.update_price(symbol, current_price, volume)
        
        elapsed = (datetime.now() - self.state_start_time).total_seconds()
        if int(elapsed) % 10 == 0 and int(elapsed) > 0:
            symbols_with_data = sum(1 for s in self.symbols if len(self.market_data.get_price_history(s)) >= self.warmup_min_candles)
            logger.info(f"WARMUP: {symbols_with_data}/{len(self.symbols)} symbols with {self.warmup_min_candles}+ candles ({elapsed:.0f}s elapsed)")
    
    async def _handle_shadow(self):
        """Handle SHADOW state - run signals for validation, NO execution."""
        elapsed = (datetime.now() - self.state_start_time).total_seconds()
        logger.info(f"SHADOW: Validating signals ({elapsed:.0f}s elapsed)...")
        
        # Update signals but DO NOT execute trades
        for symbol in self.symbols:
            current_price = self.market_data.get_current_price(symbol)
            volume = self.market_data.get_volume(symbol)
            if current_price:
                self.signal_engine.update_price(symbol, current_price, volume)
                signal = self.signal_engine.generate_signals(symbol)
                if signal and signal.get("combined"):
                    logger.info(f"[SHADOW] {symbol}: {signal['combined']['direction']} (confidence: {signal['combined']['confidence']:.2f})")
    
    async def _handle_live(self):
        """Handle LIVE state - full trading mode."""
        # Update signal engine with current prices
        for symbol in self.symbols:
            current_price = self.market_data.get_current_price(symbol)
            volume = self.market_data.get_volume(symbol)
            if current_price:
                self.signal_engine.update_price(symbol, current_price, volume)
        
        # Rebalance portfolio
        health_scores = self.scoring_engine.calculate_health_scores(self.symbols, self.market_data)
        allocations = self.portfolio_manager.calculate_allocations(health_scores)
        self.portfolio_manager.set_allocations(allocations)
        
        # Execute trades based on signals and allocations
        await self._execute_trades()
        
        # Log status
        self._log_status()
        
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
                
                # State-specific logic
                if self.state == SystemState.INIT:
                    await self._handle_init()
                elif self.state == SystemState.WARMUP:
                    await self._handle_warmup()
                elif self.state == SystemState.SHADOW:
                    await self._handle_shadow()
                elif self.state == SystemState.LIVE:
                    await self._handle_live()
                
                # Sleep for next iteration
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
                
        # Cleanup
        await self.shutdown()
        
    async def _execute_trades(self):
        """Execute trades based on signals and allocations with data level awareness."""
        # Only execute in LIVE state
        if self.state != SystemState.LIVE:
            return
        
        allocations = self.portfolio_manager.get_all_allocations()
        
        # Get startup throttle (20-30% first 60 seconds)
        startup_throttle = self.risk_engine.get_startup_throttle()
        
        for symbol, allocation in allocations.items():
            if self.survival_engine.is_blacklisted(symbol):
                continue
            
            # Check symbol data readiness
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
    # Configuration (using absolute path)
    config_path = CONFIG_PATH
    
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
