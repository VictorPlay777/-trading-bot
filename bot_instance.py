"""
Bot Instance - Wrapper for single trading bot with hot-reload config
Each bot runs in its own process with isolated configuration
"""
import os
import sys
import json
import time
import signal
import logging
import threading
from datetime import datetime
from typing import Dict, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import BybitClient
from engine import TradingEngine
from config import trading_config, strategy_config


class BotStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class BotStats:
    """Real-time bot statistics"""
    bot_id: str
    status: str
    
    # Trading stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    
    # Position stats
    active_positions: int = 0
    max_positions: int = 0
    
    # Runtime
    uptime_seconds: int = 0
    last_error: str = ""
    error_count: int = 0
    
    # Performance
    balance: float = 0.0
    max_drawdown: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class BotInstance:
    """
    Single bot instance with:
    - Hot-reload configuration
    - Isolated API credentials
    - Independent logging
    - Graceful start/stop/pause
    """
    
    def __init__(self, config_path: str, on_stats_update: Optional[Callable] = None):
        self.config_path = config_path
        self.config: Dict = {}
        self.on_stats_update = on_stats_update
        
        # Bot components
        self.api: Optional[BybitClient] = None
        self.engine: Optional[TradingEngine] = None
        
        # State
        self.status = BotStatus.STOPPED
        self.stats = BotStats(bot_id="", status="stopped")
        self.start_time: Optional[datetime] = None
        
        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._config_watcher: Optional[threading.Thread] = None
        self._last_config_mtime: float = 0
        
        # Logger
        self.logger: Optional[logging.Logger] = None
        
        self._load_config()
    
    def _load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            
            self.stats.bot_id = self.config.get('bot_id', 'unknown')
            self._last_config_mtime = os.path.getmtime(self.config_path)
            
            # Setup logging
            self._setup_logging()
            
            self.logger.info(f"Config loaded: {self.config.get('name')}")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to load config: {e}")
            else:
                print(f"[ERROR] Failed to load config {self.config_path}: {e}")
            return False
    
    def _setup_logging(self):
        """Setup isolated logging for this bot"""
        bot_id = self.config.get('bot_id', 'unknown')
        log_file = self.config.get('logging', {}).get('file', f'bot_logs/{bot_id}.log')
        log_level = self.config.get('logging', {}).get('level', 'INFO')
        
        # Create logger
        self.logger = logging.getLogger(bot_id)
        self.logger.setLevel(getattr(logging, log_level))
        
        # Clear existing handlers
        self.logger.handlers = []
        
        # File handler
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setLevel(getattr(logging, log_level))
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        
        self.logger.addHandler(fh)
    
    def _start_config_watcher(self):
        """Watch config file for changes (hot-reload)"""
        def watcher():
            while not self._stop_event.is_set():
                try:
                    mtime = os.path.getmtime(self.config_path)
                    if mtime > self._last_config_mtime:
                        self.logger.info("Config file changed, reloading...")
                        if self._load_config():
                            self._apply_config_changes()
                        self._last_config_mtime = mtime
                except Exception as e:
                    self.logger.warning(f"Config watcher error: {e}")
                
                time.sleep(5)  # Check every 5 seconds
        
        self._config_watcher = threading.Thread(target=watcher, daemon=True)
        self._config_watcher.start()
    
    def _apply_config_changes(self):
        """Apply configuration changes without restart"""
        if self.engine:
            # Update leverage
            new_leverage = self.config.get('strategy', {}).get('leverage', 10)
            if new_leverage != self.engine.leverage:
                self.logger.info(f"Leverage changed: {self.engine.leverage}x → {new_leverage}x")
                self.engine.leverage = new_leverage
            
            # Reload position manager configuration (stats_file, skip_analytics_filter, max_positions, etc.)
            self.engine.position_manager.reload_config(self.config)
        
        self.logger.info("Configuration hot-reloaded successfully")
    
    def _init_api(self) -> bool:
        """Initialize API client with bot-specific credentials"""
        try:
            # Hardcoded API keys from config (HARDCORE MODE!)
            api_key = self.config.get('api', {}).get('key', 'rRsm08OPN027nk5hgF')
            api_secret = self.config.get('api', {}).get('secret', 'GD1qBUUx1KROqmAKwJLOpAanLNDwG6zr1CyA')
            testnet = self.config.get('api', {}).get('testnet', False)
            
            if not api_key or not api_secret:
                self.logger.error(f"API credentials not found in config")
                return False
            
            self.api = BybitClient()  # Keys read from config.py directly
            self.logger.info(f"API initialized (HARDCORE MODE, testnet={testnet})")
            return True
            
        except Exception as e:
            self.logger.error(f"API initialization failed: {e}")
            return False
    
    def _init_engine(self) -> bool:
        """Initialize trading engine"""
        try:
            # Apply config to strategy
            # Pass bot-specific config to engine so it uses JSON settings, not global
            self.engine = TradingEngine(self.api, self.config)
            self.logger.info("Trading engine initialized with bot-specific config")
            return True
            
        except Exception as e:
            self.logger.error(f"Engine initialization failed: {e}")
            return False
    
    def _trading_loop(self):
        """Main trading loop"""
        self.logger.info("Trading loop started")
        
        cycle_count = 0
        while not self._stop_event.is_set():
            try:
                # Check pause
                if self._pause_event.is_set():
                    time.sleep(1)
                    continue
                
                # Run trading cycle
                if self.engine:
                    self.engine.run_cycle()
                    self._update_stats()
                
                cycle_count += 1
                
                # Sleep between cycles
                time.sleep(60)  # 1-minute cycles
                
            except Exception as e:
                self.logger.error(f"Trading cycle error: {e}")
                self.stats.error_count += 1
                self.stats.last_error = str(e)
                self._notify_stats_update()
                time.sleep(5)
        
        self.logger.info("Trading loop stopped")
    
    def _update_stats(self):
        """Update bot statistics"""
        if not self.engine:
            return
        
        try:
            # Trading stats
            self.stats.total_trades = self.engine.session_trades
            self.stats.winning_trades = self.engine.session_wins
            self.stats.losing_trades = self.engine.session_losses
            
            if self.engine.session_trades > 0:
                self.stats.win_rate = self.engine.session_wins / self.engine.session_trades
            
            self.stats.total_pnl = self.engine.session_pnl
            
            # Position stats
            positions = self.engine.position_manager.get_all_positions()
            self.stats.active_positions = len(positions)
            self.stats.max_positions = self.config.get('strategy', {}).get('max_positions', 20)
            
            # Runtime
            if self.start_time:
                self.stats.uptime_seconds = int((datetime.utcnow() - self.start_time).total_seconds())
            
            # Status
            self.stats.status = self.status.value
            
            self._notify_stats_update()
            
        except Exception as e:
            self.logger.warning(f"Stats update error: {e}")
    
    def _notify_stats_update(self):
        """Notify parent about stats update"""
        if self.on_stats_update:
            try:
                self.on_stats_update(self.stats.to_dict())
            except Exception as e:
                self.logger.warning(f"Stats notification error: {e}")
    
    # === Public API ===
    
    def check_api_conflict(self, all_bots: list) -> bool:
        """Check if another bot is using same API"""
        my_key = self.config.get('api', {}).get('key', '')
        my_bot_id = self.stats.bot_id
        
        for bot in all_bots:
            other_bot_id = bot.stats.bot_id
            if other_bot_id == my_bot_id:
                continue  # Skip self
            if bot.status.value == 'running':
                other_key = bot.config.get('api', {}).get('key', '')
                if other_key == my_key:
                    self.logger.error(f"⚠️ API CONFLICT: Bot {other_bot_id} already running with same API key!")
                    self.logger.error(f"Stop {other_bot_id} first before starting {my_bot_id}")
                    return True
        return False
    
    def start(self, all_bots: list = None) -> bool:
        """Start the bot"""
        if self.status == BotStatus.RUNNING:
            return True
        
        # Check API conflicts
        if all_bots and self.check_api_conflict(all_bots):
            self.status = BotStatus.ERROR
            return False
        
        self.status = BotStatus.STARTING
        self._stop_event.clear()
        self._pause_event.clear()
        
        # Initialize
        if not self._init_api():
            self.status = BotStatus.ERROR
            return False
        
        if not self._init_engine():
            self.status = BotStatus.ERROR
            return False
        
        # Start config watcher
        self._start_config_watcher()
        
        # Start trading thread
        self._thread = threading.Thread(target=self._trading_loop, daemon=True)
        self._thread.start()
        
        self.start_time = datetime.utcnow()
        self.status = BotStatus.RUNNING
        self.stats.status = "running"
        
        self.logger.info(f"Bot {self.stats.bot_id} started successfully")
        return True
    
    def stop(self, timeout: int = 30) -> bool:
        """Stop the bot gracefully"""
        if self.status == BotStatus.STOPPED:
            return True
        
        self.logger.info("Stopping bot...")
        self.status = BotStatus.STOPPING
        self.stats.status = "stopping"
        
        # Signal stop
        self._stop_event.set()
        
        # Wait for thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        
        # Close all positions (optional)
        if self.engine and self.config.get('risk', {}).get('close_on_stop', False):
            self.logger.info("Closing all positions...")
            for symbol in list(self.engine.position_manager.positions.keys()):
                try:
                    self.engine.position_manager.close_position(symbol, reason="bot_stop")
                except Exception as e:
                    self.logger.warning(f"Failed to close {symbol}: {e}")
        
        self.status = BotStatus.STOPPED
        self.stats.status = "stopped"
        self.logger.info("Bot stopped")
        
        return True
    
    def pause(self) -> bool:
        """Pause trading (keep positions)"""
        if self.status != BotStatus.RUNNING:
            return False
        
        self._pause_event.set()
        self.status = BotStatus.PAUSED
        self.stats.status = "paused"
        self.logger.info("Bot paused (positions kept)")
        return True
    
    def resume(self) -> bool:
        """Resume trading"""
        if self.status != BotStatus.PAUSED:
            return False
        
        self._pause_event.clear()
        self.status = BotStatus.RUNNING
        self.stats.status = "running"
        self.logger.info("Bot resumed")
        return True
    
    def update_config(self, new_config: Dict) -> bool:
        """Update configuration programmatically"""
        try:
            # Update config
            self.config.update(new_config)
            self.config['updated_at'] = datetime.utcnow().isoformat()
            
            # Save to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            # Apply changes
            self._apply_config_changes()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Config update failed: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Get full bot status"""
        self._update_stats()
        return {
            'bot_id': self.stats.bot_id,
            'name': self.config.get('name', 'Unknown'),
            'status': self.status.value,
            'enabled': self.config.get('enabled', False),
            'stats': self.stats.to_dict(),
            'config_path': self.config_path,
            'api_testnet': self.config.get('api', {}).get('testnet', False)
        }
    
    def get_logs(self, lines: int = 100) -> list:
        """Get recent log lines"""
        try:
            log_file = self.config.get('logging', {}).get('file')
            if not log_file or not os.path.exists(log_file):
                return []
            
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                return all_lines[-lines:]
                
        except Exception as e:
            return [f"Error reading logs: {e}"]


if __name__ == "__main__":
    # Test single bot
    import time
    
    bot = BotInstance("bot_configs/bot_2_conservative.json")
    
    print("Bot status:", bot.get_status())
    
    # Start (will fail without API keys)
    if bot.start():
        print("Bot started, running for 10 seconds...")
        time.sleep(10)
        bot.stop()
    else:
        print("Failed to start bot")
