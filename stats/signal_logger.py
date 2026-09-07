"""
Professional Signal Logger - Complete signal tracking with full feature snapshot
"""
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from loguru import logger

from .system_id import SystemIDGenerator


@dataclass
class SignalRecord:
    """Complete signal record with full feature snapshot"""
    signal_id: str
    timestamp: float
    symbol: str
    timeframe: str
    direction: str
    signal_score: float
    strategy_version: str
    model_version: str
    feature_version: str
    
    decision: str  # "ACCEPTED" or "REJECTED"
    decision_reason: str
    decision_timestamp: float
    
    market_regime: str
    volatility_regime: str
    trend_regime: str
    
    price_at_signal: float
    
    full_features: Dict[str, Any]
    
    trade_id: Optional[str] = None  # Populated if signal results in trade


class SignalLogger:
    """Professional signal logging with complete feature snapshot"""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.signals_file = self.logs_dir / "signals_v2.jsonl"
        self._lock = threading.Lock()
        
        # Ensure file exists with header
        if not self.signals_file.exists():
            self._write_header()
    
    def _write_header(self):
        """Write schema header to file"""
        header = {
            "schema": "signal_v2",
            "version": "2.0",
            "description": "Professional signal logging with full feature snapshot",
            "created_at": time.time()
        }
        with open(self.signals_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header) + "\n")
    
    def log_signal(self, signal_data: Dict[str, Any], decision: str, decision_reason: str) -> str:
        """
        Log a complete signal record
        
        Args:
            signal_data: Complete signal data including features
            decision: "ACCEPTED" or "REJECTED"
            decision_reason: Reason for decision
            
        Returns:
            signal_id: Unique identifier for this signal
        """
        try:
            signal_id = SystemIDGenerator.generate_signal_id()
            now = time.time()
            
            # Extract core signal information
            record = SignalRecord(
                signal_id=signal_id,
                timestamp=signal_data.get('timestamp', now),
                symbol=signal_data.get('symbol', ''),
                timeframe=signal_data.get('timeframe', '1m'),
                direction=signal_data.get('direction', ''),
                signal_score=signal_data.get('confidence', 0.0),
                strategy_version=signal_data.get('strategy_version', 'unknown'),
                model_version=signal_data.get('model_version', 'unknown'),
                feature_version=signal_data.get('feature_version', 'v1'),
                
                decision=decision,
                decision_reason=decision_reason,
                decision_timestamp=now,
                
                market_regime=signal_data.get('regime', 'unknown'),
                volatility_regime=self._classify_volatility(signal_data),
                trend_regime=self._classify_trend(signal_data),
                
                price_at_signal=signal_data.get('entry', 0.0),
                
                full_features=signal_data.get('full_features', {}),
                
                trade_id=None  # Will be populated if trade is opened
            )
            
            with self._lock:
                with open(self.signals_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(asdict(record), default=str) + "\n")
            
            logger.debug(f"[SIGNAL_LOG] Logged signal {signal_id} for {record.symbol} - {decision}")
            return signal_id
            
        except Exception as e:
            logger.error(f"[SIGNAL_LOG] Failed to log signal: {e}")
            return ""
    
    def link_trade(self, signal_id: str, trade_id: str):
        """Link a signal to a trade"""
        try:
            # In production, this would update the existing record
            # For now, we'll create a linkage record
            linkage_file = self.logs_dir / "signal_trade_links.jsonl"
            
            linkage = {
                "signal_id": signal_id,
                "trade_id": trade_id,
                "linked_at": time.time()
            }
            
            with self._lock:
                with open(linkage_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(linkage) + "\n")
            
            logger.debug(f"[SIGNAL_LOG] Linked signal {signal_id} to trade {trade_id}")
            
        except Exception as e:
            logger.error(f"[SIGNAL_LOG] Failed to link signal to trade: {e}")
    
    def _classify_volatility(self, signal_data: Dict[str, Any]) -> str:
        """Classify volatility regime from signal data"""
        atr = signal_data.get('atr', 0.0)
        price = signal_data.get('entry', 1.0)
        
        if price == 0:
            return "unknown"
        
        atr_pct = (atr / price) * 100
        
        if atr_pct < 0.1:
            return "very_low"
        elif atr_pct < 0.3:
            return "low"
        elif atr_pct < 0.6:
            return "normal"
        elif atr_pct < 1.0:
            return "high"
        else:
            return "very_high"
    
    def _classify_trend(self, signal_data: Dict[str, Any]) -> str:
        """Classify trend regime from signal data"""
        regime = signal_data.get('regime', 'unknown')
        
        if regime == 'trend':
            # Determine direction from EMA slopes if available
            features = signal_data.get('full_features', {})
            ema_slope_20 = features.get('ema_slope_20', 0.0)
            
            if ema_slope_20 > 0.0001:
                return "up"
            elif ema_slope_20 < -0.0001:
                return "down"
            else:
                return "flat"
        elif regime == 'breakout':
            return "breakout"
        elif regime == 'chop':
            return "sideways"
        else:
            return "unknown"