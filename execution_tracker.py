from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str  # "Buy" | "Sell"
    qty: float
    price: float
    fee: float
    fee_currency: str
    is_maker: Optional[bool]
    ts_ms: int
    exec_id: str
    order_id: Optional[str] = None


class ExecutionTracker:
    """
    Execution-aware accounting layer.
    - polls /v5/execution/list via Exchange.get_executions()
    - persists fills as JSONL (append-only) for auditability
    - computes per-symbol fee totals and realized PnL (FIFO inventory)
    """

    def __init__(self, exchange, log_dir: str = "logs"):
        self.ex = exchange
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._seen_exec_ids = set()  # in-process dedupe
        self._cursor_by_symbol: Dict[str, str] = {}
        self._last_poll_ms_by_symbol: Dict[str, int] = {}
        self._fills_path = self.log_dir / "fills.jsonl"

        # FIFO inventory for realized PnL (symbol -> list of (side, qty, price))
        self._inv: Dict[str, List[Tuple[str, float, float]]] = {}
        self._fees: Dict[str, float] = {}
        self._realized: Dict[str, float] = {}

    def _append_fill(self, f: Fill) -> None:
        with self._fills_path.open("a", encoding="utf-8") as w:
            w.write(json.dumps(asdict(f), ensure_ascii=False) + "\n")

    @staticmethod
    def _to_float(x: Any, default: float = 0.0) -> float:
        try:
            if x is None or x == "":
                return default
            return float(x)
        except Exception:
            return default

    @staticmethod
    def _to_int_ms(x: Any, default: int) -> int:
        try:
            if x is None or x == "":
                return default
            return int(float(x))
        except Exception:
            return default

    @staticmethod
    def _maker_flag(row: Dict[str, Any]) -> Optional[bool]:
        # Bybit may expose isMaker as "1"/"0" or bool; be tolerant.
        v = row.get("isMaker", None)
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in {"1", "true", "yes"}:
            return True
        if s in {"0", "false", "no"}:
            return False
        return None

    def poll_symbol(self, symbol: str, limit: int = 100) -> List[Fill]:
        """
        Returns new fills discovered since last poll (best-effort).
        Uses cursor if present; falls back to time window.
        """
        now_ms = int(time.time() * 1000)
        start_ms = self._last_poll_ms_by_symbol.get(symbol, now_ms - 60_000)
        cursor = self._cursor_by_symbol.get(symbol)

        resp = self.ex.get_executions(
            symbol=symbol,
            limit=limit,
            cursor=cursor,
            start_time_ms=start_ms,
            end_time_ms=now_ms,
        )
        if int(resp.get("retCode", -1)) != 0:
            return []

        r = resp.get("result", {}) or {}
        rows = r.get("list", []) or []
        next_cursor = r.get("nextPageCursor")
        if next_cursor:
            self._cursor_by_symbol[symbol] = str(next_cursor)
        self._last_poll_ms_by_symbol[symbol] = now_ms

        out: List[Fill] = []
        for row in rows:
            exec_id = str(row.get("execId") or row.get("execID") or row.get("id") or "")
            if not exec_id:
                continue
            if exec_id in self._seen_exec_ids:
                continue
            self._seen_exec_ids.add(exec_id)

            f = Fill(
                symbol=str(row.get("symbol") or symbol),
                side=str(row.get("side") or ""),
                qty=self._to_float(row.get("execQty", row.get("qty", 0.0))),
                price=self._to_float(row.get("execPrice", row.get("price", 0.0))),
                fee=self._to_float(row.get("execFee", row.get("fee", 0.0))),
                fee_currency=str(row.get("feeCurrency", row.get("feeCoin", row.get("feeCurrency", ""))) or ""),
                is_maker=self._maker_flag(row),
                ts_ms=self._to_int_ms(row.get("execTime", row.get("time", None)), default=now_ms),
                exec_id=exec_id,
                order_id=str(row.get("orderId") or "") or None,
            )
            if f.qty <= 0 or f.price <= 0:
                continue
            self._append_fill(f)
            out.append(f)

        # Sort chronologically for stable FIFO accounting
        out.sort(key=lambda x: x.ts_ms)
        for f in out:
            self._apply_fill(f)
        return out

    def _apply_fill(self, f: Fill) -> None:
        # fees
        self._fees[f.symbol] = self._fees.get(f.symbol, 0.0) + abs(f.fee)

        inv = self._inv.setdefault(f.symbol, [])
        side = f.side
        if side not in {"Buy", "Sell"}:
            return

        # If we buy -> we increase long inventory; sell -> reduce long or increase short.
        # We'll track inventory signed by direction: +qty means long, -qty means short.
        fill_qty = f.qty if side == "Buy" else -f.qty
        fill_px = f.price

        # Realized PnL when fill crosses existing inventory opposite sign
        realized = 0.0

        def sign(x: float) -> int:
            return 1 if x > 0 else -1 if x < 0 else 0

        q = fill_qty
        while q != 0.0 and inv:
            inv_side_qty, inv_px = inv[0]
            if sign(inv_side_qty) == sign(q):
                break
            # match
            m = min(abs(inv_side_qty), abs(q))
            # long->sell or short->buy
            if inv_side_qty > 0 and q < 0:
                realized += (fill_px - inv_px) * m
            elif inv_side_qty < 0 and q > 0:
                realized += (inv_px - fill_px) * m
            inv_side_qty = inv_side_qty + (m if inv_side_qty < 0 else -m)
            q = q + (m if q < 0 else -m)
            if abs(inv_side_qty) < 1e-12:
                inv.pop(0)
            else:
                inv[0] = (inv_side_qty, inv_px)

        if abs(q) >= 1e-12:
            inv.append((q, fill_px))

        if realized != 0.0:
            self._realized[f.symbol] = self._realized.get(f.symbol, 0.0) + realized

    def get_symbol_metrics(self, symbol: str) -> Dict[str, float]:
        return {
            "fees_total": float(self._fees.get(symbol, 0.0)),
            "realized_pnl": float(self._realized.get(symbol, 0.0)),
        }

