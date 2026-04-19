"""
Symbol Analytics Module - Tracks per-symbol performance for adaptive trading
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class SymbolStats:
    """Statistics for a single trading symbol"""
    symbol: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0  # After fees
    gross_pnl: float = 0.0  # Before fees
    avg_pnl: float = 0.0
    winrate: float = 0.5  # Default 50%
    last_updated: str = ""
    
    # Extended metrics
    avg_win_amount: float = 0.0
    avg_loss_amount: float = 0.0
    profit_factor: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0


class SymbolAnalytics:
    """
    Tracks and analyzes per-symbol trading performance
    Provides adaptive position sizing and symbol filtering
    """
    
    def __init__(self, stats_file: str = "symbol_stats.json"):
        self.stats_file = stats_file
        self.stats: Dict[str, SymbolStats] = {}
        self.load_stats()
    
    def load_stats(self):
        """Load statistics from JSON file"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    for symbol, stats_dict in data.items():
                        self.stats[symbol] = SymbolStats(**stats_dict)
                print(f"[ANALYTICS] Loaded stats for {len(self.stats)} symbols")
            except Exception as e:
                print(f"[ANALYTICS] Error loading stats: {e}")
                self.stats = {}
        else:
            print(f"[ANALYTICS] No existing stats file, starting fresh")
            self.stats = {}
    
    def save_stats(self):
        """Save statistics to JSON file"""
        try:
            data = {symbol: asdict(stats) for symbol, stats in self.stats.items()}
            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ANALYTICS] Error saving stats: {e}")
    
    def record_trade(self, symbol: str, pnl: float, is_win: bool, fees: float = 0):
        """
        Record a completed trade
        
        Args:
            symbol: Trading pair
            pnl: Profit/Loss percentage (e.g., 2.5 for 2.5%)
            is_win: True if trade was profitable
            fees: Total fees paid
        """
        if symbol not in self.stats:
            self.stats[symbol] = SymbolStats(symbol=symbol)
        
        stats = self.stats[symbol]
        stats.trades += 1
        stats.gross_pnl += pnl
        stats.total_pnl += (pnl - fees)
        
        if is_win:
            stats.wins += 1
            stats.consecutive_wins += 1
            stats.consecutive_losses = 0
            stats.avg_win_amount = (stats.avg_win_amount * (stats.wins - 1) + pnl) / stats.wins
        else:
            stats.losses += 1
            stats.consecutive_losses += 1
            stats.consecutive_wins = 0
            stats.avg_loss_amount = (stats.avg_loss_amount * (stats.losses - 1) + abs(pnl)) / stats.losses
        
        # Recalculate derived metrics
        stats.winrate = stats.wins / stats.trades if stats.trades > 0 else 0.5
        stats.avg_pnl = stats.total_pnl / stats.trades if stats.trades > 0 else 0
        
        # Profit factor = gross profit / gross loss
        total_wins = stats.wins * stats.avg_win_amount if stats.wins > 0 else 0
        total_losses = stats.losses * stats.avg_loss_amount if stats.losses > 0 else 0.001
        stats.profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        stats.last_updated = datetime.now().isoformat()
        
        # Auto-save every 5 trades
        if stats.trades % 5 == 0:
            self.save_stats()
    
    def get_position_size_multiplier(self, symbol: str) -> float:
        """
        Calculate position size multiplier based on symbol performance
        
        Returns:
            Multiplier (0.1 to 3.0) for base position size
        """
        stats = self.stats.get(symbol)
        
        if not stats or stats.trades < 5:
            # New symbol - trade small to test
            return 0.3
        
        # Based on win rate
        if stats.winrate >= 0.70:
            return 3.0  # Excellent - full size
        elif stats.winrate >= 0.60:
            return 2.0  # Good - increase
        elif stats.winrate >= 0.55:
            return 1.0  # OK - normal size
        elif stats.winrate >= 0.50:
            return 0.5  # Marginal - reduce
        else:
            return 0.2  # Poor - minimal
    
    def get_risk_reward_ratio(self, symbol: str) -> float:
        """
        Get dynamic R:R ratio based on win rate
        
        Returns:
            Risk/Reward ratio (e.g., 2.0 means 2:1)
        """
        stats = self.stats.get(symbol)
        
        if not stats or stats.trades < 10:
            return 1.5  # Conservative for new symbols
        
        if stats.winrate >= 0.65:
            return 2.5  # High win rate - can risk more
        elif stats.winrate >= 0.55:
            return 2.0
        elif stats.winrate >= 0.50:
            return 1.5
        else:
            return 1.0  # Low win rate - tight targets
    
    def should_trade_symbol(self, symbol: str, min_trades: int = 10, min_winrate: float = 0.55) -> bool:
        """
        Determine if we should trade this symbol
        
        Args:
            symbol: Trading pair to check
            min_trades: Minimum trades for statistical significance
            min_winrate: Minimum win rate to allow trading
            
        Returns:
            True if symbol passes filters
        """
        stats = self.stats.get(symbol)
        
        if not stats:
            # New symbol - allow with small size
            return True
        
        if stats.trades < min_trades:
            # Not enough data - allow for testing
            return True
        
        # Check win rate
        if stats.winrate < min_winrate:
            print(f"[FILTER] {symbol}: Win rate {stats.winrate*100:.1f}% < {min_winrate*100:.1f}%, skipping")
            return False
        
        # Check if consistently losing
        if stats.consecutive_losses >= 3:
            print(f"[FILTER] {symbol}: {stats.consecutive_losses} consecutive losses, cooling off")
            return False
        
        # Check profit factor
        if stats.profit_factor < 0.8 and stats.trades >= 10:
            print(f"[FILTER] {symbol}: Profit factor {stats.profit_factor:.2f} too low")
            return False
        
        return True
    
    def get_top_symbols(self, n: int = 30, min_trades: int = 5) -> list:
        """
        Get top N performing symbols by win rate
        
        Returns:
            List of (symbol, stats) tuples sorted by win rate
        """
        eligible = [
            (symbol, stats) for symbol, stats in self.stats.items()
            if stats.trades >= min_trades and stats.winrate >= 0.55
        ]
        
        # Sort by win rate, then by profit factor
        eligible.sort(key=lambda x: (x[1].winrate, x[1].profit_factor), reverse=True)
        
        return eligible[:n]
    
    def print_summary(self):
        """Print summary of top and worst performers"""
        if not self.stats:
            print("[ANALYTICS] No statistics available yet")
            return
        
        # Sort by total PnL
        sorted_stats = sorted(
            self.stats.items(),
            key=lambda x: x[1].total_pnl,
            reverse=True
        )
        
        print("\n" + "="*80)
        print("🏆 TOP 10 PERFORMING SYMBOLS")
        print("="*80)
        print(f"{'Symbol':<15} {'Trades':>8} {'Win%':>8} {'Total PnL%':>12} {'Avg PnL%':>10} {'P.F.':>8}")
        print("-"*80)
        
        for symbol, stats in sorted_stats[:10]:
            print(f"{symbol:<15} {stats.trades:>8} {stats.winrate*100:>7.1f}% {stats.total_pnl:>11.2f}% {stats.avg_pnl:>9.2f}% {stats.profit_factor:>7.2f}")
        
        print("\n" + "="*80)
        print("💀 BOTTOM 10 PERFORMERS")
        print("="*80)
        print(f"{'Symbol':<15} {'Trades':>8} {'Win%':>8} {'Total PnL%':>12} {'Avg PnL%':>10} {'P.F.':>8}")
        print("-"*80)
        
        for symbol, stats in sorted_stats[-10:]:
            print(f"{symbol:<15} {stats.trades:>8} {stats.winrate*100:>7.1f}% {stats.total_pnl:>11.2f}% {stats.avg_pnl:>9.2f}% {stats.profit_factor:>7.2f}")
        
        print("="*80)
        print(f"\nTotal symbols tracked: {len(self.stats)}")
        print(f"Symbols with >55% win rate: {sum(1 for s in self.stats.values() if s.winrate >= 0.55)}")
        print(f"Symbols with <50% win rate: {sum(1 for s in self.stats.values() if s.winrate < 0.50)}")
        print("="*80 + "\n")


# Singleton instance for global access
_analytics = None

def get_analytics(stats_file: str = "symbol_stats.json") -> SymbolAnalytics:
    """Get or create global analytics instance"""
    global _analytics
    if _analytics is None:
        _analytics = SymbolAnalytics(stats_file)
    return _analytics
