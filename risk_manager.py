"""
Risk Manager - Position sizing, SL/TP calculation, exposure limits
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import numpy as np

from config import risk_config, trading_config, fee_config
from logger import get_logger, log_event

logger = get_logger()

# Bybit symbol precision and limits (testnet)
SYMBOL_PRECISION = {
    "BTCUSDT": {"qty_precision": 3, "min_qty": 0.001, "max_qty": 10000},
    "ETHUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 50000},  # Changed to 1 decimal
    "SOLUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 500000},  # Changed to 1 decimal
    "XRPUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 1000000},
    "DOGEUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 5000000},
    "ADAUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 2000000},
    "AVAXUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 100000},
    "MATICUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 5000000},
    "LINKUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 100000},
    "DOTUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 500000},
    "WIFUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 1000000},  # Low price token, integer qty
    "TRXUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 5000000},
    "LTCUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 100000},
    "BCHUSDT": {"qty_precision": 1, "min_qty": 0.1, "max_qty": 10000},
    "NEARUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 2000000},
    "OPUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 5000000},
    "ARBUSDT": {"qty_precision": 0, "min_qty": 1, "max_qty": 5000000},
}


def format_quantity(symbol: str, qty: float) -> float:
    """Format quantity according to Bybit symbol precision and limits"""
    if symbol not in SYMBOL_PRECISION:
        # Default to 3 decimals if symbol not found
        precision = 3
        min_qty = 0.001
        max_qty = 1000000
    else:
        precision = SYMBOL_PRECISION[symbol]["qty_precision"]
        min_qty = SYMBOL_PRECISION[symbol]["min_qty"]
        max_qty = SYMBOL_PRECISION[symbol]["max_qty"]

    # Cap at max quantity
    qty = min(qty, max_qty)

    # Ensure minimum quantity
    qty = max(qty, min_qty)

    # Round to precision
    return round(qty, precision)


@dataclass
class PositionSize:
    """Calculated position size with risk parameters"""
    size: float  # Position size in contracts/base currency
    notional: float  # Position value in USDT
    leverage: int
    risk_amount: float  # Risk in USDT
    stop_loss_price: float
    take_profit_1: float
    take_profit_2: float
    rr_ratio: float
    confidence: float  # 0.0 to 1.0 - sizing confidence


@dataclass
class RiskStatus:
    """Current risk status"""
    daily_pnl: float
    daily_trades: int
    consecutive_losses: int
    total_exposure: float
    max_exposure_reached: bool
    daily_loss_limit_hit: bool
    trading_paused: bool
    pause_until: Optional[datetime]


class RiskManager:
    """
    Manages all risk aspects:
    - Position sizing based on volatility
    - Leverage adjustment
    - Daily limits tracking
    - Kill switch functionality
    """
    
    def __init__(self):
        self.cfg = risk_config
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._consecutive_losses = 0
        self._last_reset_date = datetime.utcnow().date()
        self._trading_paused = False
        self._pause_until: Optional[datetime] = None
        self._trade_history: list = []
    
    def _check_daily_reset(self):
        """Reset daily counters if new day"""
        current_date = datetime.utcnow().date()
        if current_date != self._last_reset_date:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset_date = current_date
            self._trading_paused = False
            self._pause_until = None
            log_event("info", "Daily risk counters reset")
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        atr: float,
        signal_confidence: float,
        volatility_pct: float,
        symbol: str = "BTCUSDT"
    ) -> PositionSize:
        """
        Calculate position size - FIXED 100k USDT for futures mad mode
        """
        self._check_daily_reset()

        # FIXED POSITION SIZE: 100,000 USDT notional for futures
        position_notional = 100000.0  # Fixed 100k USDT
        logger.info(f"Fixed position size: ${position_notional:.2f} (mad mode)")

        # Calculate leverage based on symbol max leverage (use default leverage)
        if trading_config.category == "spot":
            leverage = 1  # No leverage for spot
        else:
            # Use default leverage, capped at symbol max
            base_leverage = trading_config.default_leverage
            symbol_max = trading_config.symbol_max_leverage.get(symbol, trading_config.max_leverage)
            leverage = min(base_leverage, symbol_max)
            logger.info(f"Using leverage: {leverage}x (max for {symbol}: {symbol_max}x)")

        # Calculate size in contracts
        position_size = position_notional / entry_price

        # Format quantity according to Bybit symbol precision
        position_size = format_quantity(symbol, position_size)

        # Recalculate notional with formatted size
        position_notional = position_size * entry_price

        # Calculate risk amount (4% loss = 4000 USDT on 100k position)
        risk_amount = position_notional * 0.04

        log_event("info", f"Position calculated: ${position_notional:.2f} notional, {leverage}x lev",
                  size=position_size,
                  notional=position_notional,
                  leverage=leverage,
                  risk=risk_amount)

        return PositionSize(
            size=position_size,
            notional=position_notional,
            leverage=leverage,
            risk_amount=risk_amount,
            stop_loss_price=stop_loss_price,
            take_profit_1=stop_loss_price,  # Not used - TP/SL from strategy
            take_profit_2=stop_loss_price,  # Not used - TP/SL from strategy
            rr_ratio=2.5,  # 10% profit / 4% loss = 2.5:1
            confidence=signal_confidence
        )
    
    def can_trade(self, account_balance: float) -> Tuple[bool, str]:
        """
        Check if trading is allowed based on risk limits
        """
        self._check_daily_reset()
        
        # Check trading pause
        if self._trading_paused:
            if self._pause_until and datetime.utcnow() < self._pause_until:
                remaining = (self._pause_until - datetime.utcnow()).total_seconds() / 60
                return False, f"Trading paused for {remaining:.0f} more minutes"
            else:
                # Resume trading
                self._trading_paused = False
                self._pause_until = None
                log_event("info", "Trading resumed from pause")
        
        # Check daily loss limit
        daily_loss_limit = account_balance * self.cfg.max_daily_loss_pct
        if abs(min(0, self._daily_pnl)) >= daily_loss_limit:
            self._trigger_pause(60 * 24)  # Pause for 24 hours
            return False, f"Daily loss limit hit: ${self._daily_pnl:.2f}"

        # Check consecutive losses - DISABLED for mad mode
        # if self._consecutive_losses >= self.cfg.max_consecutive_losses:
        #     self._trigger_pause(60 * 4)  # Pause for 4 hours
        #     return False, f"Max consecutive losses reached: {self._consecutive_losses}"

        # Check max daily trades
        if self._daily_trades >= trading_config.max_daily_trades:
            return False, f"Max daily trades reached: {self._daily_trades}"
        
        return True, "OK"
    
    def _trigger_pause(self, minutes: int):
        """Trigger trading pause"""
        self._trading_paused = True
        self._pause_until = datetime.utcnow() + timedelta(minutes=minutes)
        log_event("warning", f"Trading PAUSED for {minutes} minutes due to risk limit",
                  pause_duration_minutes=minutes,
                  daily_pnl=self._daily_pnl,
                  consecutive_losses=self._consecutive_losses)
    
    def on_trade_closed(
        self,
        pnl_net: float,
        trade_duration_minutes: float,
        was_stop_loss: bool
    ):
        """Update risk tracking when trade closes"""
        self._check_daily_reset()
        
        self._daily_pnl += pnl_net
        self._daily_trades += 1
        
        if pnl_net < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        
        self._trade_history.append({
            "pnl": pnl_net,
            "time": datetime.utcnow(),
            "duration": trade_duration_minutes,
            "was_sl": was_stop_loss
        })
        
        # Trim history
        cutoff = datetime.utcnow() - timedelta(days=30)
        self._trade_history = [t for t in self._trade_history if t["time"] > cutoff]
        
        log_event("info", f"Trade closed: PnL=${pnl_net:.2f}, Daily=${self._daily_pnl:.2f}",
                  pnl=pnl_net,
                  daily_pnl=self._daily_pnl,
                  daily_trades=self._daily_trades,
                  consecutive_losses=self._consecutive_losses)
    
    def calculate_realistic_pnl(
        self,
        entry_price: float,
        exit_price: float,
        size: float,
        leverage: int,
        direction: str,  # "long" or "short"
        duration_hours: float = 0
    ) -> Dict[str, float]:
        """
        Calculate realistic PnL including all fees
        For spot trading (no leverage, no funding fees)
        """
        notional = size * entry_price

        # Gross PnL (no leverage for spot)
        if direction == "long":
            price_diff = exit_price - entry_price
        else:
            price_diff = entry_price - exit_price

        gross_pnl = price_diff * size

        # Fees (spot trading - no funding fees)
        entry_fee = notional * fee_config.taker_fee
        exit_fee = (size * exit_price) * fee_config.taker_fee

        # No funding fees for spot trading
        funding_fee = 0

        # Slippage (no leverage for spot)
        slippage_cost = notional * self.cfg.slippage_pct

        total_fees = entry_fee + exit_fee + funding_fee + slippage_cost
        
        net_pnl = gross_pnl - total_fees
        
        return {
            "gross_pnl": gross_pnl,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "funding_fee": funding_fee,
            "slippage": slippage_cost,
            "total_fees": total_fees,
            "net_pnl": net_pnl,
            "roi_pct": (net_pnl / notional) * 100 if notional > 0 else 0
        }
    
    def get_status(self, account_balance: float = 0) -> RiskStatus:
        """Get current risk status"""
        self._check_daily_reset()

        daily_loss_limit = account_balance * self.cfg.max_daily_loss_pct
        daily_loss_hit = abs(min(0, self._daily_pnl)) >= daily_loss_limit

        return RiskStatus(
            daily_pnl=self._daily_pnl,
            daily_trades=self._daily_trades,
            consecutive_losses=self._consecutive_losses,
            total_exposure=0.0,  # Updated by portfolio
            max_exposure_reached=False,
            daily_loss_limit_hit=daily_loss_hit,
            trading_paused=self._trading_paused,
            pause_until=self._pause_until
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get risk statistics"""
        if not self._trade_history:
            return {"total_trades": 0}
        
        pnls = [t["pnl"] for t in self._trade_history]
        
        return {
            "total_trades": len(pnls),
            "win_rate": len([p for p in pnls if p > 0]) / len(pnls) * 100,
            "avg_pnl": np.mean(pnls),
            "max_drawdown": min(pnls) if pnls else 0,
            "profit_factor": (
                sum(p for p in pnls if p > 0) / abs(sum(p for p in pnls if p < 0))
                if sum(p for p in pnls if p < 0) != 0 else float('inf')
            )
        }


# Global risk manager instance
risk_manager = RiskManager()
