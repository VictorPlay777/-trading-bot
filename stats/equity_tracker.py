"""
Professional Equity Tracker - Complete portfolio state tracking with equity curve
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
class EquitySnapshot:
    """Complete portfolio state snapshot"""
    timestamp: float
    balance: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: int
    gross_exposure: float
    net_exposure: float
    drawdown: float
    drawdown_pct: float
    peak_equity: float


class EquityTracker:
    """Professional equity curve tracking"""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.equity_file = self.logs_dir / "equity_snapshots_v2.jsonl"
        self._lock = threading.Lock()
        
        # Track peak equity for drawdown calculation
        self._peak_equity = 0.0
        
        # Ensure file exists with header
        if not self.equity_file.exists():
            self._write_header()
    
    def _write_header(self):
        """Write schema header to file"""
        header = {
            "schema": "equity_v2",
            "version": "2.0",
            "description": "Professional equity curve tracking with complete portfolio state",
            "created_at": time.time()
        }
        with open(self.equity_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header) + "\n")
    
    def log_snapshot(self, portfolio_data: Dict[str, Any]) -> str:
        """
        Log equity snapshot
        
        Args:
            portfolio_data: Complete portfolio state data
            
        Returns:
            snapshot_id: Unique identifier for this snapshot
        """
        try:
            snapshot_id = SystemIDGenerator.generate_equity_snapshot_id()
            now = time.time()
            
            equity = portfolio_data.get('equity', 0.0)
            balance = portfolio_data.get('balance', equity)
            
            # Update peak equity
            if equity > self._peak_equity:
                self._peak_equity = equity
            
            # Calculate drawdown
            drawdown = self._peak_equity - equity
            drawdown_pct = (drawdown / self._peak_equity * 100) if self._peak_equity > 0 else 0.0
            
            # Create snapshot
            snapshot = EquitySnapshot(
                timestamp=now,
                balance=balance,
                equity=equity,
                realized_pnl=portfolio_data.get('realized_pnl', 0.0),
                unrealized_pnl=portfolio_data.get('unrealized_pnl', 0.0),
                open_positions=portfolio_data.get('open_positions', 0),
                gross_exposure=portfolio_data.get('gross_exposure', 0.0),
                net_exposure=portfolio_data.get('net_exposure', 0.0),
                drawdown=drawdown,
                drawdown_pct=drawdown_pct,
                peak_equity=self._peak_equity
            )
            
            with self._lock:
                with open(self.equity_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(asdict(snapshot), default=str) + "\n")
            
            logger.debug(f"[EQUITY_TRACK] Logged snapshot {snapshot_id} - Equity: ${equity:.2f}, DD: {drawdown_pct:.2f}%")
            return snapshot_id
            
        except Exception as e:
            logger.error(f"[EQUITY_TRACK] Failed to log snapshot: {e}")
            return ""
    
    def get_current_drawdown(self) -> float:
        """Get current drawdown percentage"""
        return 0.0  # Will be calculated from latest snapshot
    
    def get_peak_equity(self) -> float:
        """Get peak equity"""
        return self._peak_equity