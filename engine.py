"""
Engine - Central cycle for Adaptive Momentum Trading Bot
"""
import logging
import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime
import time
import random

from momentum_engine import MomentumEngine, MomentumSignal
from signal_engine import SignalEngine, Signal
from position_manager import PositionManager, Position, TradeType
from learning import LearningModule
from liquidity_engine import LiquidityEngine, LiquidityAnalysis
from liquidation_engine import LiquidationEngine, LiquidationSignal
from api_client import BybitClient
from config import trading_config, strategy_config

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Central cycle for Adaptive Momentum Trading Bot
    
    Each cycle:
    1. Get market data
    2. Momentum detection -> open MOMENTUM trade if found
    3. Signal detection -> open SCOUT trade if found
    4. Probe logic -> occasionally open PROBE trade
    5. Position management -> stops, pyramiding, trailing, closures
    6. Learning -> update weights, record statistics
    """
    
    def __init__(self, api_client: BybitClient):
        self.api = api_client
        
        # Initialize engines
        self.momentum_engine = MomentumEngine(strategy_config)
        self.signal_engine = SignalEngine(strategy_config)
        self.position_manager = PositionManager(strategy_config, api_client)
        self.learning_module = LearningModule(strategy_config)
        self.liquidity_engine = LiquidityEngine(strategy_config)
        self.liquidation_engine = LiquidationEngine(strategy_config)
        
        # Trading parameters
        self.symbols = self._load_symbols()
        self.max_position_size = 100000.0  # $100k max position per trade (will be adjusted based on balance)
        self.leverage = trading_config.default_leverage  # 100x
        
        # Probe settings
        self.probability_of_probe = 0.50  # 50% chance to open probe each cycle (increased for testing)
        
        # Market data cache
        self.market_data: Dict[str, pd.DataFrame] = {}
        
        # Symbol statistics tracking
        self.symbol_stats: Dict[str, Dict] = {}
        
        logger.info("Trading Engine initialized")
    
    def _load_symbols(self) -> List[str]:
        """Load all trading symbols from Bybit API"""
        try:
            symbols = self.api.get_all_trading_symbols(min_volume_24h=500000)  # Min 500K volume
            logger.info(f"Loaded {len(symbols)} symbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")
            return symbols
        except Exception as e:
            logger.error(f"Failed to load symbols, using defaults: {e}")
            return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
    
    def _update_symbol_stats(self, symbol: str, trade_result: str, pnl: float = 0) -> None:
        """Update per-symbol statistics"""
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "win_rate": 0.0,
                "last_updated": datetime.utcnow()
            }
        
        stats = self.symbol_stats[symbol]
        stats["total_trades"] += 1
        stats["total_pnl"] += pnl
        
        if trade_result == "win":
            stats["winning_trades"] += 1
        elif trade_result == "loss":
            stats["losing_trades"] += 1
        
        if stats["total_trades"] > 0:
            stats["win_rate"] = stats["winning_trades"] / stats["total_trades"]
            stats["avg_pnl"] = stats["total_pnl"] / stats["total_trades"]
        
        stats["last_updated"] = datetime.utcnow()
    
    def run_cycle(self) -> None:
        """Run one complete trading cycle"""
        try:
            # 1. Get market data
            self._fetch_market_data()
            
            # Log active positions count periodically
            open_positions = len(self.position_manager.get_all_positions())
            if open_positions > 0:
                position_symbols = [p.symbol for p in self.position_manager.get_all_positions()]
                logger.info(f"Active positions: {open_positions}/{len(self.symbols)} - {position_symbols}")
            
            # 2. Process each symbol
            for symbol in self.symbols:
                if symbol not in self.market_data:
                    continue
                
                df = self.market_data[symbol]
                current_price = df['close'].iloc[-1]
                
                # 2.1 Check if position exists
                if self.position_manager.has_position(symbol):
                    # Manage existing position
                    self._manage_position(symbol, df, current_price)
                else:
                    # Look for new trade opportunities
                    self._look_for_trades(symbol, df, current_price)
            
            # 3. Learning update (periodic)
            self._periodic_learning()
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")
    
    def _fetch_market_data(self) -> None:
        """Fetch market data for all symbols"""
        try:
            for symbol in self.symbols:
                # Get klines (1m timeframe)
                klines = self.api.get_klines(symbol, interval="1", limit=200)
                
                # get_klines returns a list directly
                if klines and isinstance(klines, list) and len(klines) > 0:
                    # Check if data is in expected format
                    if isinstance(klines[0], list):
                        # Data is list of lists
                        df = pd.DataFrame(klines)
                        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
                    elif isinstance(klines[0], dict):
                        # Data is list of dicts
                        df = pd.DataFrame(klines)
                    else:
                        logger.warning(f"Unexpected data format for {symbol}")
                        continue
                    
                    # Convert timestamp safely
                    try:
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
                    except Exception as e:
                        logger.warning(f"Error parsing timestamp for {symbol}: {e}")
                        continue
                    
                    df.set_index('timestamp', inplace=True)
                    df = df.astype({'open': float, 'high': float, 'low': float, 'close': float, 'volume': float})
                    self.market_data[symbol] = df
                    logger.debug(f"Fetched market data for {symbol}: {len(df)} candles")
                else:
                    logger.warning(f"Failed to fetch market data for {symbol}")
            
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
    
    def _look_for_trades(self, symbol: str, df: pd.DataFrame, current_price: float) -> None:
        """Look for new trade opportunities with priority: LIQUIDATION > MOMENTUM > SIGNAL > PROBE"""
        try:
            logger.debug(f"Checking for trades for {symbol}")
            
            # 1. Liquidation cascade hunting (highest priority)
            liquidation_signal = self.liquidation_engine.detect_liquidation_opportunity(df, symbol)
            if liquidation_signal:
                logger.debug(f"Liquidation signal detected: strength={liquidation_signal.strength:.2f}, state={liquidation_signal.market_state}")
                if liquidation_signal.strength > 0.7:
                    logger.info(f"LIQUIDATION signal for {symbol}: {liquidation_signal.reason}")
                    self._open_liquidation_trade(symbol, liquidation_signal, current_price)
                    return  # Don't open other trades if liquidation detected
                else:
                    logger.debug(f"Liquidation signal too weak: {liquidation_signal.strength:.2f}")
            
            # 2. Momentum detection
            momentum_signal = self.momentum_engine.detect_momentum(df, symbol)
            if momentum_signal:
                logger.debug(f"Momentum signal detected: {momentum_signal.reason}")
                # Check liquidity context before momentum trade
                liquidity_analysis = self.liquidity_engine.analyze_liquidity(df, symbol)
                
                # Skip momentum if liquidity trap detected
                if liquidity_analysis and liquidity_analysis.has_trap:
                    logger.warning(f"Momentum skipped for {symbol}: liquidity trap detected")
                    return
                
                logger.info(f"MOMENTUM signal for {symbol}: {momentum_signal.reason}")
                self._open_momentum_trade(symbol, momentum_signal, current_price)
                return  # Don't open other trades if momentum detected
            
            # 3. Signal detection (SCOUT trade)
            signal = self.signal_engine.generate_signal(df, symbol)
            if signal:
                logger.debug(f"Signal detected: {signal.direction}, strength={signal.strength:.2f}")
                # Check liquidity context before signal trade
                liquidity_analysis = self.liquidity_engine.analyze_liquidity(df, symbol)
                
                # Skip signal if entry quality is poor
                if liquidity_analysis and liquidity_analysis.entry_quality == "avoid":
                    logger.warning(f"Signal skipped for {symbol}: poor entry quality")
                    return
                
                logger.info(f"SCOUT signal for {symbol}: {signal.reason}")
                self._open_scout_trade(symbol, signal, current_price)
                return  # Don't open probe if scout signal found
            
            # 4. Probe logic (random small trade)
            probe_roll = random.random()
            logger.debug(f"Probe roll: {probe_roll:.4f} (threshold: {self.probability_of_probe})")
            if probe_roll < self.probability_of_probe:
                logger.info(f"PROBE trade for {symbol}")
                self._open_probe_trade(symbol, current_price)
            
            logger.debug(f"No trade opened for {symbol} this cycle")
            
        except Exception as e:
            logger.error(f"Error looking for trades for {symbol}: {e}")
    
    def _open_liquidation_trade(self, symbol: str, liquidation_signal: LiquidationSignal, current_price: float) -> bool:
        """Open LIQUIDATION trade (cascade hunting)"""
        try:
            # Calculate max position size based on account balance
            account_balance = self._get_account_balance()
            max_position_size = account_balance * 0.4  # Use 40% of balance for liquidation trades
            
            return self.position_manager.open_position(
                symbol=symbol,
                direction=liquidation_signal.direction,
                entry_price=current_price,
                trade_type=TradeType.MOMENTUM,  # Use MOMENTUM trade type for liquidation trades
                max_position_size=max_position_size,
                leverage=self.leverage,
                atr=self._calculate_atr(self.market_data[symbol])
            )
        except Exception as e:
            logger.error(f"Error opening liquidation trade for {symbol}: {e}")
            return False

    def _open_momentum_trade(self, symbol: str, momentum_signal: MomentumSignal, current_price: float) -> bool:
        """Open MOMENTUM trade"""
        try:
            # Calculate max position size based on account balance
            account_balance = self._get_account_balance()
            max_position_size = account_balance * 0.3  # Use 30% of balance for momentum trades
            
            return self.position_manager.open_position(
                symbol=symbol,
                direction=momentum_signal.direction,
                entry_price=current_price,
                trade_type=TradeType.MOMENTUM,
                max_position_size=max_position_size,
                leverage=self.leverage,
                atr=self._calculate_atr(self.market_data[symbol])
            )
        except Exception as e:
            logger.error(f"Error opening momentum trade for {symbol}: {e}")
            return False
    
    def _open_scout_trade(self, symbol: str, signal: Signal, current_price: float) -> bool:
        """Open SCOUT trade"""
        try:
            # Calculate max position size based on account balance
            account_balance = self._get_account_balance()
            max_position_size = account_balance * 0.2  # Use 20% of balance for scout trades
            
            return self.position_manager.open_position(
                symbol=symbol,
                direction=signal.direction,
                entry_price=current_price,
                trade_type=TradeType.SCOUT,
                max_position_size=max_position_size,
                leverage=self.leverage,
                atr=self._calculate_atr(self.market_data[symbol])
            )
        except Exception as e:
            logger.error(f"Error opening scout trade for {symbol}: {e}")
            return False
    
    def _open_probe_trade(self, symbol: str, current_price: float) -> bool:
        """Open PROBE trade"""
        try:
            # Calculate max position size based on account balance
            account_balance = self._get_account_balance()
            max_position_size = account_balance * 0.05  # Use 5% of balance for probe trades
            
            # Random direction for probe
            direction = "long" if random.random() > 0.5 else "short"
            
            return self.position_manager.open_position(
                symbol=symbol,
                direction=direction,
                entry_price=current_price,
                trade_type=TradeType.PROBE,
                max_position_size=max_position_size,
                leverage=self.leverage,
                atr=self._calculate_atr(self.market_data[symbol])
            )
        except Exception as e:
            logger.error(f"Error opening probe trade for {symbol}: {e}")
            return False
    
    def _manage_position(self, symbol: str, df: pd.DataFrame, current_price: float) -> None:
        """Manage existing position"""
        try:
            position = self.position_manager.get_position(symbol)
            if not position:
                return
            
            # Apply SL/TP if not yet set (happens in cycle after position opens)
            if not position.sl_tp_set:
                # Get actual position info from exchange
                actual_position = self.api.check_position_state(symbol)
                if actual_position and actual_position.get("entry_price", 0) > 0:
                    actual_entry = actual_position["entry_price"]
                    self.position_manager.apply_sl_tp_to_exchange(symbol, actual_entry)
                else:
                    # Use estimated price if exchange data not available
                    self.position_manager.apply_sl_tp_to_exchange(symbol, position.entry_price)
            
            # Update PnL
            self.position_manager.update_pnl(symbol, current_price)
            
            # Check stop loss
            if position.stop_loss:
                if position.direction == "long" and current_price <= position.stop_loss:
                    logger.warning(f"Stop loss hit for {symbol}")
                    self._close_position(symbol, "stop_loss", current_price)
                    return
                elif position.direction == "short" and current_price >= position.stop_loss:
                    logger.warning(f"Stop loss hit for {symbol}")
                    self._close_position(symbol, "stop_loss", current_price)
                    return
            
            # Check take profit
            if position.take_profit:
                if position.direction == "long" and current_price >= position.take_profit:
                    logger.info(f"Take profit hit for {symbol}")
                    self._close_position(symbol, "take_profit", current_price)
                    return
                elif position.direction == "short" and current_price <= position.take_profit:
                    logger.info(f"Take profit hit for {symbol}")
                    self._close_position(symbol, "take_profit", current_price)
                    return
            
            # Update trailing stop
            self.position_manager.update_trailing_stop(symbol, current_price)
            
            # Smart stop management (breakeven, trailing, partial profits)
            atr = self._calculate_atr(df)
            self.position_manager.manage_smart_stops(symbol, current_price, atr)
            
            # Check for partial profit opportunity
            if position.stop_loss:
                risk_distance = abs(position.entry_price - position.stop_loss)
                if risk_distance > 0:
                    if position.direction == "long":
                        profit_distance = current_price - position.entry_price
                    else:
                        profit_distance = position.entry_price - current_price
                    profit_multiple = profit_distance / risk_distance
                    self.position_manager.take_partial_profit(symbol, current_price, profit_multiple)
            
            # Pyramiding (add to profitable position)
            if position.pnl > 0:
                account_balance = self._get_account_balance()
                max_position_size = account_balance * 0.5  # Max 50% of balance
                self.position_manager.pyramid_position(symbol, current_price, max_position_size)
            
            # Probe trade management (close quickly if losing)
            if position.trade_type == TradeType.PROBE and position.pnl < 0:
                if abs(position.pnl) > position.notional * 0.01:  # Close if 1% loss
                    logger.warning(f"Probe trade losing, closing {symbol}")
                    self._close_position(symbol, "probe_loss", current_price)
            
        except Exception as e:
            logger.error(f"Error managing position for {symbol}: {e}")
    
    def _close_position(self, symbol: str, reason: str, current_price: float) -> None:
        """Close position and record for learning"""
        try:
            position = self.position_manager.get_position(symbol)
            if not position:
                return
            
            # Calculate PnL
            if position.direction == "long":
                pnl = (current_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - current_price) * position.quantity
            
            # Record trade for learning
            self.learning_module.record_trade(
                symbol=symbol,
                trade_type=position.trade_type.value,
                direction=position.direction,
                signals_used=["momentum", "signal"],  # Simplified for now
                entry_price=position.entry_price,
                exit_price=current_price,
                entry_time=position.entry_time,
                exit_time=datetime.utcnow()
            )
            
            # Update per-symbol statistics
            trade_result = "win" if pnl > 0 else "loss"
            self._update_symbol_stats(symbol, trade_result, pnl)
            
            # Log symbol-specific PnL
            logger.info(f"Closed {symbol}: {reason}, PnL: ${pnl:.2f}")
            
            # Close position
            self.position_manager.close_position(symbol, reason)
            
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
    
    def _get_account_balance(self) -> float:
        """Get current account balance"""
        try:
            balance = self.api.get_wallet_balance()
            return balance.get("USDT", {}).get("wallet_balance", 100000.0)
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return 100000.0  # Fallback
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate ATR"""
        try:
            if len(df) < period + 1:
                return None
            
            high = df['high'].iloc[-period:]
            low = df['low'].iloc[-period:]
            close = df['close'].iloc[-period-1:-1]
            
            true_range = pd.concat([
                high - low,
                (high - close).abs(),
                (low - close).abs()
            ], axis=1).max(axis=1)
            
            atr = true_range.rolling(window=period).mean().iloc[-1]
            return atr
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None
    
    def _periodic_learning(self) -> None:
        """Periodic learning updates"""
        try:
            # Get trade statistics
            stats = self.learning_module.get_trade_statistics()
            if stats.get("total_trades", 0) > 0:
                logger.info(f"Trade stats: {stats['total_trades']} trades, "
                          f"win rate: {stats['win_rate']*100:.1f}%, "
                          f"avg PnL: {stats['avg_pnl_pct']*100:.2f}%")
            
            # Get best performing symbols from learning module
            best_symbols = self.learning_module.get_best_performing_symbols(top_n=3)
            if best_symbols:
                logger.info(f"Best performing symbols: {best_symbols}")
            
            # Log per-symbol statistics
            if self.symbol_stats:
                logger.info("--- Per-Symbol Statistics ---")
                sorted_symbols = sorted(self.symbol_stats.items(), 
                                      key=lambda x: x[1].get("win_rate", 0), 
                                      reverse=True)
                for symbol, sym_stats in sorted_symbols[:10]:  # Top 10 by win rate
                    logger.info(f"{symbol}: {sym_stats['total_trades']} trades, "
                              f"win rate: {sym_stats['win_rate']*100:.1f}%, "
                              f"avg PnL: ${sym_stats['avg_pnl']:.2f}, "
                              f"total PnL: ${sym_stats['total_pnl']:.2f}")
            
        except Exception as e:
            logger.error(f"Error in periodic learning: {e}")
    
    def run(self) -> None:
        """Run the main trading loop"""
        logger.info("Starting trading engine...")
        
        while True:
            try:
                self.run_cycle()
                
                # Update uptime for dashboard
                if hasattr(self, 'start_time'):
                    self.uptime_seconds = int(time.time() - self.start_time)
                
                time.sleep(2)  # Run every 2 seconds (faster for testing)
            except KeyboardInterrupt:
                logger.info("Trading engine stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                time.sleep(5)  # Wait before retrying
