"""
Professional Trade Logger - Complete trade tracking with MAE/MFE and full PnL breakdown
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
class TradeRecord:
    """Complete trade record with all required metrics"""
    trade_id: str
    signal_id: Optional[str]  # Can be null if no signal associated
    
    strategy_version: str
    model_version: str
    feature_version: str
    
    symbol: str
    timeframe: str
    side: str
    
    signal_timestamp: float
    entry_timestamp: float
    exit_timestamp: float
    
    entry_price: float
    exit_price: float
    quantity: float
    
    stop_loss: float
    take_profit: float
    
    exit_reason: str
    holding_time: float
    
    gross_pnl: float
    commission: float
    funding: float
    slippage: float
    spread_cost: float
    net_pnl: float
    
    return_pct: float
    risk_amount: float
    r_multiple: float
    
    mae: float
    mae_pct: float
    mae_r: float
    
    mfe: float
    mfe_pct: float
    mfe_r: float
    
    equity_at_entry: float
    equity_at_exit: float


class TradeLogger:
    """Professional trade logging with complete metrics"""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.trades_file = self.logs_dir / "trades_v2.jsonl"
        self._lock = threading.Lock()
        
        # Ensure file exists with header
        if not self.trades_file.exists():
            self._write_header()
    
    def _write_header(self):
        """Write schema header to file"""
        header = {
            "schema": "trade_v2",
            "version": "2.0",
            "description": "Professional trade logging with MAE/MFE and full PnL breakdown",
            "created_at": time.time()
        }
        with open(self.trades_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header) + "\n")
    
    def log_trade(self, trade_data: Dict[str, Any]) -> str:
        """
        Log a complete trade record
        
        Args:
            trade_data: Complete trade data including all metrics
            
        Returns:
            trade_id: Unique identifier for this trade
        """
        try:
            # Generate trade ID if not provided
            trade_id = trade_data.get('trade_id') or SystemIDGenerator.generate_trade_id(
                trade_data.get('symbol', 'UNKNOWN'),
                trade_data.get('entry_timestamp', time.time())
            )
            
            # Calculate derived metrics if not provided
            if 'return_pct' not in trade_data or trade_data['return_pct'] == 0:
                trade_data['return_pct'] = self._calculate_return_pct(trade_data)
            
            if 'r_multiple' not in trade_data or trade_data['r_multiple'] == 0:
                trade_data['r_multiple'] = self._calculate_r_multiple(trade_data)
            
            # Create record
            record = TradeRecord(
                trade_id=trade_id,
                signal_id=trade_data.get('signal_id'),
                
                strategy_version=trade_data.get('strategy_version', 'unknown'),
                model_version=trade_data.get('model_version', 'unknown'),
                feature_version=trade_data.get('feature_version', 'v1'),
                
                symbol=trade_data.get('symbol', ''),
                timeframe=trade_data.get('timeframe', '1m'),
                side=trade_data.get('side', ''),
                
                signal_timestamp=trade_data.get('signal_timestamp', 0.0),
                entry_timestamp=trade_data.get('entry_timestamp', 0.0),
                exit_timestamp=trade_data.get('exit_timestamp', 0.0),
                
                entry_price=trade_data.get('entry_price', 0.0),
                exit_price=trade_data.get('exit_price', 0.0),
                quantity=trade_data.get('quantity', 0.0),
                
                stop_loss=trade_data.get('stop_loss', 0.0),
                take_profit=trade_data.get('take_profit', 0.0),
                
                exit_reason=trade_data.get('exit_reason', ''),
                holding_time=trade_data.get('holding_time', 0.0),
                
                gross_pnl=trade_data.get('gross_pnl', 0.0),
                commission=trade_data.get('commission', 0.0),
                funding=trade_data.get('funding', 0.0),
                slippage=trade_data.get('slippage', 0.0),
                spread_cost=trade_data.get('spread_cost', 0.0),
                net_pnl=trade_data.get('net_pnl', 0.0),
                
                return_pct=trade_data.get('return_pct', 0.0),
                risk_amount=trade_data.get('risk_amount', 0.0),
                r_multiple=trade_data.get('r_multiple', 0.0),
                
                mae=trade_data.get('mae', 0.0),
                mae_pct=trade_data.get('mae_pct', 0.0),
                mae_r=trade_data.get('mae_r', 0.0),
                
                mfe=trade_data.get('mfe', 0.0),
                mfe_pct=trade_data.get('mfe_pct', 0.0),
                mfe_r=trade_data.get('mfe_r', 0.0),
                
                equity_at_entry=trade_data.get('equity_at_entry', 0.0),
                equity_at_exit=trade_data.get('equity_at_exit', 0.0)
            )
            
            with self._lock:
                with open(self.trades_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(asdict(record), default=str) + "\n")
            
            logger.info(f"[TRADE_LOG] Logged trade {trade_id} for {record.symbol} - PnL: ${record.net_pnl:.2f}")
            return trade_id
            
        except Exception as e:
            logger.error(f"[TRADE_LOG] Failed to log trade: {e}")
            return ""
    
    def _calculate_return_pct(self, trade_data: Dict[str, Any]) -> float:
        """Calculate return percentage"""
        try:
            entry_price = trade_data.get('entry_price', 0.0)
            exit_price = trade_data.get('exit_price', 0.0)
            side = trade_data.get('side', '')
            
            if entry_price == 0:
                return 0.0
            
            if side == 'long':
                return ((exit_price - entry_price) / entry_price) * 100
            elif side == 'short':
                return ((entry_price - exit_price) / entry_price) * 100
            else:
                return 0.0
        except Exception:
            return 0.0
    
    def _calculate_r_multiple(self, trade_data: Dict[str, Any]) -> float:
        """Calculate R-multiple (net_pnl / risk_amount)"""
        try:
            net_pnl = trade_data.get('net_pnl', 0.0)
            risk_amount = trade_data.get('risk_amount', 0.0)
            
            if risk_amount == 0:
                return 0.0
            
            return net_pnl / risk_amount
        except Exception:
            return 0.0