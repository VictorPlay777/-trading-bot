"""
System ID Generator for unique identifiers
"""
import uuid
import time
from typing import Optional


class SystemIDGenerator:
    """Generate unique IDs for signals, trades, and other events"""
    
    @staticmethod
    def generate_signal_id() -> str:
        """Generate unique signal ID"""
        return f"sig_{uuid.uuid4().hex[:16]}_{int(time.time())}"
    
    @staticmethod
    def generate_trade_id(symbol: str, timestamp: float) -> str:
        """Generate unique trade ID based on symbol and timestamp"""
        return f"{symbol}_{int(timestamp)}_{uuid.uuid4().hex[:8]}"
    
    @staticmethod
    def generate_equity_snapshot_id() -> str:
        """Generate unique equity snapshot ID"""
        return f"eq_{uuid.uuid4().hex[:12]}_{int(time.time())}"