"""
Professional Advanced Metrics Calculator - Calculate derived metrics from raw data
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from statistics import mean, median, stdev
from loguru import logger


class AdvancedMetricsCalculator:
    """Calculate advanced risk and performance metrics from raw trade data"""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
    
    def calculate_trade_statistics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate comprehensive trade statistics"""
        if not trades:
            return self._empty_trade_stats()
        
        winning_trades = [t for t in trades if t.get('net_pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('net_pnl', 0) < 0]
        
        total_trades = len(trades)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        gross_profit = sum(t.get('gross_pnl', 0) for t in winning_trades)
        gross_loss = abs(sum(t.get('gross_pnl', 0) for t in losing_trades))
        net_profit = sum(t.get('net_pnl', 0) for t in trades)
        
        wins = [t.get('net_pnl', 0) for t in winning_trades]
        losses = [abs(t.get('net_pnl', 0)) for t in losing_trades]
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_count,
            "losing_trades": losing_count,
            "win_rate": winning_count / total_trades if total_trades > 0 else 0.0,
            
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_profit": net_profit,
            
            "average_win": mean(wins) if wins else 0.0,
            "average_loss": mean(losses) if losses else 0.0,
            "median_win": median(wins) if wins else 0.0,
            "median_loss": median(losses) if losses else 0.0,
            
            "profit_factor": (gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)),
            "expectancy": net_profit / total_trades if total_trades > 0 else 0.0,
            
            "average_r": mean([t.get('r_multiple', 0) for t in trades]) if trades else 0.0,
            "median_r": median([t.get('r_multiple', 0) for t in trades]) if trades else 0.0,
            
            "max_win": max(wins) if wins else 0.0,
            "max_loss": max(losses) if losses else 0.0,
            
            "max_consecutive_wins": self._calculate_max_consecutive(trades, True),
            "max_consecutive_losses": self._calculate_max_consecutive(trades, False),
            
            "average_holding_time": mean([t.get('holding_time', 0) for t in trades]) if trades else 0.0,
            "median_holding_time": median([t.get('holding_time', 0) for t in trades]) if trades else 0.0
        }
    
    def calculate_risk_statistics(self, equity_snapshots: List[Dict[str, Any]], 
                                  trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate comprehensive risk statistics"""
        if not equity_snapshots:
            return self._empty_risk_stats()
        
        # Extract equity curve
        equity_curve = [s.get('equity', 0) for s in equity_snapshots]
        timestamps = [s.get('timestamp', 0) for s in equity_snapshots]
        
        if len(equity_curve) < 2:
            return self._empty_risk_stats()
        
        # Calculate returns
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                returns.append((equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1])
        
        if not returns:
            return self._empty_risk_stats()
        
        # Calculate drawdowns
        peak_equity = max(equity_curve)
        max_drawdown = peak_equity - min(equity_curve)
        max_drawdown_pct = (max_drawdown / peak_equity * 100) if peak_equity > 0 else 0.0
        
        # Calculate average drawdown
        drawdowns = []
        current_peak = equity_curve[0]
        for equity in equity_curve:
            if equity > current_peak:
                current_peak = equity
            drawdown = (current_peak - equity) / current_peak if current_peak > 0 else 0
            if drawdown > 0:
                drawdowns.append(drawdown)
        
        avg_drawdown = mean(drawdowns) * 100 if drawdowns else 0.0
        
        # Risk metrics
        avg_return = mean(returns)
        std_return = stdev(returns) if len(returns) > 1 else 0.0
        
        sharpe_ratio = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0.0
        
        # Sortino (downside deviation)
        negative_returns = [r for r in returns if r < 0]
        downside_std = stdev(negative_returns) if len(negative_returns) > 1 else 0.0
        sortino_ratio = (avg_return / downside_std * (252 ** 0.5)) if downside_std > 0 else 0.0
        
        # Calmar ratio
        calmar_ratio = (avg_return * 252 / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
        
        # Recovery factor
        recovery_factor = (sum(t.get('net_pnl', 0) for t in trades) / max_drawdown) if max_drawdown > 0 else 0.0
        
        return {
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "average_drawdown": avg_drawdown,
            
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "recovery_factor": recovery_factor
        }
    
    def calculate_categorized_statistics(self, trades: List[Dict[str, Any]], 
                                         category: str) -> Dict[str, Any]:
        """Calculate statistics by category (symbol, direction, timeframe, etc.)"""
        if not trades:
            return {}
        
        # Group by category
        grouped = {}
        for trade in trades:
            key = trade.get(category, 'unknown')
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(trade)
        
        # Calculate statistics for each group
        results = {}
        for key, group_trades in grouped.items():
            results[key] = self.calculate_trade_statistics(group_trades)
        
        return results
    
    def calculate_time_based_statistics(self, trades: List[Dict[str, Any]], 
                                       period: str = 'daily') -> Dict[str, Any]:
        """Calculate statistics by time period (daily, weekly, monthly)"""
        if not trades:
            return {}
        
        # Group by time period
        grouped = {}
        for trade in trades:
            timestamp = trade.get('exit_timestamp', trade.get('entry_timestamp', 0))
            if timestamp == 0:
                continue
            
            if period == 'daily':
                key = time.strftime('%Y-%m-%d', time.gmtime(timestamp))
            elif period == 'weekly':
                key = time.strftime('%Y-W%W', time.gmtime(timestamp))
            elif period == 'monthly':
                key = time.strftime('%Y-%m', time.gmtime(timestamp))
            else:
                key = 'unknown'
            
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(trade)
        
        # Calculate statistics for each period
        results = {}
        for key, period_trades in grouped.items():
            results[key] = self.calculate_trade_statistics(period_trades)
        
        return results
    
    def _calculate_max_consecutive(self, trades: List[Dict[str, Any]], wins: bool) -> int:
        """Calculate maximum consecutive wins or losses"""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in trades:
            is_win = trade.get('net_pnl', 0) > 0
            if is_win == wins:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _empty_trade_stats(self) -> Dict[str, Any]:
        """Return empty trade statistics"""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_profit": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "median_win": 0.0,
            "median_loss": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "average_r": 0.0,
            "median_r": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "average_holding_time": 0.0,
            "median_holding_time": 0.0
        }
    
    def _empty_risk_stats(self) -> Dict[str, Any]:
        """Return empty risk statistics"""
        return {
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "average_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "recovery_factor": 0.0
        }