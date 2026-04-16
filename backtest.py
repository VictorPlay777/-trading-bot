"""
Backtest module for strategy validation
Tests strategy on historical data before live trading
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Backtest results"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float


class Backtester:
    """Backtest engine for strategy validation"""
    
    def __init__(self, strategy, api_client, symbols: List[str], timeframe: str = "1"):
        self.strategy = strategy
        self.api = api_client
        self.symbols = symbols
        self.timeframe = timeframe
        self.initial_balance = 1000000.0  # $1M like live trading
        
    def fetch_historical_data(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """Fetch historical data for backtesting"""
        try:
            # Calculate limit based on timeframe and days
            limit = min(days * 1440 // int(self.timeframe), 1000)  # Max 1000 candles
            
            klines = self.api.get_klines(symbol, self.timeframe, limit)
            
            if not klines:
                logger.warning(f"No historical data for {symbol}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'turnover', 'volume1', 'avgPrice', 'volume2', 'volume3'
            ])
            
            # Convert types
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            df = df.set_index('timestamp')
            df = df.sort_index()
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()
    
    def simulate_trade(
        self,
        entry_price: float,
        direction: str,
        tp: float,
        sl: float,
        df: pd.DataFrame,
        entry_idx: int
    ) -> Tuple[float, str, int]:
        """
        Simulate a single trade
        Returns: (pnl, exit_reason, duration_bars)
        """
        if direction == "long":
            for i in range(entry_idx, len(df)):
                high = df.iloc[i]['high']
                low = df.iloc[i]['low']
                
                if high >= tp:
                    # Hit TP
                    pnl_pct = (tp - entry_price) / entry_price
                    return pnl_pct, "TP", i - entry_idx
                elif low <= sl:
                    # Hit SL
                    pnl_pct = (sl - entry_price) / entry_price
                    return pnl_pct, "SL", i - entry_idx
            
            # Didn't hit TP or SL - exit at last price
            last_price = df.iloc[-1]['close']
            pnl_pct = (last_price - entry_price) / entry_price
            return pnl_pct, "End", len(df) - entry_idx
            
        else:  # short
            for i in range(entry_idx, len(df)):
                high = df.iloc[i]['high']
                low = df.iloc[i]['low']
                
                if low <= tp:
                    # Hit TP
                    pnl_pct = (entry_price - tp) / entry_price
                    return pnl_pct, "TP", i - entry_idx
                elif high >= sl:
                    # Hit SL
                    pnl_pct = (entry_price - sl) / entry_price
                    return pnl_pct, "SL", i - entry_idx
            
            # Didn't hit TP or SL - exit at last price
            last_price = df.iloc[-1]['close']
            pnl_pct = (entry_price - last_price) / entry_price
            return pnl_pct, "End", len(df) - entry_idx
    
    def run_backtest(self, symbol: str, days: int = 30) -> Optional[BacktestResult]:
        """Run backtest for a single symbol"""
        logger.info(f"Running backtest for {symbol} ({days} days)")
        
        # Fetch historical data
        df = self.fetch_historical_data(symbol, days)
        if df.empty or len(df) < 100:
            logger.warning(f"Insufficient data for {symbol}")
            return None
        
        # Simulate trades
        trades = []
        balance = self.initial_balance
        position = None
        entry_price = 0
        tp = 0
        sl = 0
        direction = ""
        
        for i in range(50, len(df)):  # Start after enough data for indicators
            current_df = df.iloc[:i+1]
            current_price = current_df.iloc[-1]['close']
            
            # Get indicators
            from market_data import MarketDataManager
            market_data = MarketDataManager(self.api)
            try:
                analysis = market_data._calculate_indicators(current_df)
                regime = market_data._detect_regime(current_df, analysis)
                
                # Generate signal
                signal = self.strategy.generate_signal(
                    symbol,
                    current_df,
                    analysis,
                    regime
                )
                
                # Handle entry
                if signal.is_entry and position is None:
                    direction = "long" if signal.signal_type.value == "long_entry" else "short"
                    entry_price = current_price
                    tp = signal.take_profit_1
                    sl = signal.stop_loss
                    
                    # Simulate trade
                    pnl_pct, exit_reason, duration = self.simulate_trade(
                        entry_price, direction, tp, sl, df, i
                    )
                    
                    # Calculate PnL with leverage
                    leverage = 20  # Use same leverage as live
                    pnl = pnl_pct * leverage * (balance * 0.1)  # 10% position size
                    
                    trades.append({
                        'pnl': pnl,
                        'reason': exit_reason,
                        'duration': duration,
                        'entry': entry_price,
                        'exit': entry_price * (1 + pnl_pct) if direction == "long" else entry_price * (1 - pnl_pct)
                    })
                    
                    balance += pnl
                    position = None
                    
            except Exception as e:
                continue
        
        # Calculate metrics
        if not trades:
            logger.warning(f"No trades generated for {symbol}")
            return None
        
        winning_trades = [t for t in trades if t['pnl'] > 0]
        losing_trades = [t for t in trades if t['pnl'] <= 0]
        
        total_trades = len(trades)
        wins = len(winning_trades)
        losses = len(losing_trades)
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        total_pnl = sum(t['pnl'] for t in trades)
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
        
        profit_factor = abs(sum(t['pnl'] for t in winning_trades) / sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
        
        # Calculate max drawdown
        cumulative_pnl = np.cumsum([t['pnl'] for t in trades])
        max_drawdown = (np.max(cumulative_pnl) - np.min(cumulative_pnl)) / self.initial_balance
        
        # Calculate Sharpe ratio (simplified)
        returns = [t['pnl'] / self.initial_balance for t in trades]
        sharpe_ratio = np.mean(returns) / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        result = BacktestResult(
            total_trades=total_trades,
            winning_trades=wins,
            losing_trades=losses,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio
        )
        
        logger.info(f"Backtest results for {symbol}:")
        logger.info(f"  Total trades: {total_trades}")
        logger.info(f"  Win rate: {win_rate:.2%}")
        logger.info(f"  Total PnL: ${total_pnl:.2f}")
        logger.info(f"  Profit factor: {profit_factor:.2f}")
        logger.info(f"  Max drawdown: {max_drawdown:.2%}")
        logger.info(f"  Sharpe ratio: {sharpe_ratio:.2f}")
        
        return result
    
    def run_all_backtests(self, days: int = 30) -> Dict[str, BacktestResult]:
        """Run backtests for all symbols"""
        logger.info("=" * 60)
        logger.info("RUNNING BACKTESTS FOR ALL SYMBOLS")
        logger.info("=" * 60)
        
        results = {}
        for symbol in self.symbols:
            result = self.run_backtest(symbol, days)
            if result:
                results[symbol] = result
        
        # Print summary
        if results:
            logger.info("=" * 60)
            logger.info("BACKTEST SUMMARY")
            logger.info("=" * 60)
            
            avg_win_rate = np.mean([r.win_rate for r in results.values()])
            avg_profit_factor = np.mean([r.profit_factor for r in results.values()])
            total_pnl = sum([r.total_pnl for r in results.values()])
            
            logger.info(f"Average win rate: {avg_win_rate:.2%}")
            logger.info(f"Average profit factor: {avg_profit_factor:.2f}")
            logger.info(f"Total PnL: ${total_pnl:.2f}")
            
            # Recommendation
            if avg_win_rate >= 0.55 and avg_profit_factor >= 1.5:
                logger.info("✅ STRATEGY PASSED - Ready for live trading")
            else:
                logger.warning("⚠️ STRATEGY FAILED - Win rate < 55% or profit factor < 1.5")
                logger.warning("Recommend: Adjust parameters before live trading")
        
        return results


if __name__ == "__main__":
    # Test backtest
    from api_client import BybitClient
    from strategy import SmartScalpingStrategy
    from config import trading_config
    
    api = BybitClient()
    strategy = SmartScalpingStrategy()
    
    backtester = Backtester(strategy, api, trading_config.symbols, trading_config.main_timeframe)
    results = backtester.run_all_backtests(days=7)  # 7 days for quick test
