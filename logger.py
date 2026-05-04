"""
Structured logging for trading bot.
"""
import json
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from config import logging_config


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter for structured logs"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


class TradeLogger:
    """Specialized logger for trade events"""
    
    def __init__(self, csv_path: str = "logs/trades.csv"):
        self.csv_path = csv_path
        self._ensure_csv_exists()
    
    def _ensure_csv_exists(self):
        """Create CSV with headers if doesn't exist"""
        Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(self.csv_path):
            headers = [
                "timestamp", "trade_id", "symbol", "direction", "entry_price",
                "exit_price", "size", "leverage", "entry_reason", "exit_reason",
                "sl_price", "tp_price", "pnl_gross", "entry_fee", "exit_fee",
                "funding_fees", "pnl_net", "roi_pct", "regime_at_entry",
                "rsi_at_entry", "adx_at_entry", "atr_at_entry", "duration_min"
            ]
            with open(self.csv_path, 'w') as f:
                f.write(','.join(headers) + '\n')
    
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log a completed trade to CSV"""
        row = [
            trade_data.get("timestamp", datetime.utcnow().isoformat()),
            trade_data.get("trade_id", ""),
            trade_data.get("symbol", ""),
            trade_data.get("direction", ""),
            trade_data.get("entry_price", 0),
            trade_data.get("exit_price", 0),
            trade_data.get("size", 0),
            trade_data.get("leverage", 0),
            trade_data.get("entry_reason", ""),
            trade_data.get("exit_reason", ""),
            trade_data.get("sl_price", 0),
            trade_data.get("tp_price", 0),
            trade_data.get("pnl_gross", 0),
            trade_data.get("entry_fee", 0),
            trade_data.get("exit_fee", 0),
            trade_data.get("funding_fees", 0),
            trade_data.get("pnl_net", 0),
            trade_data.get("roi_pct", 0),
            trade_data.get("regime_at_entry", ""),
            trade_data.get("rsi_at_entry", 0),
            trade_data.get("adx_at_entry", 0),
            trade_data.get("atr_at_entry", 0),
            trade_data.get("duration_min", 0),
        ]
        
        with open(self.csv_path, 'a') as f:
            f.write(','.join(str(x) for x in row) + '\n')


# Global logger setup
def setup_logger(name: str = "trading_bot") -> logging.Logger:
    """Setup and return configured logger"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, logging_config.log_level))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler with simple format
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handlers with structured JSON format
    if logging_config.log_to_file:
        Path(logging_config.log_dir).mkdir(parents=True, exist_ok=True)
        for component_file in (
            "bot.log",
            "errors.log",
            "trades.log",
            "ml.log",
            "api.log",
            "websocket.log",
            "risk.log",
        ):
            file_handler = logging.handlers.RotatingFileHandler(
                os.path.join(logging_config.log_dir, component_file),
                maxBytes=logging_config.max_log_size_mb * 1024 * 1024,
                backupCount=logging_config.backup_count
            )
            file_handler.setFormatter(StructuredLogFormatter())
            # Keep component handlers mostly independent:
            # only bot.log should collect everything from this logger.
            if component_file != "bot.log":
                if component_file == "errors.log":
                    file_handler.setLevel(logging.ERROR)
                else:
                    # Component-specific files are fed by dedicated loggers.
                    file_handler.setLevel(logging.CRITICAL + 1)
            logger.addHandler(file_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the global logger instance"""
    return logging.getLogger("trading_bot")


def log_event(level: str, message: str, **kwargs):
    """Helper to log with extra fields"""
    logger = get_logger()
    extra = {"extra": kwargs}
    getattr(logger, level.lower())(message, extra=extra)


def get_component_logger(component: str) -> logging.Logger:
    """
    Returns a dedicated structured logger with its own rotating file.
    Supported components include: trades/errors/ml/api/websocket/risk.
    """
    logger_name = f"trading_bot.{component}"
    component_logger = logging.getLogger(logger_name)
    component_logger.setLevel(getattr(logging, logging_config.log_level))
    component_logger.propagate = False
    if component_logger.handlers:
        return component_logger

    Path(logging_config.log_dir).mkdir(parents=True, exist_ok=True)
    component_log_path = os.path.join(logging_config.log_dir, f"{component}.log")
    fh = logging.handlers.RotatingFileHandler(
        component_log_path,
        maxBytes=logging_config.max_log_size_mb * 1024 * 1024,
        backupCount=logging_config.backup_count,
    )
    fh.setFormatter(StructuredLogFormatter())
    component_logger.addHandler(fh)

    # Mirror ERROR+ into shared errors log for centralized triage.
    if component != "errors":
        err_fh = logging.handlers.RotatingFileHandler(
            os.path.join(logging_config.log_dir, "errors.log"),
            maxBytes=logging_config.max_log_size_mb * 1024 * 1024,
            backupCount=logging_config.backup_count,
        )
        err_fh.setLevel(logging.ERROR)
        err_fh.setFormatter(StructuredLogFormatter())
        component_logger.addHandler(err_fh)

    return component_logger


# Initialize global trade logger
trade_logger = TradeLogger(logging_config.trade_log_csv)
