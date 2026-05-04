from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PnLSnapshot:
    symbol: str
    unrealized_pnl_exchange: Optional[float]
    cum_realized_pnl_exchange: Optional[float]
    fees_total_execution: float
    realized_pnl_execution: float
    net_expectancy: float


def build_net_expectancy(
    symbol: str,
    unrealized_pnl_exchange: Optional[float],
    cum_realized_pnl_exchange: Optional[float],
    fees_total_execution: float,
    realized_pnl_execution: float,
    slippage_estimate: float = 0.0,
) -> PnLSnapshot:
    """
    Unified metric:
      net_expectancy = realized(exec) + unrealized(exchange) - fees(exec) - slippage_estimate
    If exchange unrealized is missing, it is treated as 0 in this unified metric.
    """
    unreal = unrealized_pnl_exchange if unrealized_pnl_exchange is not None else 0.0
    net = realized_pnl_execution + unreal - fees_total_execution - slippage_estimate
    return PnLSnapshot(
        symbol=symbol,
        unrealized_pnl_exchange=unrealized_pnl_exchange,
        cum_realized_pnl_exchange=cum_realized_pnl_exchange,
        fees_total_execution=float(fees_total_execution),
        realized_pnl_execution=float(realized_pnl_execution),
        net_expectancy=float(net),
    )

