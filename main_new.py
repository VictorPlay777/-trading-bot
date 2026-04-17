"""
Adaptive Momentum Trading Bot - Main Entry Point
"""
import logging
import sys
import time
from datetime import datetime

from config import api_config, trading_config
from api_client import BybitClient
from engine import TradingEngine
from web_dashboard import start_dashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("INITIALIZING ADAPTIVE MOMENTUM TRADING BOT")
    logger.info("=" * 60)
    logger.info(f"Exchange: Bybit {'Testnet' if api_config.testnet else 'Mainnet'}")
    logger.info(f"Symbols: {', '.join(trading_config.symbols)}")
    logger.info(f"Leverage: {trading_config.default_leverage}x")
    logger.info("-" * 60)
    
    try:
        # Initialize API client
        api_client = BybitClient()
        
        # Initialize trading engine
        engine = TradingEngine(api_client)
        
        # Start web dashboard
        start_dashboard(engine, host='0.0.0.0', port=5000)
        logger.info("=" * 60)
        logger.info("WEB DASHBOARD STARTED")
        logger.info("Access at: http://111.88.150.44:5000")
        logger.info("=" * 60)
        
        # Track uptime
        start_time = time.time()
        
        # Run the engine
        logger.info("Starting trading engine...")
        engine.uptime_seconds = 0
        engine.start_time = start_time
        engine.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
