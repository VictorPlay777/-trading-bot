import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Signal generation engine with 3 strategies:
    - Momentum: orderflow + price velocity
    - Mean Reversion: deviation from short MA
    - Breakout Detection: volatility expansion
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.strategies = config.get("strategies", {})
        
        # Enable/disable strategies
        self.enable_momentum = self.strategies.get("enable_momentum", True)
        self.enable_mean_reversion = self.strategies.get("enable_mean_reversion", True)
        self.enable_breakout = self.strategies.get("enable_breakout", True)
        
        # TEST MODE: Generate random signals for testing
        self.test_mode = config.get("test_mode", False)
        
        # Price history for analysis
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Signal cache
        self.current_signals: Dict[str, dict] = {}
        
        # ATR for volatility-based TP/SL
        self.atr_values: Dict[str, float] = {}
        
    def update_price(self, symbol: str, price: float, volume: float = 0):
        """Update price history for signal calculation."""
        self.price_history[symbol].append({
            "price": price,
            "volume": volume,
            "timestamp": datetime.now().timestamp()
        })
        
        # Calculate ATR
        if len(self.price_history[symbol]) >= 14:
            self.atr_values[symbol] = self._calculate_atr(symbol)
            
    def generate_signals(self, symbol: str) -> dict:
        """Generate all signals for a symbol."""
        
    def generate_fallback_signal(self, symbol: str, current_price: float, volume: float) -> dict:
        """
        Generate fallback signal for startup without historical data.
        Uses: volume spikes, short-term momentum, simple price action.
        """
        history = list(self.price_history[symbol])
        
        if len(history) < 3:
            return None  # Need at least 3 data points
            
        # Calculate short-term momentum (last 3 points)
        recent_prices = [h["price"] for h in history[-3:]]
        momentum = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] * 100
        
        # Calculate volume spike (current vs average of last 10)
        recent_volumes = [h.get("volume", 0) for h in history[-10:]]
        avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else volume
        volume_spike = volume / avg_volume if avg_volume > 0 else 1.0
        
        # Simple logic: strong momentum + volume spike = signal
        if abs(momentum) > 0.1 and volume_spike > 1.5:
            direction = "long" if momentum > 0 else "short"
            confidence = min(abs(momentum) * 5, 0.8)  # Cap at 0.8
            
            return {
                "combined": {
                    "direction": direction,
                    "confidence": confidence,
                    "strategy": "fallback"
                }
            }
        
        return None
    
    def generate_signals(self, symbol: str) -> dict:
        """Generate all signals for a symbol."""
        # TEST MODE: Generate simple random signals for testing
        if self.test_mode:
            return self._generate_test_signal(symbol)
        
        signals = {
            "symbol": symbol,
            "timestamp": datetime.now().timestamp(),
            "momentum": None,
            "mean_reversion": None,
            "breakout": None,
            "combined": None
        }
        
        if self.enable_momentum:
            signals["momentum"] = self._momentum_signal(symbol)
            
        if self.enable_mean_reversion:
            signals["mean_reversion"] = self._mean_reversion_signal(symbol)
            
        if self.enable_breakout:
            signals["breakout"] = self._breakout_signal(symbol)
            
        # Combine signals
        signals["combined"] = self._combine_signals(signals)
        
        self.current_signals[symbol] = signals
        return signals
    
    def _generate_test_signal(self, symbol: str) -> dict:
        """Generate simple test signal - alternating long/short every 30 seconds"""
        import random
        import time
        
        # Use timestamp to alternate direction every 30 seconds
        current_time = int(time.time())
        cycle = (current_time // 30) % 2  # 0 or 1
        
        direction = "long" if cycle == 0 else "short"
        
        signals = {
            "symbol": symbol,
            "timestamp": datetime.now().timestamp(),
            "momentum": {
                "direction": direction,
                "strength": 0.8,
                "confidence": 0.9,
                "reason": "TEST MODE: Simple alternating signal"
            },
            "mean_reversion": None,
            "breakout": None,
            "combined": {
                "direction": direction,
                "strength": 0.8,
                "confidence": 0.9,
                "reason": "TEST MODE: Simple alternating signal"
            }
        }
        
        self.current_signals[symbol] = signals
        return signals
        
    def _momentum_signal(self, symbol: str) -> Optional[dict]:
        """
        Momentum strategy based on price velocity and orderflow.
        Returns signal if momentum is strong in one direction.
        """
        try:
            prices = list(self.price_history[symbol])
            if len(prices) < 20:
                return None
                
            # Calculate price velocity (rate of change)
            recent_prices = [p["price"] for p in prices[-10:]]
            older_prices = [p["price"] for p in prices[-20:-10]]
            
            recent_avg = np.mean(recent_prices)
            older_avg = np.mean(older_prices)
            
            # Price velocity
            velocity = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            # Volume confirmation
            recent_volume = np.mean([p["volume"] for p in prices[-10:]])
            older_volume = np.mean([p["volume"] for p in prices[-20:-10]])
            volume_ratio = recent_volume / older_volume if older_volume > 0 else 1
            
            # Signal generation
            if velocity > 0.001 and volume_ratio > 1.2:
                return {
                    "direction": "long",
                    "strength": min(abs(velocity) * 100, 1.0),
                    "confidence": min(volume_ratio / 2, 1.0),
                    "reason": f"Positive momentum: {velocity:.4f}, volume ratio: {volume_ratio:.2f}"
                }
            elif velocity < -0.001 and volume_ratio > 1.2:
                return {
                    "direction": "short",
                    "strength": min(abs(velocity) * 100, 1.0),
                    "confidence": min(volume_ratio / 2, 1.0),
                    "reason": f"Negative momentum: {velocity:.4f}, volume ratio: {volume_ratio:.2f}"
                }
                
        except Exception as e:
            logger.error(f"Error in momentum signal for {symbol}: {e}")
            
        return None
        
    def _mean_reversion_signal(self, symbol: str) -> Optional[dict]:
        """
        Mean reversion strategy based on deviation from short MA.
        Returns signal when price deviates significantly from mean.
        """
        try:
            prices = list(self.price_history[symbol])
            if len(prices) < 30:
                return None
                
            price_values = [p["price"] for p in prices]
            current_price = price_values[-1]
            
            # Short moving average (10 periods)
            ma_short = np.mean(price_values[-10:])
            
            # Long moving average (30 periods)
            ma_long = np.mean(price_values[-30:])
            
            # Standard deviation for threshold
            std_dev = np.std(price_values[-30:])
            
            # Deviation from MA
            deviation = (current_price - ma_short) / ma_short if ma_short > 0 else 0
            
            # Z-score
            z_score = deviation / (std_dev / ma_short) if std_dev > 0 and ma_short > 0 else 0
            
            # Signal generation
            if z_score > 2.0:  # Significantly overbought
                return {
                    "direction": "short",
                    "strength": min(abs(z_score) / 3, 1.0),
                    "confidence": 0.7,
                    "reason": f"Overbought: z-score {z_score:.2f}"
                }
            elif z_score < -2.0:  # Significantly oversold
                return {
                    "direction": "long",
                    "strength": min(abs(z_score) / 3, 1.0),
                    "confidence": 0.7,
                    "reason": f"Oversold: z-score {z_score:.2f}"
                }
                
        except Exception as e:
            logger.error(f"Error in mean reversion signal for {symbol}: {e}")
            
        return None
        
    def _breakout_signal(self, symbol: str) -> Optional[dict]:
        """
        Breakout detection based on volatility expansion.
        Returns signal when price breaks out of recent range with volume.
        """
        try:
            prices = list(self.price_history[symbol])
            if len(prices) < 50:
                return None
                
            price_values = [p["price"] for p in prices]
            current_price = price_values[-1]
            
            # Calculate recent range
            recent_prices = price_values[-20:]
            high = max(recent_prices)
            low = min(recent_prices)
            range_size = high - low
            
            # Calculate volatility
            volatility = np.std(price_values[-20:]) / np.mean(price_values[-20:]) if np.mean(price_values[-20:]) > 0 else 0
            
            # Volume check
            recent_volume = [p["volume"] for p in prices[-10:]]
            avg_volume = np.mean(recent_volume)
            
            # Breakout conditions
            if range_size > 0:
                # Breakout above resistance
                if current_price > high and volatility > 0.01 and avg_volume > 0:
                    breakout_strength = (current_price - high) / range_size
                    return {
                        "direction": "long",
                        "strength": min(breakout_strength, 1.0),
                        "confidence": min(volatility * 50, 1.0),
                        "reason": f"Breakout above resistance: {breakout_strength:.4f}"
                    }
                    
                # Breakout below support
                if current_price < low and volatility > 0.01 and avg_volume > 0:
                    breakout_strength = (low - current_price) / range_size
                    return {
                        "direction": "short",
                        "strength": min(breakout_strength, 1.0),
                        "confidence": min(volatility * 50, 1.0),
                        "reason": f"Breakout below support: {breakout_strength:.4f}"
                    }
                    
        except Exception as e:
            logger.error(f"Error in breakout signal for {symbol}: {e}")
            
        return None
        
    def _combine_signals(self, signals: dict) -> Optional[dict]:
        """
        Combine all signals into a single trading decision.
        Uses weighted voting based on signal strength and confidence.
        """
        momentum = signals.get("momentum")
        mean_reversion = signals.get("mean_reversion")
        breakout = signals.get("breakout")
        
        votes = {"long": 0, "short": 0}
        total_weight = 0
        
        # Weight each signal by strength * confidence
        for signal in [momentum, mean_reversion, breakout]:
            if signal and signal["direction"] in votes:
                weight = signal["strength"] * signal["confidence"]
                votes[signal["direction"]] += weight
                total_weight += weight
                
        if total_weight == 0:
            return None
            
        # Determine winner
        if votes["long"] > votes["short"]:
            return {
                "direction": "long",
                "strength": votes["long"] / total_weight,
                "confidence": votes["long"] / (votes["long"] + votes["short"]),
                "votes": votes
            }
        elif votes["short"] > votes["long"]:
            return {
                "direction": "short",
                "strength": votes["short"] / total_weight,
                "confidence": votes["short"] / (votes["long"] + votes["short"]),
                "votes": votes
            }
        else:
            return None
            
    def _calculate_atr(self, symbol: str, period: int = 14) -> float:
        """Calculate Average True Range for volatility-based TP/SL."""
        try:
            prices = list(self.price_history[symbol])
            if len(prices) < period + 1:
                return 0.0
                
            true_ranges = []
            for i in range(len(prices) - 1, len(prices) - period - 1, -1):
                high = prices[i]["price"]
                low = prices[i]["price"]
                prev_close = prices[i-1]["price"]
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
                
            return np.mean(true_ranges) if true_ranges else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating ATR for {symbol}: {e}")
            return 0.0
            
    def get_atr(self, symbol: str) -> float:
        """Get ATR value for symbol."""
        return self.atr_values.get(symbol, 0.0)
        
    def get_current_signal(self, symbol: str) -> Optional[dict]:
        """Get current combined signal for symbol."""
        return self.current_signals.get(symbol)


from collections import defaultdict
