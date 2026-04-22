import numpy as np
import logging
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class ScoringEngine:
    """
    Health score calculation for each coin.
    Combines multiple metrics into a single health score.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.scoring_config = config.get("scoring", {})
        
        # Scoring weights
        self.pnl_weight = self.scoring_config.get("pnl_weight", 2.0)
        self.volatility_weight = self.scoring_config.get("volatility_weight", 1.2)
        self.volume_weight = self.scoring_config.get("volume_weight", 1.5)
        self.momentum_weight = self.scoring_config.get("momentum_weight", 2.0)
        
        # Per-symbol metrics
        self.pnl_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.volume_scores: Dict[str, float] = {}
        self.volatility_scores: Dict[str, float] = {}
        self.momentum_scores: Dict[str, float] = {}
        self.health_scores: Dict[str, float] = {}
        
        # Performance tracking
        self.total_pnl: Dict[str, float] = {}
        self.trade_count: Dict[str, int] = {}
        self.win_count: Dict[str, int] = {}
        
    def record_trade(self, symbol: str, pnl: float):
        """Record trade result for scoring."""
        self.pnl_history[symbol].append(pnl)
        
        # Update totals
        self.total_pnl[symbol] = self.total_pnl.get(symbol, 0) + pnl
        self.trade_count[symbol] = self.trade_count.get(symbol, 0) + 1
        if pnl > 0:
            self.win_count[symbol] = self.win_count.get(symbol, 0) + 1
            
    def update_volume_score(self, symbol: str, volume: float):
        """Update volume score based on relative volume."""
        # Normalize volume score (0-1) based on recent history
        if symbol not in self.volume_scores:
            self.volume_scores[symbol] = 0.5
            
        # Simple moving average for smoothing
        current_score = self.volume_scores[symbol]
        target_score = min(volume / 1000000, 1.0)  # Normalize to 1M volume
        self.volume_scores[symbol] = current_score * 0.8 + target_score * 0.2
        
    def update_volatility_score(self, symbol: str, price_history: List[float]):
        """Update volatility score based on price movement."""
        if len(price_history) < 20:
            self.volatility_scores[symbol] = 0.5
            return
            
        # Calculate volatility (std dev / mean)
        volatility = np.std(price_history[-20:]) / np.mean(price_history[-20:])
        
        # Normalize to 0-1 range (0.5% - 5% volatility)
        min_vol = 0.005
        max_vol = 0.05
        normalized = (volatility - min_vol) / (max_vol - min_vol)
        normalized = max(0, min(1, normalized))
        
        self.volatility_scores[symbol] = normalized
        
    def update_momentum_score(self, symbol: str, signal_strength: float):
        """Update momentum score based on signal strength."""
        if symbol not in self.momentum_scores:
            self.momentum_scores[symbol] = 0.5
            
        # Decay old score, add new signal
        current_score = self.momentum_scores[symbol]
        self.momentum_scores[symbol] = current_score * 0.9 + signal_strength * 0.1
        
    def calculate_health_score(self, symbol: str) -> float:
        """
        Calculate health score for symbol.
        Combines PnL, volume, volatility, and momentum scores.
        """
        # PnL score (0-1)
        pnl_score = self._calculate_pnl_score(symbol)
        
        # Volume score (0-1)
        volume_score = self.volume_scores.get(symbol, 0.5)
        
        # Volatility score (0-1)
        volatility_score = self.volatility_scores.get(symbol, 0.5)
        
        # Momentum score (0-1)
        momentum_score = self.momentum_scores.get(symbol, 0.5)
        
        # Weighted combination
        total_weight = (
            self.pnl_weight + 
            self.volume_weight + 
            self.volatility_weight + 
            self.momentum_weight
        )
        
        health_score = (
            (pnl_score * self.pnl_weight) +
            (volume_score * self.volume_weight) +
            (volatility_score * self.volatility_weight) +
            (momentum_score * self.momentum_weight)
        ) / total_weight
        
        self.health_scores[symbol] = health_score
        return health_score
        
    def _calculate_pnl_score(self, symbol: str) -> float:
        """Calculate PnL score based on recent performance."""
        if symbol not in self.total_pnl or self.trade_count.get(symbol, 0) == 0:
            return 0.5  # Neutral score for new symbols
            
        total_pnl = self.total_pnl[symbol]
        trade_count = self.trade_count[symbol]
        win_rate = self.win_count.get(symbol, 0) / trade_count if trade_count > 0 else 0.5
        
        # Score based on win rate and PnL
        # Win rate: 0.5 is neutral, >0.5 is good
        win_rate_score = (win_rate - 0.5) * 2  # -1 to 1
        
        # PnL score: normalize based on trade count
        avg_pnl = total_pnl / trade_count if trade_count > 0 else 0
        pnl_score = min(avg_pnl * 100, 1.0)  # Scale to 0-1
        
        # Combine
        combined = (win_rate_score + pnl_score) / 2
        return max(0, min(1, combined + 0.5))  # Normalize to 0-1
        
    def get_health_score(self, symbol: str) -> float:
        """Get current health score for symbol."""
        return self.health_scores.get(symbol, 0.5)
        
    def get_all_scores(self) -> Dict[str, float]:
        """Get all health scores."""
        return self.health_scores.copy()
        
    def get_top_symbols(self, n: int = 50) -> List[tuple]:
        """Get top N symbols by health score."""
        sorted_scores = sorted(
            self.health_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_scores[:n]
        
    def get_symbol_stats(self, symbol: str) -> dict:
        """Get detailed stats for a symbol."""
        return {
            "health_score": self.health_scores.get(symbol, 0.5),
            "pnl_score": self._calculate_pnl_score(symbol),
            "volume_score": self.volume_scores.get(symbol, 0.5),
            "volatility_score": self.volatility_scores.get(symbol, 0.5),
            "momentum_score": self.momentum_scores.get(symbol, 0.5),
            "total_pnl": self.total_pnl.get(symbol, 0),
            "trade_count": self.trade_count.get(symbol, 0),
            "win_count": self.win_count.get(symbol, 0),
            "win_rate": self.win_count.get(symbol, 0) / self.trade_count.get(symbol, 1) if self.trade_count.get(symbol, 0) > 0 else 0
        }


from collections import defaultdict, deque
