"""
Professional Data Quality Checker - Validate data integrity and consistency
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger


class DataQualityChecker:
    """Validate data integrity and consistency across all data sources"""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self._errors = []
        self._warnings = []
    
    def validate_signal_record(self, signal_data: Dict[str, Any]) -> bool:
        """Validate a signal record"""
        errors = []
        
        # Required fields
        required_fields = [
            'signal_id', 'timestamp', 'symbol', 'direction', 
            'decision', 'decision_timestamp'
        ]
        
        for field in required_fields:
            if field not in signal_data or signal_data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Field type validation
        if 'timestamp' in signal_data:
            try:
                ts = float(signal_data['timestamp'])
                if ts <= 0 or ts > time.time() + 3600:  # Allow 1 hour future for clock sync
                    errors.append(f"Invalid timestamp: {ts}")
            except (TypeError, ValueError):
                errors.append(f"Invalid timestamp type: {signal_data['timestamp']}")
        
        if 'symbol' in signal_data:
            if not isinstance(signal_data['symbol'], str) or len(signal_data['symbol']) < 3:
                errors.append(f"Invalid symbol: {signal_data['symbol']}")
        
        if 'direction' in signal_data:
            if signal_data['direction'] not in ['long', 'short']:
                errors.append(f"Invalid direction: {signal_data['direction']}")
        
        if 'decision' in signal_data:
            if signal_data['decision'] not in ['ACCEPTED', 'REJECTED']:
                errors.append(f"Invalid decision: {signal_data['decision']}")
        
        # Logical validation
        if 'decision_timestamp' in signal_data and 'timestamp' in signal_data:
            if signal_data['decision_timestamp'] < signal_data['timestamp']:
                errors.append("Decision timestamp before signal timestamp")
        
        if errors:
            self._errors.extend(errors)
            logger.warning(f"[DATA_QUALITY] Signal validation failed: {errors}")
            return False
        
        return True
    
    def validate_trade_record(self, trade_data: Dict[str, Any]) -> bool:
        """Validate a trade record"""
        errors = []
        
        # Required fields
        required_fields = [
            'trade_id', 'symbol', 'side', 'entry_timestamp', 
            'exit_timestamp', 'entry_price', 'exit_price'
        ]
        
        for field in required_fields:
            if field not in trade_data or trade_data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Field type validation
        if 'entry_price' in trade_data:
            try:
                price = float(trade_data['entry_price'])
                if price <= 0:
                    errors.append(f"Invalid entry_price: {price}")
            except (TypeError, ValueError):
                errors.append(f"Invalid entry_price type: {trade_data['entry_price']}")
        
        if 'exit_price' in trade_data:
            try:
                price = float(trade_data['exit_price'])
                if price <= 0:
                    errors.append(f"Invalid exit_price: {price}")
            except (TypeError, ValueError):
                errors.append(f"Invalid exit_price type: {trade_data['exit_price']}")
        
        if 'quantity' in trade_data:
            try:
                qty = float(trade_data['quantity'])
                if qty <= 0:
                    errors.append(f"Invalid quantity: {qty}")
            except (TypeError, ValueError):
                errors.append(f"Invalid quantity type: {trade_data['quantity']}")
        
        # Logical validation
        if 'entry_timestamp' in trade_data and 'exit_timestamp' in trade_data:
            if trade_data['exit_timestamp'] < trade_data['entry_timestamp']:
                errors.append("Exit timestamp before entry timestamp")
        
        if 'holding_time' in trade_data:
            if trade_data['holding_time'] < 0:
                errors.append(f"Invalid holding_time: {trade_data['holding_time']}")
        
        # PnL consistency check
        if 'gross_pnl' in trade_data and 'net_pnl' in trade_data:
            gross = float(trade_data['gross_pnl'])
            net = float(trade_data['net_pnl'])
            costs = float(trade_data.get('commission', 0)) + float(trade_data.get('funding', 0)) + \
                   float(trade_data.get('slippage', 0)) + float(trade_data.get('spread_cost', 0))
            
            expected_net = gross - costs
            if abs(net - expected_net) > 0.01:  # Allow 1 cent rounding
                errors.append(f"PnL inconsistency: gross={gross}, costs={costs}, net={net}, expected={expected_net}")
        
        if errors:
            self._errors.extend(errors)
            logger.warning(f"[DATA_QUALITY] Trade validation failed: {errors}")
            return False
        
        return True
    
    def validate_equity_snapshot(self, equity_data: Dict[str, Any]) -> bool:
        """Validate an equity snapshot"""
        errors = []
        
        # Required fields
        required_fields = ['timestamp', 'balance', 'equity']
        
        for field in required_fields:
            if field not in equity_data or equity_data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Field type validation
        if 'balance' in equity_data:
            try:
                balance = float(equity_data['balance'])
                if balance < 0:
                    errors.append(f"Invalid balance (negative): {balance}")
            except (TypeError, ValueError):
                errors.append(f"Invalid balance type: {equity_data['balance']}")
        
        if 'equity' in equity_data:
            try:
                equity = float(equity_data['equity'])
                if equity < 0:
                    errors.append(f"Invalid equity (negative): {equity}")
            except (TypeError, ValueError):
                errors.append(f"Invalid equity type: {equity_data['equity']}")
        
        # Logical validation
        if 'drawdown' in equity_data:
            if equity_data['drawdown'] < 0:
                errors.append(f"Invalid drawdown (negative): {equity_data['drawdown']}")
        
        if 'drawdown_pct' in equity_data:
            dd_pct = float(equity_data['drawdown_pct'])
            if dd_pct < 0 or dd_pct > 100:
                errors.append(f"Invalid drawdown_pct: {dd_pct}")
        
        if errors:
            self._errors.extend(errors)
            logger.warning(f"[DATA_QUALITY] Equity snapshot validation failed: {errors}")
            return False
        
        return True
    
    def check_duplicates(self, file_path: Path, id_field: str = 'id') -> List[str]:
        """Check for duplicate IDs in a file"""
        try:
            if not file_path.exists():
                return []
            
            seen_ids = set()
            duplicates = []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('{'):  # Skip header lines
                        continue
                    
                    try:
                        data = json.loads(line)
                        record_id = data.get(id_field)
                        if record_id and record_id in seen_ids:
                            duplicates.append(record_id)
                        seen_ids.add(record_id)
                    except json.JSONDecodeError:
                        continue
            
            if duplicates:
                logger.warning(f"[DATA_QUALITY] Found {len(duplicates)} duplicate {id_field}s in {file_path.name}")
            
            return duplicates
            
        except Exception as e:
            logger.error(f"[DATA_QUALITY] Error checking duplicates: {e}")
            return []
    
    def get_errors(self) -> List[str]:
        """Get all validation errors"""
        return self._errors.copy()
    
    def get_warnings(self) -> List[str]:
        """Get all validation warnings"""
        return self._warnings.copy()
    
    def clear_errors(self):
        """Clear all errors and warnings"""
        self._errors.clear()
        self._warnings.clear()