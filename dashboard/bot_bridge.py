from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import get_origin

from loguru import logger

from dashboard.store import Store


DEFAULT_CONTROL = {
    "paused": False,
    "trading_enabled": True,
    "kill_switch_triggered": False,
    "kill_switch_reason": None,
    "emergency_stop": False,
}
DEFAULT_RISK = {
    "risk_per_trade_pct": 0.0,
    "max_open_positions": 0,
    "max_daily_loss_pct": 0.0,
    "max_daily_loss_usd": 0.0,
    "max_drawdown_pct": 0.0,
    "max_position_notional_usdt": 0.0,
    "max_leverage": 1,
    "long_enabled": True,
    "short_enabled": True,
    "allowed_symbols": [],
    "kill_switch_enabled": True,
    "kill_switch_close_positions": False,
    "kill_switch_auto_reset_daily": True,
}


def _float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def bucket_confidence(c):
    c = _float(c)
    if c < 0.50:
        return "<0.50"
    for lo in (0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50):
        if c >= lo:
            hi = lo + 0.05
            return f"{lo:.2f}-{hi:.2f}" if lo < 0.90 else "0.90+"
    return "0.90+"


def bucket_adx(v):
    v = _float(v)
    for lo, hi in ((40, None), (30, 40), (25, 30), (20, 25), (15, 20), (10, 15)):
        if hi is None and v >= lo:
            return "40+"
        if hi is not None and lo <= v < hi:
            return f"{lo}-{hi}"
    return "<10"


def bucket_atr_pct(v):
    v = _float(v)
    if v < 0.15:
        return "low"
    if v < 0.4:
        return "normal"
    if v < 0.8:
        return "high"
    return "extreme"


def bucket_volume(rel):
    rel = _float(rel)
    if rel < 0.7:
        return "low"
    if rel < 1.3:
        return "normal"
    if rel < 2.5:
        return "high"
    return "extreme"


def bucket_funding(rate):
    rate = _float(rate)
    if rate >= 0.0005:
        return "strong_positive"
    if rate > 0.0001:
        return "positive"
    if rate <= -0.0005:
        return "strong_negative"
    if rate < -0.0001:
        return "negative"
    return "neutral"


def bucket_oi(change):
    if change is None:
        return None
    change = _float(change)
    if change > 0.02:
        return "strong_rising"
    if change > 0.005:
        return "rising"
    if change < -0.02:
        return "strong_falling"
    if change < -0.005:
        return "falling"
    return "neutral"


def bucket_depth(depth):
    depth = _float(depth)
    if depth < 2000:
        return "<2k"
    if depth < 7000:
        return "2k-7k"
    if depth < 20000:
        return "7k-20k"
    if depth < 50000:
        return "20k-50k"
    return "50k+"


def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def trade_row_from_record(
    record: dict,
    realized_pnl_net: float | None = None,
    exit_reason: str | None = None,
    exit_price: float | None = None,
) -> dict:
    signal = record.get("signal") or {}
    levels = record.get("take_profit_levels") or {}
    reasons = record.get("exit_reasons") or []
    last_reason = ""
    if reasons:
        last = reasons[-1]
        last_reason = str(last.get("reason", "") if isinstance(last, dict) else last)
    pnl = _float(record.get("realized_pnl_net") if realized_pnl_net is None else realized_pnl_net)
    entry = _float(record.get("entry_price"))
    qty = _float(record.get("qty_total"))
    stop_loss = _float(record.get("stop_loss_price"))
    notional = _float(record.get("notional_entry"), entry * qty)
    # Correct risk amount: use provided value, else fall back to intended SL distance.
    risk_amount = _float(record.get("risk_amount"))
    r_multiple_calc = record.get("r_multiple_calc") or "sl_based"
    if risk_amount <= 0 and stop_loss > 0:
        risk_amount = abs(entry - stop_loss) * qty
        r_multiple_calc = "sl_based"
    # If no TP/SL was used, risk is effectively the notional and R is a return ratio.
    if risk_amount <= 0 and notional > 0:
        risk_amount = notional
        r_multiple_calc = "notional_fallback"
    r_multiple = record.get("r_multiple")
    if r_multiple is None and risk_amount > 0:
        r_multiple = pnl / risk_amount
    return {
        "trade_id": record.get("trade_id") or f"{record.get('symbol', '')}_{int(_float(record.get('opened_ts')))}",
        "strategy_id": record.get("strategy_id"),
        "symbol": record.get("symbol"),
        "side": record.get("direction") or record.get("side"),
        "opened_ts": _float(record.get("opened_ts")),
        "closed_ts": record.get("closed_ts"),
        "duration_sec": record.get("duration_sec"),
        "entry_price": entry,
        "exit_price": _float(record.get("exit_price") if exit_price is None else exit_price),
        "qty": qty,
        "notional": notional,
        "leverage": int(_float(record.get("leverage"), 0)),
        "stop_loss": stop_loss,
        "tp1": _float(levels.get("tp1")),
        "tp2": _float(levels.get("tp2")),
        "tp3": _float(levels.get("tp3")),
        "pnl": pnl,
        "pnl_pct": (pnl / notional * 100.0) if notional else None,
        "pnl_source": record.get("pnl_source"),
        "fees_est": _float(record.get("entry_fees_est")) + _float(record.get("exit_fees_est")),
        "fees_actual": None,
        "funding_est": _float(record.get("funding_estimate")),
        "r_multiple": r_multiple,
        "risk_amount": risk_amount,
        "r_multiple_calc": r_multiple_calc,
        "exit_reason": exit_reason or last_reason or "manual_or_external",
        "exit_reasons_json": json.dumps(reasons, ensure_ascii=False, default=str),
        "signal_json": json.dumps(signal, ensure_ascii=False, default=str),
        "raw_json": json.dumps(record, ensure_ascii=False, default=str),
        "confidence": signal.get("confidence"),
        "regime": signal.get("regime"),
        "ev": signal.get("ev"),
        "score": signal.get("score"),
        "updated_ts": time.time(),
        "signal_snapshot_id": record.get("signal_snapshot_id"),
        "signal_id": signal.get("signal_id") or record.get("signal_id"),
        "mae": record.get("mae"),
        "mfe": record.get("mfe"),
        "mae_r": record.get("mae_r"),
        "mfe_r": record.get("mfe_r"),
        "gross_pnl": record.get("gross_pnl"),
        "result": record.get("result") or (
            "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
        ),
        "size_mult": signal.get("size_mult"),
    }


class BotBridge:
    def __init__(self, store: Store | None = None, strategy_id: str = "unknown", config_path: str = ""):
        self.store = store or Store()
        self.strategy_id = strategy_id
        self.config_path = config_path
        self.started_ts = time.time()
        self._cache = {}
        self._bybit_ok = False
        self._bybit_last_ok_ts = None
        self._bybit_last_error = None
        self._sink_id = None

    def _cached_setting(self, key, default):
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < 2.0:
            return dict(cached[1])
        value = self.store.get_setting(key, {}) or {}
        merged = dict(default)
        if isinstance(value, dict):
            merged.update(value)
        self._cache[key] = (now, merged)
        return dict(merged)

    def control(self) -> dict:
        return self._cached_setting("control", DEFAULT_CONTROL)

    def risk(self) -> dict:
        return self._cached_setting("risk", DEFAULT_RISK)

    def is_paused(self) -> bool:
        control = self.control()
        return bool(control.get("paused") or control.get("emergency_stop"))

    def trading_enabled(self) -> bool:
        control = self.control()
        return bool(control.get("trading_enabled", True)) and not bool(control.get("kill_switch_triggered"))

    def risk_check(self, sig: dict, open_positions: list[dict], equity: float) -> tuple[bool, str]:
        if not self.trading_enabled():
            return False, "dashboard_trading_disabled"
        risk = self.risk()
        direction = str(sig.get("direction", "")).lower()
        if direction == "long" and not risk.get("long_enabled", True):
            return False, "dashboard_long_disabled"
        if direction == "short" and not risk.get("short_enabled", True):
            return False, "dashboard_short_disabled"
        allowed_symbols = risk.get("allowed_symbols") or []
        if allowed_symbols and sig.get("symbol") not in allowed_symbols:
            return False, "dashboard_symbol_not_allowed"
        max_positions = int(_float(risk.get("max_open_positions"), 0))
        if max_positions > 0:
            active = sum(1 for position in open_positions if _float(position.get("size", position.get("qty", 0))) > 0)
            if active >= max_positions:
                return False, "dashboard_max_positions"
        return True, "ok"

    def cap_qty(self, symbol: str, qty, entry: float):
        value = _decimal(qty)
        cap = _decimal(self.risk().get("max_position_notional_usdt"))
        if cap > 0 and _decimal(entry) > 0:
            capped = cap / _decimal(entry)
            if value > capped:
                self.event(
                    "WARNING",
                    "RISK_SIZE_CAPPED",
                    f"{symbol} quantity capped by dashboard notional limit",
                    symbol=symbol,
                    metadata={"requested_qty": str(value), "capped_qty": str(capped), "entry": entry},
                )
                return capped
        return value

    def check_kill_switch(self, equity: float, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        risk = self.risk()
        state = self.store.get_setting("kill_switch_state", {}) or {}
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        if state.get("day") != day:
            state = {
                "day": day,
                "day_start_equity": float(equity),
                "peak_equity": _float(state.get("peak_equity"), float(equity)),
                "triggered": False,
                "triggered_reason": None,
                "triggered_ts": None,
            }
            self.store.set_setting("kill_switch_state", state)
            if risk.get("kill_switch_auto_reset_daily", True):
                control = self.control()
                control["kill_switch_triggered"] = False
                control["kill_switch_reason"] = None
                self.store.set_setting("control", control)
                self._cache.pop("control", None)
        state["peak_equity"] = max(_float(state.get("peak_equity"), float(equity)), float(equity))
        self.store.set_setting("kill_switch_state", state)
        self.store.set_setting("equity_peak", state["peak_equity"])
        if not risk.get("kill_switch_enabled", True):
            return bool(self.control().get("kill_switch_triggered"))
        day_start = _float(state.get("day_start_equity"))
        peak = _float(state.get("peak_equity"))
        daily_loss_usd = day_start - float(equity)
        daily_loss_pct = daily_loss_usd / day_start * 100.0 if day_start > 0 else 0.0
        drawdown_pct = (peak - float(equity)) / peak * 100.0 if peak > 0 else 0.0
        reason = None
        if _float(risk.get("max_daily_loss_pct")) > 0 and daily_loss_pct >= _float(risk["max_daily_loss_pct"]):
            reason = f"daily_loss_pct={daily_loss_pct:.4f}"
        elif _float(risk.get("max_daily_loss_usd")) > 0 and daily_loss_usd >= _float(risk["max_daily_loss_usd"]):
            reason = f"daily_loss_usd={daily_loss_usd:.4f}"
        elif _float(risk.get("max_drawdown_pct")) > 0 and drawdown_pct >= _float(risk["max_drawdown_pct"]):
            reason = f"drawdown_pct={drawdown_pct:.4f}"
        if reason and not state.get("triggered"):
            state["triggered"] = True
            state["triggered_reason"] = reason
            state["triggered_ts"] = now
            self.store.set_setting("kill_switch_state", state)
            control = self.control()
            control["kill_switch_triggered"] = True
            control["kill_switch_reason"] = reason
            self.store.set_setting("control", control)
            self._cache.pop("control", None)
            self.event(
                "CRITICAL",
                "RISK_LIMIT_REACHED",
                f"kill_switch_triggered {reason}",
                metadata={"reason": reason, "equity": equity},
            )
            logger.warning(f"[RISK] kill_switch_triggered reason={reason} equity={equity}")
        return bool(state.get("triggered") or self.control().get("kill_switch_triggered"))

    def position_overrides(self, symbol) -> dict | None:
        overrides = self.store.get_setting("position_overrides", {}) or {}
        value = overrides.get(symbol)
        if value is not None:
            overrides.pop(symbol, None)
            self.store.set_setting("position_overrides", overrides)
        return value

    def heartbeat(self, **fields):
        row = {
            "ts": time.time(),
            "pid": os.getpid(),
            "started_ts": self.started_ts,
            "paused": int(self.is_paused()),
            "trading_enabled": int(self.trading_enabled()),
            "strategy_id": self.strategy_id,
            "config_path": self.config_path,
            "bybit_ok": int(self._bybit_ok),
            "bybit_last_ok_ts": self._bybit_last_ok_ts,
            "bybit_last_error": self._bybit_last_error,
        }
        row.update(fields)
        self.store.write_heartbeat(row)

    def bybit_ok(self):
        self._bybit_ok = True
        self._bybit_last_ok_ts = time.time()
        self._bybit_last_error = None

    def bybit_error(self, msg):
        self._bybit_ok = False
        self._bybit_last_error = str(msg)

    def record_signal(self, sig, allowed, reason):
        self.store.insert_signal(
            {
                "ts": time.time(),
                "symbol": sig.get("symbol"),
                "direction": sig.get("direction"),
                "confidence": sig.get("confidence"),
                "score": sig.get("score"),
                "ev": sig.get("ev"),
                "regime": sig.get("regime"),
                "agreement": sig.get("agreement"),
                "allowed": int(bool(allowed)),
                "reason": reason,
                "strategy_id": sig.get("strategy_id", self.strategy_id),
            }
        )
        return self._record_signal_snapshot(sig, allowed, reason)

    def _record_signal_snapshot(self, sig, allowed, reason):
        try:
            ts = _float(sig.get("timestamp"), time.time()) or time.time()
            dt = datetime.fromtimestamp(ts, timezone.utc)
            atr = _float(sig.get("atr"))
            entry = _float(sig.get("entry"))
            atr_pct = atr / entry * 100.0 if entry > 0 else None
            reasons = sig.get("_rejection_reasons")
            extra = {}
            for key, value in (sig.get("full_features") or {}).items():
                if isinstance(value, (int, float, str, bool)) or value is None:
                    extra[key] = value
            row = {
                "ts": ts,
                "signal_id": sig.get("_signal_id") or None,
                "symbol": sig.get("symbol"),
                "direction": sig.get("direction"),
                "timeframe": sig.get("timeframe"),
                "entry_price": entry,
                "probability_long": sig.get("probability_long"),
                "probability_short": sig.get("probability_short"),
                "predicted_direction": sig.get("predicted_direction"),
                "di_plus": sig.get("di_plus"),
                "di_minus": sig.get("di_minus"),
                "ema_slope": sig.get("ema_slope"),
                "ret_1": sig.get("ret_1"), "ret_3": sig.get("ret_3"),
                "ret_5": sig.get("ret_5"), "ret_10": sig.get("ret_10"),
                "momentum": sig.get("momentum"),
                "distance_from_high": sig.get("distance_from_high"),
                "distance_from_low": sig.get("distance_from_low"),
                "volume_change": sig.get("volume_change"),
                "confidence": _float(sig.get("confidence")),
                "probability": sig.get("probability"),
                "agreement": int(_float(sig.get("agreement"))),
                "h3_dir": sig.get("h3_dir"), "h3_conf": sig.get("h3_conf"),
                "h5_dir": sig.get("h5_dir"), "h5_conf": sig.get("h5_conf"),
                "h10_dir": sig.get("h10_dir"), "h10_conf": sig.get("h10_conf"),
                "regime": sig.get("regime"),
                "regime_confidence": sig.get("regime_confidence"),
                "trend_score": sig.get("trend_score"),
                "breakout_score": sig.get("breakout_score"),
                "chop_score": sig.get("chop_score"),
                "panic_score": sig.get("panic_score"),
                "atr": atr,
                "atr_pct": atr_pct,
                "realized_volatility": sig.get("realized_volatility"),
                "adx": sig.get("adx"),
                "ema_distance": sig.get("ema_distance"),
                "trend_strength": sig.get("trend_strength"),
                "volume": sig.get("volume"),
                "rel_volume": sig.get("rel_volume"),
                "spread_bps": _float(sig.get("spread_bps")),
                "spread_pct": sig.get("spread_pct"),
                "bid_depth": sig.get("bid_depth"),
                "ask_depth": sig.get("ask_depth"),
                "total_depth": sig.get("total_depth"),
                "imbalance": sig.get("imbalance"),
                "funding_rate": sig.get("funding_rate"),
                "open_interest": sig.get("open_interest"),
                "oi_change": sig.get("oi_change"),
                "basis": sig.get("basis"),
                "pc_1m": sig.get("pc_1m"), "pc_5m": sig.get("pc_5m"),
                "pc_15m": sig.get("pc_15m"), "pc_1h": sig.get("pc_1h"),
                "hl_range": sig.get("hl_range"),
                "wick_ratio": sig.get("wick_ratio"),
                "quality_score": _float(sig.get("score")),
                "uncertainty": sig.get("uncertainty"),
                "ev": sig.get("ev"),
                "edge_score": sig.get("edge_score"),
                "allowed": int(bool(allowed)),
                "rejection_reason": None if allowed else reason,
                "rejection_reasons_json": None if allowed else (reasons or ([reason] if reason else [])),
                "size_mult": sig.get("_size_mult"),
                "confidence_bucket": bucket_confidence(sig.get("confidence")),
                "adx_bucket": bucket_adx(sig.get("adx")),
                "atr_bucket": bucket_atr_pct(atr_pct),
                "volume_bucket": bucket_volume(sig.get("rel_volume")),
                "volatility_bucket": bucket_atr_pct(atr_pct),
                "funding_bucket": bucket_funding(sig.get("funding_rate")),
                "oi_bucket": bucket_oi(sig.get("oi_change")),
                "depth_bucket": bucket_depth(sig.get("depth_usdt")),
                "hour_utc": dt.hour,
                "dow_utc": dt.weekday(),
                "feature_version": sig.get("feature_version"),
                "signal_schema_version": sig.get("signal_schema_version"),
                "strategy_id": sig.get("strategy_id", self.strategy_id),
                "extra_json": extra or None,
            }
            return self.store.insert_signal_snapshot(row)
        except Exception:
            return None

    # --- Counterfactual outcome resolution (research only, never decision path) ---
    def list_unresolved_signals(self, min_ts, limit=500):
        return self.store.list_unresolved_signals(min_ts, limit)

    def insert_signal_outcome(self, row):
        self.store.insert_signal_outcome(row)

    def record_trade(self, record: dict, realized_pnl_net: float, exit_reason: str, exit_price: float):
        self.store.upsert_trade(trade_row_from_record(record, realized_pnl_net, exit_reason, exit_price))

    def patch_trade_pnl(self, trade_id, pnl, exit_price):
        self.store.update_trade_pnl(trade_id, pnl, exit_price, "bybit_closed_pnl_patch")

    def record_fill(self, fill_obj):
        row = asdict(fill_obj) if is_dataclass(fill_obj) else dict(fill_obj)
        row["raw_json"] = json.dumps(row, ensure_ascii=False, default=str)
        self.store.upsert_fill(row)

    def snapshot_positions(self, position_states: dict, exchange_rows_by_symbol: dict[str, dict], prices: dict[str, float]):
        rows = []
        for symbol, state in position_states.items():
            exchange = exchange_rows_by_symbol.get(symbol) or {}
            entry = _float(getattr(state, "entry_price", 0.0))
            stop = _float(getattr(state, "stop_loss_price", 0.0))
            total_qty = _decimal(getattr(state, "qty_total", 0))
            closed_qty = _decimal(getattr(state, "qty_closed", 0))
            remaining = max(Decimal("0"), total_qty - closed_qty)
            qty = _float(exchange.get("size"), _float(remaining))
            mark = _float(prices.get(symbol), _float(exchange.get("markPrice"), entry))
            unreal = exchange.get("unrealisedPnl", exchange.get("unrealizedPnl"))
            if unreal is None:
                unreal = (mark - entry) * qty if getattr(state, "side", "") == "long" else (entry - mark) * qty
            unreal = _float(unreal)
            denominator = entry * qty
            risk_dollars = abs(entry - stop) * qty if stop > 0 else 0.0
            levels = getattr(state, "take_profit_levels", {}) or {}
            rows.append(
                {
                    "symbol": symbol,
                    "side": getattr(state, "side", None),
                    "entry_price": entry,
                    "mark_price": mark,
                    "qty": qty,
                    "qty_closed": _float(closed_qty),
                    "leverage": int(_float(getattr(state, "leverage", 0))),
                    "stop_loss": stop,
                    "tp1": _float(levels.get("tp1")),
                    "tp2": _float(levels.get("tp2")),
                    "tp3": _float(levels.get("tp3")),
                    "trailing_price": _float(getattr(state, "trailing_price", 0)),
                    "unrealized_pnl": unreal,
                    "unrealized_pnl_pct": unreal / denominator * 100.0 if denominator else None,
                    "r_multiple": unreal / risk_dollars if risk_dollars else None,
                    "position_value": _float(exchange.get("positionValue"), mark * qty),
                    "cum_realised_pnl": _float(exchange.get("cumRealisedPnl"), _float(getattr(state, "cum_realised_pnl", 0))),
                    "opened_ts": _float(getattr(state, "opened_ts", 0)),
                    "strategy_id": self.strategy_id,
                    "exit_state": getattr(state, "exit_state", None),
                    "tp1_done": int(bool(getattr(state, "tp1_done", False))),
                    "tp2_done": int(bool(getattr(state, "tp2_done", False))),
                    "tp3_done": int(bool(getattr(state, "tp3_done", False))),
                    "signal_json": json.dumps(getattr(state, "signal_meta", {}) or {}, default=str),
                    "updated_ts": time.time(),
                }
            )
        self.store.replace_positions(rows)

    def snapshot_equity(self, wallet_resp: dict, open_positions: int):
        account = ((wallet_resp or {}).get("result") or {}).get("list") or [{}]
        values = account[0] if account else {}
        self.store.insert_equity(
            {
                "ts": time.time(),
                "equity": _float(values.get("totalEquity")),
                "wallet_balance": _float(values.get("totalWalletBalance")),
                "available_balance": _float(values.get("totalAvailableBalance")),
                "unrealized_pnl": _float(values.get("totalPerpUPL")),
                "open_positions": open_positions,
            }
        )

    def event(self, level, event_type, message, symbol=None, metadata=None):
        return self.store.insert_event(
            time.time(), level, event_type, message, symbol=symbol,
            strategy_id=self.strategy_id, metadata=metadata,
        )

    def apply_strategy_overrides(self, prod):
        overrides = self.store.get_setting(f"strategy_overrides:{self.strategy_id}", {}) or {}
        if not is_dataclass(prod) or not isinstance(overrides, dict):
            return []
        applied = []
        for field_info in fields(prod):
            if field_info.name not in overrides:
                continue
            value = overrides[field_info.name]
            expected = field_info.type
            origin = get_origin(expected)
            valid = (
                isinstance(value, list) if origin is list else
                isinstance(value, dict) if origin is dict else
                (type(value) is expected or (expected is float and type(value) is int))
                if expected in (int, float, bool, str) else False
            )
            if valid:
                setattr(prod, field_info.name, value)
                applied.append(field_info.name)
        if applied:
            logger.info(f"[STRATEGY] overrides applied keys={applied}")
        return applied

    def _sink(self, message):
        try:
            text = str(message).strip()
            record = getattr(message, "record", {}) or {}
            level = getattr(record.get("level"), "name", "INFO")
            symbol = self._symbol(text)
            clean = re.sub(
                r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ \| [A-Z]+ *\| [^ ]+ - ",
                "",
                text,
            )
            try:
                self.store.insert_log(
                    record.get("time").timestamp() if record.get("time") else time.time(),
                    level,
                    self._log_category(clean, level),
                    clean,
                    symbol=symbol,
                )
            except Exception:
                pass
            event_type = None
            event_level = level
            metadata = {}
            if "[FALLBACK OPEN]" in text or "[OPEN]" in text:
                event_type = "POSITION_OPENED"
            elif "[EXIT]" in text:
                event_type = "POSITION_CLOSED_PARTIAL" if self._number(text, "remaining") > 0 else "POSITION_CLOSED"
                reason = self._value(text, "reason")
                if reason == "stop_loss":
                    event_type = "SL_HIT"
                elif reason.startswith("tp"):
                    event_type = "TP_HIT"
                elif reason == "trailing_exit":
                    event_type = "TRAILING_EXIT"
                elif reason == "signal_reversal":
                    event_type = "REVERSAL_EXIT"
            elif "[EXIT FAIL]" in text or "[ENTRY FAIL]" in text:
                event_type, event_level = "ORDER_FAILED", "WARNING"
            elif "[TRADE RECORDED]" in text:
                event_type = "TRADE_RECORDED"
                metadata["pnl"] = self._number(text, "realized_pnl_net")
            elif "[MANUAL_INTERVENTION_DETECTED]" in text:
                event_type, event_level = "MANUAL_INTERVENTION", "WARNING"
            elif "[RECONCILE_TRIGGERED]" in text:
                event_type, event_level = "POSITION_RECONCILED", "WARNING"
            elif "[MANUAL_OVERRIDE]" in text:
                event_type = "MANUAL_OVERRIDE"
            elif "[RISK]" in text:
                if "kill_switch_triggered" in text:
                    return
                event_type, event_level = "RISK_EVENT", "WARNING"
            elif "[HEALTH] graceful_shutdown" in text:
                event_type = "BOT_STOPPED"
            elif "[HEALTH] stop_requested" in text:
                event_type = "BOT_STOP_REQUESTED"
            elif "[BOOT]" in text:
                event_type = "BOT_STARTED"
            elif "[LOOP EXCEPTION]" in text or "[ENTRY EXCEPTION]" in text or "[MONITOR] exception" in text:
                event_type, event_level = "BOT_ERROR", "ERROR"
                text = text[:500]
            elif "[LOOP] get_positions failed" in text:
                event_type, event_level = "BYBIT_CONNECTION_ERROR", "ERROR"
                self.bybit_error(text)
            elif any(tag in text for tag in ("[STICKINESS]", "[SIGNAL]", "[POSITION]", "[EXPECTANCY]", "[FILL]", "[EXCHANGE POS]")):
                return
            if event_type:
                self.event(event_level, event_type, text, symbol=symbol, metadata=metadata or None)
        except Exception:
            return

    _TRADE_TAGS = (
        "[OPEN]", "[EXIT]", "[FILL]", "[TRADE", "[ORDER", "[ENTRY", "[POSITION]",
        "[TP", "[SL", "POSITION_OPENED", "POSITION_CLOSED", "filled", "Fill ",
    )
    _SYSTEM_TAGS = (
        "[BOOT]", "[HEALTH]", "[DASHBOARD]", "[RISK]", "[KILL", "[RECONCILE",
        "[MANUAL", "graceful_shutdown", "stop_requested", "[STATE]",
    )

    @classmethod
    def _log_category(cls, text, level):
        if any(tag in text for tag in cls._TRADE_TAGS):
            return "TRADE"
        if level in ("WARNING", "ERROR", "CRITICAL"):
            return level if level != "CRITICAL" else "ERROR"
        if any(tag in text for tag in cls._SYSTEM_TAGS):
            return "SYSTEM"
        if level == "SUCCESS":
            return "SUCCESS"
        return "INFO"

    @staticmethod
    def _symbol(text):
        match = re.search(r"\b([A-Z0-9]+USDT)\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _value(text, key):
        match = re.search(rf"\b{re.escape(key)}=([^\s]+)", text)
        return match.group(1).rstrip(",") if match else ""

    @classmethod
    def _number(cls, text, key):
        return _float(cls._value(text, key), 0.0)

    def install_log_sink(self):
        if self._sink_id is None:
            self._sink_id = logger.add(self._sink, level="INFO")
        return self._sink_id
