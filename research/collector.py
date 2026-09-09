from __future__ import annotations

import json
import time
import traceback
from typing import Any



SIGNAL_SCHEMA_VERSION = "v1"


def _float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _json(value):
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


class ResearchCollector:
    """Write-only research layer. Trading logic never reads from here."""

    def __init__(self, bridge=None, strategy_id: str = "unknown"):
        # Lazy imports so the module can load even if the dashboard package
        # is not present in this environment.
        try:
            from dashboard.store import Store
        except Exception:
            from dashboard_server_backup.store import Store

        self.bridge = bridge
        self.strategy_id = strategy_id
        self.store = bridge.store if bridge is not None else Store()

    def _safe(self, fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except Exception:
            # Research must never break trading.
            return None

    def record_tier1_reject(self, symbol: str, reason: str, context: dict | None = None):
        """Record cheap tier-1 rejects (low vol, low pct, low depth)."""
        row = {
            "ts": time.time(),
            "symbol": symbol,
            "allowed": 0,
            "final_reason": reason,
            "all_reasons": [reason],
            "strategy_id": self.strategy_id,
        }
        if context:
            row.update(context)
        return self._safe(self.store.insert_signal_decision, row)

    def record_signal(
        self,
        sig: dict,
        allowed: bool,
        reason: str,
        all_reasons: list[str] | None = None,
    ) -> int | None:
        """Record the full signal snapshot and return the snapshot id."""
        # Enrich the signal with schema metadata before the bridge writes it.
        sig["feature_version"] = sig.get("feature_version") or "v2"
        sig["signal_schema_version"] = SIGNAL_SCHEMA_VERSION

        snapshot_id = None
        if self.bridge is not None:
            snapshot_id = self._safe(self.bridge.record_signal, sig, allowed, reason)

        sig["_snapshot_id"] = snapshot_id
        return snapshot_id

    def record_decision(
        self,
        sig: dict,
        allowed: bool,
        reason: str,
        all_reasons: list[str] | None,
        size_mult: float,
        override: bool,
        equity: float,
        used_notional: float,
        open_positions_count: int,
    ):
        """Record the final allow/reject decision with all reasons."""
        row = {
            "signal_id": str(sig.get("_snapshot_id") or sig.get("_dash_signal_id") or sig.get("_signal_id") or ""),
            "snapshot_id": sig.get("_snapshot_id") or sig.get("_dash_signal_id"),
            "ts": time.time(),
            "symbol": sig.get("symbol"),
            "direction": sig.get("direction"),
            "allowed": int(bool(allowed)),
            "final_reason": reason,
            "all_reasons": all_reasons or ([reason] if reason else []),
            "size_mult": _float(size_mult, 1.0),
            "override": int(bool(override)),
            "equity": _float(equity),
            "used_notional": _float(used_notional),
            "open_positions_count": open_positions_count,
            "strategy_id": sig.get("strategy_id") or sig.get("strategy_version") or self.strategy_id,
        }
        return self._safe(self.store.insert_signal_decision, row)

    def record_trade_entry(
        self,
        trade_id: str,
        signal_id: str | None,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        notional: float,
        risk_amount: float,
    ):
        """Record entry lifecycle event."""
        row = {
            "trade_id": trade_id,
            "ts": time.time(),
            "event_type": "entry",
            "price": entry_price,
            "metric": risk_amount,
            "metadata": {
                "signal_id": signal_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "notional": notional,
                "risk_amount": risk_amount,
            },
        }
        return self._safe(self.store.insert_trade_event, row)

    def record_trade_event(
        self,
        trade_id: str,
        event_type: str,
        ts: float,
        price: float,
        metric: float | None,
        metadata: dict | None = None,
    ):
        """Record any intra-trade metric (mfe, mae, drawdown, tp/sl hit)."""
        row = {
            "trade_id": trade_id,
            "ts": ts,
            "event_type": event_type,
            "price": price,
            "metric": metric,
            "metadata": metadata,
        }
        return self._safe(self.store.insert_trade_event, row)

    def record_exit(
        self,
        record: dict,
        realized_pnl_net: float,
        exit_reason: str,
        exit_price: float,
        r_multiple: float | None = None,
        r_multiple_calc: str | None = None,
        risk_amount: float | None = None,
    ):
        """Record closed trade. Computes correct r_multiple before storage."""
        pnl = _float(record.get("realized_pnl_net") if realized_pnl_net is None else realized_pnl_net)
        entry = _float(record.get("entry_price"))
        qty = _float(record.get("qty_total"))
        stop_loss = _float(record.get("stop_loss_price"))
        notional = _float(record.get("notional_entry"), entry * qty)

        if risk_amount is None:
            if stop_loss > 0:
                risk_amount = abs(entry - stop_loss) * qty
                r_multiple_calc = r_multiple_calc or "sl_based"
            elif notional > 0:
                risk_amount = notional
                r_multiple_calc = r_multiple_calc or "notional_fallback"

        if r_multiple is None and risk_amount and risk_amount > 0:
            r_multiple = pnl / risk_amount

        record["r_multiple"] = r_multiple
        record["r_multiple_calc"] = r_multiple_calc
        record["risk_amount"] = risk_amount

        # Update the trade object in the database with the corrected r values.
        if self.bridge is not None:
            return self._safe(
                self.bridge.record_trade,
                record,
                realized_pnl_net,
                exit_reason,
                exit_price,
            )
