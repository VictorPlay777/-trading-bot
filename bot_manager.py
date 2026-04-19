"""
Bot Manager - Orchestrates multiple trading bot instances
Manages lifecycle, monitoring, and comparison of all bots
"""
import os
import json
import time
import glob
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from threading import Lock

from bot_instance import BotInstance, BotStats


@dataclass
class BotComparison:
    """Comparison metrics between bots"""
    bot_id: str
    name: str
    status: str
    
    # Performance
    win_rate: float
    total_pnl: float
    total_trades: int
    profit_factor: float
    
    # Risk
    max_drawdown: float
    avg_trade_pnl: float
    
    # Activity
    active_positions: int
    uptime_hours: float
    
    # Ranking
    performance_score: float = 0.0  # Composite score
    rank: int = 0


class BotManager:
    """
    Central orchestrator for multiple trading bots:
    - Discovery: Auto-finds bot configs in bot_configs/
    - Lifecycle: Start/stop/pause bots individually
    - Monitoring: Real-time stats from all bots
    - Comparison: Performance ranking
    - Safety: Isolated processes and API keys
    """
    
    def __init__(self, configs_dir: str = "bot_configs"):
        self.configs_dir = configs_dir
        self.bots: Dict[str, BotInstance] = {}
        self.stats_cache: Dict[str, Dict] = {}
        self.stats_lock = Lock()
        
        # Logger
        self.logger = logging.getLogger("BotManager")
        self._setup_logging()
        
        # Auto-discovery
        self._discover_bots()
    
    def _setup_logging(self):
        """Setup manager logging"""
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s | %(name)s | %(levelname)-8s | %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _discover_bots(self):
        """Auto-discover bot configurations"""
        config_pattern = os.path.join(self.configs_dir, "*.json")
        config_files = glob.glob(config_pattern)
        
        self.logger.info(f"Discovered {len(config_files)} bot configurations")
        
        for config_path in config_files:
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                bot_id = config.get('bot_id')
                if not bot_id:
                    self.logger.warning(f"Skipping {config_path}: no bot_id")
                    continue
                
                # Create bot instance (but don't start yet)
                bot = BotInstance(
                    config_path=config_path,
                    on_stats_update=lambda stats, bid=bot_id: self._on_bot_stats_update(bid, stats)
                )
                
                self.bots[bot_id] = bot
                self.logger.info(f"Registered bot: {bot_id} ({config.get('name')})")
                
            except Exception as e:
                self.logger.error(f"Failed to load {config_path}: {e}")
    
    def _on_bot_stats_update(self, bot_id: str, stats: Dict):
        """Callback when bot updates its stats"""
        with self.stats_lock:
            self.stats_cache[bot_id] = {
                **stats,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    # === Bot Lifecycle ===
    
    def start_bot(self, bot_id: str) -> bool:
        """Start a specific bot"""
        if bot_id not in self.bots:
            self.logger.error(f"Bot not found: {bot_id}")
            return False
        
        bot = self.bots[bot_id]
        
        if bot.status.value == "running":
            self.logger.info(f"Bot {bot_id} already running")
            return True
        
        self.logger.info(f"Starting bot {bot_id}...")
        
        try:
            # Pass all bots to check for API conflicts
            success = bot.start(list(self.bots.values()))
            if success:
                self.logger.info(f"Bot {bot_id} started successfully")
            else:
                self.logger.error(f"Failed to start bot {bot_id}")
            return success
            
        except Exception as e:
            self.logger.error(f"Error starting bot {bot_id}: {e}")
            return False
    
    def stop_bot(self, bot_id: str) -> bool:
        """Stop a specific bot"""
        if bot_id not in self.bots:
            return False
        
        bot = self.bots[bot_id]
        self.logger.info(f"Stopping bot {bot_id}...")
        
        try:
            return bot.stop()
        except Exception as e:
            self.logger.error(f"Error stopping bot {bot_id}: {e}")
            return False
    
    def pause_bot(self, bot_id: str) -> bool:
        """Pause a bot (keep positions)"""
        if bot_id not in self.bots:
            return False
        
        return self.bots[bot_id].pause()
    
    def resume_bot(self, bot_id: str) -> bool:
        """Resume a paused bot"""
        if bot_id not in self.bots:
            return False
        
        return self.bots[bot_id].resume()
    
    def start_all(self) -> Dict[str, bool]:
        """Start all enabled bots (only first bot per unique API)"""
        results = {}
        used_apis = set()
        
        for bot_id, bot in self.bots.items():
            if bot.config.get('enabled', False):
                api_key = bot.config.get('api', {}).get('key', '')
                
                if api_key in used_apis:
                    results[bot_id] = False
                    self.logger.warning(f"Bot {bot_id} skipped: API key already used by another bot!")
                    self.logger.warning(f"Only ONE bot can run per API key. Stop other bot first.")
                else:
                    results[bot_id] = self.start_bot(bot_id)
                    if results[bot_id]:
                        used_apis.add(api_key)
            else:
                results[bot_id] = None  # Skipped
                self.logger.info(f"Bot {bot_id} skipped (disabled)")
        
        return results
    
    def stop_all(self) -> Dict[str, bool]:
        """Stop all running bots"""
        results = {}
        
        for bot_id, bot in self.bots.items():
            if bot.status.value == "running":
                results[bot_id] = self.stop_bot(bot_id)
            else:
                results[bot_id] = None  # Already stopped
        
        return results
    
    # === Configuration ===
    
    def create_bot(self, config: Dict) -> Optional[str]:
        """Create new bot configuration"""
        try:
            bot_id = config.get('bot_id')
            if not bot_id:
                # Generate ID
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                bot_id = f"bot_{timestamp}"
                config['bot_id'] = bot_id
            
            # Check for duplicate
            if bot_id in self.bots:
                self.logger.error(f"Bot {bot_id} already exists")
                return None
            
            # Save config
            config_path = os.path.join(self.configs_dir, f"{bot_id}.json")
            config['created_at'] = datetime.utcnow().isoformat()
            config['updated_at'] = config['created_at']
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Create instance
            bot = BotInstance(
                config_path=config_path,
                on_stats_update=lambda stats, bid=bot_id: self._on_bot_stats_update(bid, stats)
            )
            
            self.bots[bot_id] = bot
            self.logger.info(f"Created new bot: {bot_id}")
            
            return bot_id
            
        except Exception as e:
            self.logger.error(f"Failed to create bot: {e}")
            return None
    
    def update_bot_config(self, bot_id: str, updates: Dict) -> bool:
        """Update bot configuration (hot-reload)"""
        if bot_id not in self.bots:
            return False
        
        try:
            bot = self.bots[bot_id]
            return bot.update_config(updates)
            
        except Exception as e:
            self.logger.error(f"Failed to update bot {bot_id}: {e}")
            return False
    
    def delete_bot(self, bot_id: str) -> bool:
        """Delete a bot (must be stopped first)"""
        if bot_id not in self.bots:
            return False
        
        bot = self.bots[bot_id]
        
        if bot.status.value == "running":
            self.logger.error(f"Cannot delete running bot {bot_id}")
            return False
        
        try:
            # Remove config file
            if os.path.exists(bot.config_path):
                os.remove(bot.config_path)
            
            # Remove from registry
            del self.bots[bot_id]
            
            self.logger.info(f"Deleted bot {bot_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete bot {bot_id}: {e}")
            return False
    
    # === Monitoring & Stats ===
    
    def get_bot_status(self, bot_id: str) -> Optional[Dict]:
        """Get detailed status of a bot"""
        if bot_id not in self.bots:
            return None
        
        return self.bots[bot_id].get_status()
    
    def get_all_status(self) -> List[Dict]:
        """Get status of all bots"""
        return [bot.get_status() for bot in self.bots.values()]
    
    def get_bot_logs(self, bot_id: str, lines: int = 100) -> List[str]:
        """Get logs from a specific bot"""
        if bot_id not in self.bots:
            return [f"Bot {bot_id} not found"]
        
        return self.bots[bot_id].get_logs(lines)
    
    def compare_bots(self) -> List[BotComparison]:
        """Compare performance of all bots"""
        comparisons = []
        
        for bot_id, bot in self.bots.items():
            status = bot.get_status()
            stats = status.get('stats', {})
            
            comp = BotComparison(
                bot_id=bot_id,
                name=status.get('name', 'Unknown'),
                status=status.get('status', 'unknown'),
                win_rate=stats.get('win_rate', 0),
                total_pnl=stats.get('total_pnl', 0),
                total_trades=stats.get('total_trades', 0),
                profit_factor=stats.get('profit_factor', 0),
                max_drawdown=stats.get('max_drawdown', 0),
                avg_trade_pnl=stats.get('avg_win', 0) if stats.get('win_rate', 0) > 0.5 else stats.get('avg_loss', 0),
                active_positions=stats.get('active_positions', 0),
                uptime_hours=stats.get('uptime_seconds', 0) / 3600
            )
            
            # Calculate composite score
            # Weight: PnL (40%), Win Rate (30%), Profit Factor (20%), Drawdown (10%)
            if comp.total_trades > 0:
                pnl_score = min(comp.total_pnl / 100, 10) * 4  # Cap at 1000% PnL
                wr_score = comp.win_rate * 3
                pf_score = min(comp.profit_factor, 5) * 2  # Cap at 5.0
                dd_score = max(0, 10 - comp.max_drawdown)  # Lower drawdown = higher score
                
                comp.performance_score = pnl_score + wr_score + pf_score + dd_score
            
            comparisons.append(comp)
        
        # Sort by performance score
        comparisons.sort(key=lambda x: x.performance_score, reverse=True)
        
        # Assign ranks
        for i, comp in enumerate(comparisons):
            comp.rank = i + 1
        
        return comparisons
    
    def get_leaderboard(self) -> List[Dict]:
        """Get performance leaderboard"""
        comparisons = self.compare_bots()
        
        return [
            {
                'rank': c.rank,
                'bot_id': c.bot_id,
                'name': c.name,
                'status': c.status,
                'win_rate': f"{c.win_rate*100:.1f}%",
                'total_pnl': f"${c.total_pnl:.2f}",
                'total_trades': c.total_trades,
                'score': f"{c.performance_score:.1f}",
                'active_positions': c.active_positions
            }
            for c in comparisons
        ]
    
    def get_aggregate_stats(self) -> Dict:
        """Get aggregate stats across all bots"""
        all_stats = self.get_all_status()
        
        total_bots = len(all_stats)
        running_bots = sum(1 for s in all_stats if s.get('status') == 'running')
        
        total_trades = sum(s.get('stats', {}).get('total_trades', 0) for s in all_stats)
        total_pnl = sum(s.get('stats', {}).get('total_pnl', 0) for s in all_stats)
        total_positions = sum(s.get('stats', {}).get('active_positions', 0) for s in all_stats)
        
        return {
            'total_bots': total_bots,
            'running_bots': running_bots,
            'stopped_bots': total_bots - running_bots,
            'aggregate_trades': total_trades,
            'aggregate_pnl': total_pnl,
            'aggregate_positions': total_positions,
            'timestamp': datetime.utcnow().isoformat()
        }


# Global manager instance
_manager: Optional[BotManager] = None


def get_manager() -> BotManager:
    """Get or create global bot manager"""
    global _manager
    if _manager is None:
        _manager = BotManager()
    return _manager


if __name__ == "__main__":
    # Test manager
    manager = BotManager()
    
    print("Registered bots:")
    for bot_id in manager.bots.keys():
        print(f"  - {bot_id}")
    
    print("\nStatus:")
    for status in manager.get_all_status():
        print(f"  {status['bot_id']}: {status['status']}")
