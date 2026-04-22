import logging
from typing import Dict, Set, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class SurvivalEngine:
    """
    Survival engine for coin selection.
    Blacklists underperforming coins and manages cooldown periods.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.health_config = config.get("health", {})
        self.survival_config = config.get("survival", {})
        
        # Survival settings
        self.enable_survival_mode = self.health_config.get("enable_survival_mode", True)
        self.loss_streak_blacklist = self.health_config.get("loss_streak_blacklist", 4)
        self.blacklist_duration_minutes = self.health_config.get("blacklist_duration_minutes", 1440)
        
        self.enable_blacklist = self.survival_config.get("enable_blacklist", True)
        self.enable_decay_system = self.survival_config.get("enable_decay_system", True)
        self.recovery_enabled = self.survival_config.get("recovery_enabled", True)
        
        # Blacklist management
        self.blacklist: Set[str] = set()
        self.blacklist_expiry: Dict[str, datetime] = {}  # symbol -> expiry time
        self.blacklist_reasons: Dict[str, str] = {}  # symbol -> reason
        
        # Per-symbol tracking
        self.loss_streaks: Dict[str, int] = defaultdict(int)
        self.trade_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self.last_trade_time: Dict[str, datetime] = {}
        
        # Performance tracking
        self.recovery_stats: Dict[str, dict] = defaultdict(lambda: {
            "blacklist_count": 0,
            "recovery_count": 0,
            "total_pnl": 0.0
        })
        
    def record_trade(self, symbol: str, pnl: float):
        """Record trade result and check for blacklist conditions."""
        if not self.enable_survival_mode:
            return
            
        self.trade_history[symbol].append({
            "pnl": pnl,
            "timestamp": datetime.now()
        })
        self.last_trade_time[symbol] = datetime.now()
        
        # Update loss streak
        if pnl < 0:
            self.loss_streaks[symbol] += 1
        else:
            self.loss_streaks[symbol] = 0
            
        # Check blacklist condition
        if self.enable_blacklist and self.loss_streaks[symbol] >= self.loss_streak_blacklist:
            self._add_to_blacklist(
                symbol,
                reason=f"Loss streak of {self.loss_streaks[symbol]} trades"
            )
            
    def _add_to_blacklist(self, symbol: str, reason: str):
        """Add symbol to blacklist with cooldown period."""
        if symbol in self.blacklist:
            return
            
        expiry = datetime.now() + timedelta(minutes=self.blacklist_duration_minutes)
        
        self.blacklist.add(symbol)
        self.blacklist_expiry[symbol] = expiry
        self.blacklist_reasons[symbol] = reason
        
        self.recovery_stats[symbol]["blacklist_count"] += 1
        
        logger.warning(f"Added {symbol} to blacklist: {reason} (expires {expiry})")
        
    def remove_from_blacklist(self, symbol: str):
        """Remove symbol from blacklist (manual override)."""
        if symbol in self.blacklist:
            self.blacklist.remove(symbol)
            del self.blacklist_expiry[symbol]
            del self.blacklist_reasons[symbol]
            
            self.recovery_stats[symbol]["recovery_count"] += 1
            logger.info(f"Removed {symbol} from blacklist (manual)")
            
    def check_blacklist_expiry(self):
        """Check and remove expired blacklist entries."""
        now = datetime.now()
        expired_symbols = []
        
        for symbol, expiry in self.blacklist_expiry.items():
            if now >= expiry and self.recovery_enabled:
                expired_symbols.append(symbol)
                
        for symbol in expired_symbols:
            self.remove_from_blacklist(symbol)
            logger.info(f"Removed {symbol} from blacklist (cooldown expired)")
            
    def is_blacklisted(self, symbol: str) -> bool:
        """Check if symbol is currently blacklisted."""
        return symbol in self.blacklist
        
    def get_blacklist_info(self, symbol: str) -> Optional[dict]:
        """Get blacklist information for symbol."""
        if symbol not in self.blacklist:
            return None
            
        return {
            "symbol": symbol,
            "reason": self.blacklist_reasons.get(symbol, "Unknown"),
            "expiry": self.blacklist_expiry.get(symbol),
            "time_remaining": (self.blacklist_expiry[symbol] - datetime.now()).total_seconds()
        }
        
    def get_all_blacklisted(self) -> Dict[str, dict]:
        """Get all blacklisted symbols with info."""
        return {
            symbol: self.get_blacklist_info(symbol)
            for symbol in self.blacklist
        }
        
    def get_loss_streak(self, symbol: str) -> int:
        """Get current loss streak for symbol."""
        return self.loss_streaks.get(symbol, 0)
        
    def get_trade_history(self, symbol: str, limit: int = 10) -> list:
        """Get recent trade history for symbol."""
        history = list(self.trade_history.get(symbol, []))
        return history[-limit:]
        
    def get_recovery_stats(self, symbol: str) -> dict:
        """Get recovery statistics for symbol."""
        return self.recovery_stats[symbol].copy()
        
    def apply_decay(self):
        """Apply decay to loss streaks if decay system is enabled."""
        if not self.enable_decay_system:
            return
            
        now = datetime.now()
        decay_threshold = timedelta(minutes=30)  # Decay after 30 minutes
        
        for symbol in list(self.loss_streaks.keys()):
            last_trade = self.last_trade_time.get(symbol)
            if last_trade and (now - last_trade) > decay_threshold:
                # Decay loss streak
                self.loss_streaks[symbol] = max(0, self.loss_streaks[symbol] - 1)
                
    def get_survival_summary(self) -> dict:
        """Get summary of survival engine state."""
        return {
            "blacklisted_count": len(self.blacklist),
            "blacklisted_symbols": list(self.blacklist),
            "symbols_with_loss_streak": {
                symbol: streak
                for symbol, streak in self.loss_streaks.items()
                if streak > 0
            },
            "recovery_stats": {
                symbol: stats
                for symbol, stats in self.recovery_stats.items()
                if stats["blacklist_count"] > 0
            }
        }


from collections import defaultdict, deque
