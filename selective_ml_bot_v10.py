"""
V10 Research ML Bot
===================
Thin subclass of SelectiveMLBot that swaps in V10ProductionConfig and wires up
the v10_research/ helpers via the hook points exposed in v9.1.

What v10 does on top of v9.1:
1. Logs EVERY signal (allowed and rejected) to logs/v10/signals_all.jsonl
2. Opens a shadow (paper) trade for every rejected signal, capped at 24h hold
3. Tracks MFE/MAE in R-units for every real position; persisted on close
4. Snapshots model features at entry (content-hashed file under feature_snapshots/)
5. Writes real trades to logs/v10/trades_v10.jsonl (separated from v9 history)
6. Uses an isolated last_state.json under logs/v10/ for persistence

NB: v9.1 stays untouched (no behavioural change). All v10 logic lives here.

Run with the SAME config.yaml as v9.1; the strategy class controls the rest.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Set, Tuple

import requests
from loguru import logger  # parent uses loguru; standard logging would be silenced

from selective_config_v10 import V10ProductionConfig
from selective_ml_bot import PositionState, SelectiveMLBot
from v10_research import (
    FeatureSnapshot,
    MFEMAETracker,
    ShadowTracker,
    SignalLogger,
    SymbolBiasTracker,
    UniverseFilter,
)


class V10MLBot(SelectiveMLBot):
    """v10 research subclass. Hooks fire from the parent's run/monitor loop."""

    def __init__(self, cfg_path: str):
        # Parent __init__ creates self.prod = ProductionConfig() AND reads paths
        # from getattr(self.prod, "v10_*", None). We need V10 paths active BEFORE
        # super().__init__ runs, so we monkey-patch self.prod creation by deferring
        # to an instance attribute set after super(). The path resolution in
        # parent uses getattr(self.prod, ...), so we re-run that after assigning.
        super().__init__(cfg_path)
        # Replace v9.1 ProductionConfig with V10ProductionConfig.
        self.prod = V10ProductionConfig()
        # Re-resolve paths now that v10 attributes are present on self.prod.
        self._state_path = Path(self.prod.v10_state_path)
        self._health_path = Path(self.prod.v10_health_path)
        self._trades_log_path = Path(self.prod.v10_trades_path)
        for p in (self._state_path, self._health_path, self._trades_log_path):
            p.parent.mkdir(parents=True, exist_ok=True)
        # Re-load state from the v10 path (parent loaded from default path; harmless).
        self.position_states.clear()
        self._load_state()
        # ---- v10 research helpers ----
        self.signal_logger = SignalLogger(self.prod.v10_signals_path)
        self.shadow_tracker = ShadowTracker(
            output_path=self.prod.v10_shadow_path,
            max_hold_sec=self.prod.shadow_max_hold_sec,
            max_open=self.prod.shadow_max_open,
        )
        self.mfe_tracker = MFEMAETracker()
        self.feature_snap = FeatureSnapshot(self.prod.v10_features_dir)
        self.universe_filter = UniverseFilter(
            top_n=self.prod.scan_top_symbols,
            refresh_sec=self.prod.universe_refresh_sec,
            min_turnover_usdt=self.prod.universe_min_volume_usdt,
            min_range_pct=self.prod.universe_min_range_pct,
        )
        self.symbol_bias = SymbolBiasTracker(
            Path(self.prod.v10_log_dir) / "symbol_bias.jsonl",
            min_samples=3,
        )
        # Maintain a stable mapping symbol -> trade_id so MFE/MAE survives sync.
        self._symbol_trade_id: Dict[str, str] = {}
        # Track last signal timestamp per symbol for bars_since_last_signal metric.
        self._last_signal_ts: Dict[str, float] = {}
        # Per-symbol price history (ts, price) for trend_direction & price_change_*h.
        # Keep up to 24h+ of samples; ~12 signals/min across symbols means modest memory.
        self._price_history: Dict[str, Deque[Tuple[float, float]]] = {}
        self._price_history_path = Path(self.prod.v10_log_dir) / "price_history.json"
        self._price_history_last_save_ts: float = 0.0
        self._price_history_save_interval_sec: float = 60.0  # flush to disk at most every minute
        self._load_price_history()
        # Symbols whose 24h history we've already backfilled from the exchange.
        self._backfilled_symbols: Set[str] = set()
        # BE-stop armed flag per trade_id (so we don't re-arm or move SL backwards).
        self._be_stop_armed: Dict[str, bool] = {}
        # Save strategy snapshot for full reproducibility.
        self._save_strategy_snapshot()
        logger.info(
            f"[V10] research framework armed. strategy_id={self.prod.strategy_id} "
            f"signals={self.prod.v10_signals_path} trades={self.prod.v10_trades_path} "
            f"shadow={self.prod.v10_shadow_path} max_hold={self.prod.shadow_max_hold_sec}s"
        )

    # ------------------------------------------------------------------ helpers
    def _save_strategy_snapshot(self) -> None:
        try:
            from dataclasses import asdict
            snap_dir = Path(self.prod.v10_strategies_dir)
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_path = snap_dir / f"{self.prod.strategy_id}.json"
            payload = asdict(self.prod)
            payload["snapshot_ts"] = time.time()
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"[V10] strategy snapshot saved: {snap_path}")
        except Exception as e:
            logger.warning(f"[V10] strategy snapshot failed: {e}")

    def _record_price(self, symbol: str, ts: float, price: float) -> None:
        """Append (ts, price) to per-symbol history; prune older than 25h. Persist to disk periodically.

        On first call per symbol, opportunistically backfill 24h of hourly closes from Bybit
        so that price_change_24h is available immediately (no 24h warmup needed).
        """
        if not symbol or price <= 0:
            return
        # Lazy backfill: first time we see this symbol, fetch klines.
        if symbol not in self._backfilled_symbols:
            self._backfill_kline_history(symbol, ts)
            self._backfilled_symbols.add(symbol)
        hist = self._price_history.get(symbol)
        if hist is None:
            hist = deque(maxlen=5000)
            self._price_history[symbol] = hist
        hist.append((ts, price))
        cutoff = ts - 25 * 3600
        while hist and hist[0][0] < cutoff:
            hist.popleft()
        # Flush to disk every ~60s so restarts don't wipe out 24h of history.
        if ts - self._price_history_last_save_ts >= self._price_history_save_interval_sec:
            self._save_price_history()
            self._price_history_last_save_ts = ts

    def _backfill_kline_history(self, symbol: str, now_ts: float) -> None:
        """Fetch ~25h of 5-min klines from Bybit public API and seed price_history.

        Public endpoint (no auth):
          GET https://api.bybit.com/v5/market/kline?category=linear&symbol=...&interval=5&limit=300

        300 x 5min = 25h coverage. We use the close price of each bar as a sample.
        Skips backfill silently on any error (don't break trading loop).
        """
        try:
            # If we already have >= 24h of data for this symbol (loaded from disk), skip.
            existing = self._price_history.get(symbol)
            if existing:
                oldest_ts = existing[0][0] if existing else now_ts
                if (now_ts - oldest_ts) >= 24 * 3600:
                    return
            url = "https://api.bybit.com/v5/market/kline"
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": "5",   # 5-minute bars
                "limit": 300,      # 300 * 5min = 25h
            }
            r = requests.get(url, params=params, timeout=4.0)
            if r.status_code != 200:
                return
            data = r.json()
            if str(data.get("retCode")) != "0":
                return
            klist = (data.get("result") or {}).get("list") or []
            if not klist:
                return
            # Bybit returns newest-first: [ts_ms, open, high, low, close, volume, turnover]
            samples = []
            cutoff = now_ts - 25 * 3600
            for row in klist:
                try:
                    ts = float(row[0]) / 1000.0
                    close = float(row[4])
                    if ts >= cutoff and close > 0:
                        samples.append((ts, close))
                except Exception:
                    continue
            if not samples:
                return
            samples.sort(key=lambda x: x[0])  # oldest -> newest
            existing = self._price_history.get(symbol)
            if existing is None:
                existing = deque(maxlen=5000)
                self._price_history[symbol] = existing
            # Merge: only add samples older than the oldest existing sample.
            existing_oldest = existing[0][0] if existing else float("inf")
            added = 0
            # Prepend older samples (build new deque preserving order).
            new_dq = deque(maxlen=5000)
            for ts, p in samples:
                if ts < existing_oldest:
                    new_dq.append((ts, p))
                    added += 1
            for item in existing:
                new_dq.append(item)
            self._price_history[symbol] = new_dq
            logger.info(f"[V10 BACKFILL] {symbol} added {added} klines (total {len(new_dq)}, span {(new_dq[-1][0]-new_dq[0][0])/3600:.1f}h)")
        except Exception as e:
            logger.debug(f"[V10 BACKFILL] {symbol} failed: {e}")

    def _save_price_history(self) -> None:
        """Persist price_history to disk so it survives bot restarts."""
        try:
            self._price_history_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                sym: list(hist)  # convert deque -> list for JSON
                for sym, hist in self._price_history.items()
                if hist
            }
            tmp = self._price_history_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            tmp.replace(self._price_history_path)
        except Exception as e:
            logger.debug(f"[V10 PRICE HIST SAVE] {e}")

    def _load_price_history(self) -> None:
        """Load price_history from disk on startup. Drops samples older than 25h."""
        try:
            if not self._price_history_path.exists():
                return
            with open(self._price_history_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            cutoff = time.time() - 25 * 3600
            restored = 0
            for sym, samples in payload.items():
                if not samples:
                    continue
                fresh = [(float(ts), float(p)) for ts, p in samples if float(ts) >= cutoff and float(p) > 0]
                if not fresh:
                    continue
                dq = deque(fresh, maxlen=5000)
                self._price_history[sym] = dq
                restored += len(fresh)
            logger.info(f"[V10 PRICE HIST LOAD] restored {restored} samples across {len(self._price_history)} symbols from {self._price_history_path}")
        except Exception as e:
            logger.warning(f"[V10 PRICE HIST LOAD] failed: {e}")

    def _price_change_pct(self, symbol: str, now_ts: float, current_price: float, lookback_sec: float) -> Optional[float]:
        """Return % change vs nearest historical price >= lookback_sec ago. None if no data."""
        hist = self._price_history.get(symbol)
        if not hist or current_price <= 0:
            return None
        target_ts = now_ts - lookback_sec
        ref_price = None
        # Walk from oldest; first sample with ts <= target_ts becomes reference (closest before).
        for ts, price in hist:
            if ts <= target_ts:
                ref_price = price
            else:
                break
        if ref_price is None or ref_price <= 0:
            return None
        return (current_price - ref_price) / ref_price

    def _trend_direction(self, pc_24h: Optional[float], pc_4h: Optional[float]) -> Optional[str]:
        """Classify trend from price changes. Up if both positive & 24h>5%, etc."""
        if pc_24h is None:
            return None
        if pc_24h >= 0.05:
            return "up"
        if pc_24h <= -0.05:
            return "down"
        if pc_4h is not None:
            if pc_4h >= 0.03:
                return "up_short"
            if pc_4h <= -0.03:
                return "down_short"
        return "neutral"

    def _write_excursion_history(self, trade_id: str, st: PositionState, excursion: Dict[str, Any], history: list) -> None:
        """Append one full-trajectory line to logs/v10/excursion_history.jsonl."""
        try:
            path = Path(self.prod.v10_log_dir) / "excursion_history.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "trade_id": trade_id,
                "symbol": st.symbol,
                "side": st.side,
                "entry_price": float(st.entry_price or 0.0),
                "stop_loss_price": float(excursion.get("stop_loss_price") or 0.0),
                "take_profit_price": float(excursion.get("take_profit_price") or 0.0),
                "opened_ts": float(excursion.get("opened_ts") or 0.0),
                "closed_ts": time.time(),
                "mfe_r": excursion.get("mfe_r"),
                "mae_r": excursion.get("mae_r"),
                "samples": int(excursion.get("samples") or 0),
                # samples_history is a list of [ts, price] pairs.
                "history": history,
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception as e:
            logger.debug(f"[V10 EXCURSION WRITE] {st.symbol}: {e}")

    # ------------------------------------------------------------------ phase-aware gating

    # Phase x Side -> (allow, size_multiplier). None for size means "block" (allow=False).
    # Logic:
    #   - Trade WITH the trend:    pump->long, dump->short  (boost)
    #   - Don't catch knives:      pump->short, dump->long  (block)
    #   - Be careful at extremes:  parabolic_*, dump_bottom  (penalty)
    #   - At distribution / start: pump_top, dump_start      (favor reversal side)
    PHASE_RULES: Dict[Tuple[str, str], Optional[float]] = {
        # (phase, side): size_multiplier  (None == block entry)
        ("pump", "long"):              1.30,
        ("pump", "short"):             None,
        ("pump_top", "long"):          0.50,
        ("pump_top", "short"):         1.20,
        ("dump_start", "long"):        None,
        ("dump_start", "short"):       1.30,
        ("dump", "long"):              None,
        ("dump", "short"):             1.20,
        ("dump_bottom", "long"):       0.50,
        ("dump_bottom", "short"):      0.30,
        ("bounce", "long"):            1.20,
        ("bounce", "short"):           None,
        ("parabolic_up", "long"):      None,
        ("parabolic_up", "short"):     0.30,
        ("parabolic_down", "long"):    0.30,
        ("parabolic_down", "short"):   None,
        ("uptrend", "long"):           1.00,
        ("uptrend", "short"):          0.70,
        ("downtrend", "long"):         0.70,
        ("downtrend", "short"):        1.00,
        ("flat", "long"):              1.00,
        ("flat", "short"):             1.00,
    }

    def _compute_market_phase_for_signal(self, sig: Dict[str, Any]) -> Optional[str]:
        """Compute market_phase from current price history; returns None if history insufficient."""
        symbol = sig.get("symbol", "")
        entry = self._safe_float(sig.get("entry"))
        if not symbol or entry <= 0:
            return None
        now_ts = time.time()
        # NOTE: price gets recorded in _v10_hook_signal_evaluated AFTER allowed(), so we
        # use a read-only path here (no side effects).
        pc_1h = self._price_change_pct(symbol, now_ts, entry, 3600)
        pc_4h = self._price_change_pct(symbol, now_ts, entry, 4 * 3600)
        pc_24h = self._price_change_pct(symbol, now_ts, entry, 24 * 3600)
        return self._market_phase(pc_24h, pc_4h, pc_1h)

    def _apply_phase_gating(self, sig: Dict[str, Any], ok: bool, reason: str, size_mult: float) -> Tuple[bool, str, float]:
        """Adjust (ok, reason, size_mult) based on market_phase. No-op if phase unknown."""
        if not ok:
            return ok, reason, size_mult  # already rejected; don't override
        if not getattr(self.prod, "phase_gating_enabled", True):
            return ok, reason, size_mult
        phase = self._compute_market_phase_for_signal(sig)
        if phase is None:
            return ok, reason, size_mult  # not enough history yet
        side = sig.get("direction", "")
        rule = self.PHASE_RULES.get((phase, side))
        if rule is None and (phase, side) in self.PHASE_RULES:
            # Explicit None -> block.
            new_reason = f"phase_block({phase}+{side})"
            logger.info(f"[V10 PHASE] BLOCK {sig.get('symbol')} {side} phase={phase}")
            return False, new_reason, size_mult
        if rule is None:
            return ok, reason, size_mult  # no rule defined -> default allow
        if abs(rule - 1.0) > 0.01:
            new_mult = float(size_mult) * float(rule)
            logger.info(
                f"[V10 PHASE] {sig.get('symbol')} {side} phase={phase} "
                f"size_mult {size_mult:.2f} -> {new_mult:.2f} (factor {rule})"
            )
            return ok, reason, new_mult
        return ok, reason, size_mult

    def allowed(self, sig, positions, equity, used):
        """Override of parent gate: apply phase-aware modifications on top of v9.1 logic."""
        ok, reason, size_mult = super().allowed(sig, positions, equity, used)
        try:
            return self._apply_phase_gating(sig, ok, reason, size_mult)
        except Exception as e:
            logger.debug(f"[V10 PHASE GATE] {sig.get('symbol')}: {e}")
            return ok, reason, size_mult

    def _build_extra(self, symbol: str, side: str, market_phase: Optional[str]) -> Optional[Dict[str, Any]]:
        """Build the 'extra' dict for signal logging (symbol_bias + market_phase)."""
        extra: Dict[str, Any] = {}
        bias = self.symbol_bias.bias(symbol, side)
        if bias:
            extra["symbol_bias"] = bias
        if market_phase is not None:
            extra["market_phase"] = market_phase
        return extra or None

    def _market_phase(self, pc_24h: Optional[float], pc_4h: Optional[float], pc_1h: Optional[float]) -> Optional[str]:
        """Detailed market phase classifier (pump/dump/transition/flat).

        Decision tree (priority top-down):
          - parabolic_up:    pc_24h > +50%
          - parabolic_down:  pc_24h < -30%
          - pump:            pc_24h > +20%  AND pc_4h > +5%   (still rising hard)
          - pump_top:        pc_24h > +20%  AND |pc_4h| <= 3% (distribution)
          - dump_start:      pc_24h > +5%   AND pc_4h < -5%   (reversal from pump)
          - dump:            pc_24h < -10%  AND pc_4h < -3%   (knife)
          - dump_bottom:     pc_24h < -10%  AND |pc_4h| <= 3% (capitulation)
          - bounce:          pc_24h < -10%  AND pc_4h > +5%   (dead cat / real bounce)
          - uptrend:         +5%  < pc_24h <= +20%
          - downtrend:       -20% < pc_24h <= -5%
          - flat:            |pc_24h| <= 5%
        Returns None if pc_24h missing (history not yet warm).
        """
        if pc_24h is None:
            return None
        # Parabolic extremes first (override others).
        if pc_24h > 0.50:
            return "parabolic_up"
        if pc_24h < -0.30:
            return "parabolic_down"
        # Pump zone (24h > +20%).
        if pc_24h > 0.20:
            if pc_4h is not None:
                if pc_4h > 0.05:
                    return "pump"
                if abs(pc_4h) <= 0.03:
                    return "pump_top"
                if pc_4h < -0.05:
                    return "dump_start"
            return "pump"  # default if 4h missing
        # Strong reversal from positive 24h to negative 4h.
        if pc_24h > 0.05 and pc_4h is not None and pc_4h < -0.05:
            return "dump_start"
        # Dump zone (24h < -10%).
        if pc_24h < -0.10:
            if pc_4h is not None:
                if pc_4h > 0.05:
                    return "bounce"
                if abs(pc_4h) <= 0.03:
                    return "dump_bottom"
                if pc_4h < -0.03:
                    return "dump"
            return "dump"
        # Mild trends.
        if pc_24h > 0.05:
            return "uptrend"
        if pc_24h < -0.05:
            return "downtrend"
        return "flat"

    @staticmethod
    def _safe_float(x, default: float = 0.0) -> float:
        try:
            if x is None:
                return default
            return float(x)
        except Exception:
            return default

    def _shadow_brackets(self, sig: Dict[str, Any]) -> tuple[float, float]:
        """Compute (sl, tp) for a shadow trade using the same ATR formula as real trades."""
        entry = self._safe_float(sig.get("entry"))
        atr = self._safe_float(sig.get("atr"))
        side = sig.get("direction", "")
        if entry <= 0 or atr <= 0 or side not in ("long", "short"):
            return 0.0, 0.0
        sl_mult = self._safe_float(self.prod.sl_atr_mult, 0.5)
        tp_mult = self._safe_float(self.prod.tp1_r, 0.5)
        if side == "long":
            sl = entry - sl_mult * atr
            tp = entry + tp_mult * atr
        else:
            sl = entry + sl_mult * atr
            tp = entry - tp_mult * atr
        return float(sl), float(tp)

    # ------------------------------------------------------------------ V10 HOOKS
    def _v10_hook_signal_evaluated(self, sig: Dict[str, Any], allow: bool, reason: str, size_mult: float) -> None:
        """Log every signal + open shadow trade for rejects + update shadow MFE/MAE."""
        try:
            symbol = sig.get("symbol", "")
            side = sig.get("direction", "")
            entry = self._safe_float(sig.get("entry"))
            atr = self._safe_float(sig.get("atr"))
            atr_pct = (atr / entry) if entry > 0 else 0.0
            # Best-effort fetch of regime/funding/spread/volume from the signal payload itself.
            now_ts = time.time()
            from datetime import datetime, timezone
            dt_utc = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            hour_utc = dt_utc.hour
            day_of_week = dt_utc.weekday()
            is_weekend = day_of_week >= 5
            last_ts = self._last_signal_ts.get(symbol, 0)
            bars_since = int((now_ts - last_ts) / 300) if last_ts > 0 else None  # 5-min bars
            self._last_signal_ts[symbol] = now_ts
            # Record price + compute price changes from history.
            self._record_price(symbol, now_ts, entry)
            pc_1h = self._price_change_pct(symbol, now_ts, entry, 3600)
            pc_4h = self._price_change_pct(symbol, now_ts, entry, 4 * 3600)
            pc_24h = self._price_change_pct(symbol, now_ts, entry, 24 * 3600)
            trend_dir = self._trend_direction(pc_24h, pc_4h)
            market_phase = self._market_phase(pc_24h, pc_4h, pc_1h)
            self.signal_logger.log(
                symbol=symbol,
                side=side,
                confidence=self._safe_float(sig.get("confidence")),
                score=self._safe_float(sig.get("score")),
                ev=self._safe_float(sig.get("ev")),
                regime=str(sig.get("regime", "")),
                atr=atr,
                atr_pct=atr_pct,
                spread_bps=self._safe_float(sig.get("spread_bps")),
                volume_24h=self._safe_float(sig.get("volume_24h_usdt")) or self._safe_float(sig.get("volume_24h")),
                funding_rate=self._safe_float(sig.get("funding_rate")),
                btc_trend=str(sig.get("btc_trend", "")) or None,
                allow=allow,
                reject_reason=None if allow else reason,
                size_mult=size_mult,
                # v10b: soft-filter metrics recorded for post-hoc analytics.
                adx=self._safe_float(sig.get("adx")),
                agreement=int(self._safe_float(sig.get("agreement")) or 0),
                uncertainty=self._safe_float(sig.get("uncertainty")),
                depth_usdt=self._safe_float(sig.get("depth_usdt")),
                quality_score=self._safe_float(sig.get("score")),
                trend_direction=trend_dir,
                hour_utc=hour_utc,
                day_of_week=day_of_week,
                is_weekend=is_weekend,
                price_change_1h=pc_1h,
                price_change_4h=pc_4h,
                price_change_24h=pc_24h,
                bars_since_last_signal=bars_since,
                extra=self._build_extra(symbol, side, market_phase),
            )
        except Exception as e:
            logger.debug(f"[V10 SIGNAL LOG] failed {sig.get('symbol')}: {e}")
        # Update existing shadows for this symbol with the latest entry price.
        try:
            if entry > 0:
                self.shadow_tracker.update_symbol(symbol, entry)
        except Exception:
            pass
        # If rejected and paper-trading enabled, open a shadow trade.
        if (not allow) and self.prod.paper_trade_all_signals:
            sl, tp = self._shadow_brackets(sig)
            if sl > 0 and tp > 0:
                try:
                    self.shadow_tracker.open_shadow(
                        symbol=symbol,
                        side=side,
                        entry_price=entry,
                        stop_loss_price=sl,
                        take_profit_price=tp,
                        confidence=self._safe_float(sig.get("confidence")),
                        score=self._safe_float(sig.get("score")),
                        ev=self._safe_float(sig.get("ev")),
                        regime=str(sig.get("regime", "")),
                        reject_reason=reason or "unknown",
                    )
                except Exception as e:
                    logger.debug(f"[V10 SHADOW OPEN] failed {symbol}: {e}")

    def _v10_hook_position_opened(self, st: PositionState, sig: Dict[str, Any]) -> None:
        """Snapshot features and start MFE/MAE tracking."""
        logger.warning(f"[V10 HOOK] position_opened called for {st.symbol}")
        trade_id = uuid.uuid4().hex[:16]
        st_meta = st.signal_meta or {}
        st_meta["v10_trade_id"] = trade_id
        # Capture market_phase at entry for post-trade analysis.
        try:
            entry_phase = self._compute_market_phase_for_signal(sig)
            if entry_phase:
                st_meta["market_phase"] = entry_phase
        except Exception:
            pass
        # Save feature snapshot if enabled.
        feature_hash: Optional[str] = None
        if self.prod.feature_snapshot_on_entry:
            try:
                feature_hash = self.feature_snap.save(
                    symbol=st.symbol,
                    side=st.side,
                    confidence=self._safe_float(sig.get("confidence")),
                    score=self._safe_float(sig.get("score")),
                    features=dict(sig),  # full signal payload acts as feature record
                    model_version=str(self.prod.model),
                    extra={"trade_id": trade_id, "strategy_id": self.prod.strategy_id},
                )
                st_meta["v10_feature_hash"] = feature_hash
            except Exception as e:
                logger.warning(f"[V10 SNAPSHOT] failed {st.symbol}: {e}")
        st.signal_meta = st_meta
        # Open MFE/MAE tracker.
        if self.prod.mfe_mae_tracking:
            try:
                self.mfe_tracker.open(
                    trade_id=trade_id,
                    symbol=st.symbol,
                    side=st.side,
                    entry_price=float(st.entry_price),
                    stop_loss_price=float(st.stop_loss_price),
                    take_profit_price=float(st.take_profit_levels.get("tp1", st.entry_price)),
                    opened_ts=st.opened_ts or time.time(),
                )
                self._symbol_trade_id[st.symbol] = trade_id
            except Exception as e:
                logger.debug(f"[V10 MFE OPEN] failed {st.symbol}: {e}")
        logger.info(
            f"[V10 OPEN] {st.symbol} trade_id={trade_id} feature_hash={feature_hash} "
            f"strategy_id={self.prod.strategy_id}"
        )

    def _v10_hook_price_tick(self, symbol: str, price: float, st: PositionState) -> None:
        """Update MFE/MAE, manage BE-stop & trailing, progress shadow trades."""
        # Update MFE/MAE for any open real trade on this symbol.
        try:
            tid = self._symbol_trade_id.get(symbol)
            if tid:
                self.mfe_tracker.update(tid, price)
                self._maybe_arm_be_stop(tid, st)
                self._maybe_update_trailing(tid, st)
        except Exception as e:
            logger.debug(f"[V10 PRICE TICK] {symbol}: {e}")
        # Update shadow trades for this symbol; closed ones are flushed inside.
        try:
            self.shadow_tracker.update_symbol(symbol, price)
        except Exception:
            pass

    def _maybe_arm_be_stop(self, trade_id: str, st: PositionState) -> None:
        """If MFE >= be_arm_threshold_r, move SL to entry +/- be_offset_r (lock fees+).

        Re-arms if v9 core (_rebuild_brackets_for_state) resets stop_loss_price.
        Uses excursion.r_unit() (original SL distance) so resets don't affect the math.
        """
        arm_thr = float(getattr(self.prod, "be_stop_arm_threshold_r", 0.3))
        offset_r = float(getattr(self.prod, "be_stop_offset_r", 0.05))
        if arm_thr <= 0:
            return  # feature disabled
        excursion = self.mfe_tracker.get(trade_id)
        if excursion is None or excursion.mfe_r < arm_thr:
            return
        entry = float(st.entry_price or 0.0)
        if entry <= 0:
            return
        # Use original r_unit from excursion (v9 core may reset st.stop_loss_price).
        r_unit = excursion.r_unit()
        if r_unit <= 0:
            return
        # Compute target BE SL.
        if st.side == "long":
            target_sl = entry - offset_r * r_unit  # BE below entry for long
            # Already tightened (or better)?
            if st.stop_loss_price and float(st.stop_loss_price) <= target_sl:
                self._be_stop_armed[trade_id] = True
                return
        else:  # short
            target_sl = entry + offset_r * r_unit  # BE above entry for short
            if st.stop_loss_price and float(st.stop_loss_price) >= target_sl:
                self._be_stop_armed[trade_id] = True
                return
        st.stop_loss_price = float(target_sl)
        st.updated_ts = time.time()
        self._be_stop_armed[trade_id] = True
        logger.warning(
            f"[V10 BE-STOP] {st.symbol} {st.side} mfe_r={excursion.mfe_r:.2f}R "
            f"target_sl={target_sl:.6f} entry={entry:.6f}"
        )

    def _maybe_update_trailing(self, trade_id: str, st: PositionState) -> None:
        """Trail SL once MFE >= trail_arm_threshold_r. SL = mfe_price -/+ trail_dist_r * R.

        Only ever tightens the SL (never moves it backwards). Works on top of BE-stop:
        once trailing arms (typically at +1R), it overrides the BE-stop level.
        """
        arm_thr = float(getattr(self.prod, "trail_arm_threshold_r", 0.0))
        dist_r = float(getattr(self.prod, "trail_dist_r", 0.0))
        if arm_thr <= 0 or dist_r <= 0:
            return  # disabled
        excursion = self.mfe_tracker.get(trade_id)
        if excursion is None or excursion.mfe_r < arm_thr:
            return
        entry = float(st.entry_price or 0.0)
        old_sl = float(st.stop_loss_price or 0.0)
        if entry <= 0 or old_sl <= 0:
            return
        # Reconstruct r_unit from the trade's original SL distance (BE-stop may have shrunk it,
        # so we use entry-distance to take_profit OR reconstruct via excursion fields).
        original_sl = float(excursion.stop_loss_price or old_sl)
        r_unit = abs(entry - original_sl)
        if r_unit <= 0:
            return
        mfe_price = float(excursion.mfe_price or 0.0)
        if mfe_price <= 0:
            return
        if st.side == "long":
            new_sl = mfe_price - dist_r * r_unit
            if new_sl <= old_sl:
                return  # don't widen
        else:  # short
            new_sl = mfe_price + dist_r * r_unit
            if new_sl >= old_sl:
                return
        st.stop_loss_price = float(new_sl)
        st.updated_ts = time.time()
        # Only log significant trail moves (>0.05R difference) to avoid log spam.
        if abs(new_sl - old_sl) >= 0.05 * r_unit:
            logger.warning(
                f"[V10 TRAIL] {st.symbol} {st.side} mfe_r={excursion.mfe_r:.2f}R "
                f"mfe_px={mfe_price:.6f} old_sl={old_sl:.6f} new_sl={new_sl:.6f}"
            )

    def _v10_hook_trade_closed_record(self, st: PositionState, record: Dict[str, Any]) -> None:
        """Enrich the trade record with v10 fields just before it is written."""
        try:
            tid = (st.signal_meta or {}).get("v10_trade_id")
            # Clean up BE-stop tracking for this trade.
            if tid:
                self._be_stop_armed.pop(tid, None)
            feature_hash = (st.signal_meta or {}).get("v10_feature_hash")
            record["strategy_id"] = self.prod.strategy_id
            record["v10_trade_id"] = tid
            record["v10_feature_hash"] = feature_hash
            if tid:
                excursion = self.mfe_tracker.close(tid, include_history=True)
                if excursion:
                    record["mfe_r"] = excursion.get("mfe_r")
                    record["mae_r"] = excursion.get("mae_r")
                    record["mfe_price"] = excursion.get("mfe_price")
                    record["mae_price"] = excursion.get("mae_price")
                    record["excursion_samples"] = excursion.get("samples")
                    # v10c: persist full price trajectory to a separate file so that
                    # trades_v10.jsonl stays small but we can run accurate exit-strategy backtests.
                    history = excursion.get("samples_history") or []
                    if history:
                        self._write_excursion_history(tid, st, excursion, history)
            # Compute realised exit_r in R-units using the exchange-reported exit price.
            entry = float(st.entry_price or 0.0)
            exit_price = float(record.get("exit_price") or 0.0)
            sl = float(st.stop_loss_price or 0.0)
            r_unit = abs(entry - sl) if entry and sl else 0.0
            if r_unit > 0 and exit_price > 0:
                if st.side == "long":
                    record["exit_r"] = (exit_price - entry) / r_unit
                else:
                    record["exit_r"] = (entry - exit_price) / r_unit
            # Cleanup mapping.
            if st.symbol in self._symbol_trade_id:
                self._symbol_trade_id.pop(st.symbol, None)
            # Record outcome for symbol bias tracking.
            try:
                pnl = float(record.get("realized_pnl_net", 0.0))
                tid = (st.signal_meta or {}).get("v10_trade_id", "")
                self.symbol_bias.record(st.symbol, st.side, pnl, tid)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[V10 RECORD ENRICH] failed {st.symbol}: {e}")


# ---------------------------------------------------------------------- entrypoint
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="Path to config.yaml")
    args = ap.parse_args()
    bot = V10MLBot(args.config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
