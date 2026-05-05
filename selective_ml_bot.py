import argparse
import asyncio
import copy
import json
import os
import signal
import sys
# Ensure project root is in path for local imports (data/, execution/, ml/, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import threading
import time
import traceback
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging

import numpy as np
import pandas as pd
import requests
import yaml
from loguru import logger

from data.feature_store import FeatureStore
from data.market_stream import MarketStream
from data.orderbook_stream import OrderbookStream
from execution.slippage_guard import SlippageGuard
from execution.smart_router import SmartRouter
from execution.spread_guard import SpreadGuard
from ml.horizon_ensemble import HorizonEnsemble
from ml.model_catboost import DirectionModel
from ml.meta_label_model import MetaLabelModel
from portfolio.cooldown_manager import CooldownManager
from portfolio.exposure_limits import ExposureLimits
from regime.regime_classifier import RegimeClassifier
from risk.exit_engine import ExitEngine
from risk.portfolio_heat import PortfolioHeat
from risk.position_sizer import PositionSizer
from selective_config import ProductionConfig
from edge_engine import EdgeEngine
from expected_value_engine import ExpectedValueEngine
from quality_gate import QualityGate
from trader.exchange_demo import Exchange
from execution_tracker import ExecutionTracker
from pnl_engine import build_net_expectancy
from stats_collector import StatsCollector

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


def setup_logging():
    Path("logs").mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        backtrace=True,
        diagnose=True,
    )
    logger.add("logs/ml.log", rotation="10 MB", retention=10, enqueue=True, backtrace=True, diagnose=True)
    logger.add("logs/errors.log", level="ERROR", rotation="10 MB", retention=20, enqueue=True, backtrace=True, diagnose=True)
    logger.add("logs/trades.log", filter=lambda r: "[OPEN]" in r["message"] or "[EXIT]" in r["message"], rotation="10 MB", retention=20, enqueue=True)
    logger.add("logs/api.log", filter=lambda r: "[API" in r["message"] or "[EXCHANGE DEBUG]" in r["message"], rotation="10 MB", retention=20, enqueue=True)
    logger.add("logs/websocket.log", filter=lambda r: "[WS]" in r["message"], rotation="10 MB", retention=10, enqueue=True)
    logger.add("logs/risk.log", filter=lambda r: "[RISK]" in r["message"] or "[HEALTH]" in r["message"], rotation="10 MB", retention=20, enqueue=True)
    py_logger = logging.getLogger()
    py_logger.setLevel(logging.INFO)
    py_logger.handlers.clear()
    py_handler = RotatingFileHandler("logs/api.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8")
    py_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    py_logger.addHandler(py_handler)


def atr(df: pd.DataFrame, p: int = 14) -> float:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [(df["high"] - df["low"]), (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(p).mean().iloc[-1])


@dataclass
class PositionState:
    symbol: str
    side: str
    entry_price: float
    qty_total: Decimal
    qty_closed: Decimal
    entry_fees: float
    exit_fees_estimate: float
    funding_estimate: float
    stop_loss_price: float
    take_profit_levels: dict
    exit_state: str
    tp1_done: bool = False
    tp2_done: bool = False
    tp3_done: bool = False
    trailing_price: float = 0.0
    updated_ts: float = 0.0
    leverage: int = 0
    last_exchange_size: Decimal = Decimal("0")
    cum_realised_pnl: float = 0.0
    position_value_exchange: float = 0.0
    # Trade-recorder metadata (populated at entry; used at close).
    opened_ts: float = 0.0
    signal_meta: dict = field(default_factory=dict)
    exit_reasons: list = field(default_factory=list)  # list of (reason, qty_str, ts)
    cum_realised_pnl_entry: float = 0.0
    # Original qty_total at entry - used for TP percentage calculations
    qty_original: Decimal = Decimal("0")


class SelectiveMLBot:
    def __init__(self, cfg_path: str):
        setup_logging()
        self._stop_requested = False
        self.cfg = yaml.safe_load(open(cfg_path, "r", encoding="utf-8"))
        self.ex = Exchange(self.cfg)
        self.prod = ProductionConfig()
        try:
            logger.info(
                f"[BOOT] selective_ml_bot start sizing_mode={getattr(self.prod, 'sizing_mode', None)} "
                f"base_notional_usdt={getattr(self.prod, 'base_notional_usdt', None)} "
                f"strategy_id={getattr(self.prod, 'strategy_id', 'unknown')}"
            )
        except Exception:
            pass
        # Persist a snapshot of the active strategy config (idempotent: only writes if missing)
        try:
            from dataclasses import asdict
            sid = getattr(self.prod, "strategy_id", "unknown")
            strat_dir = Path(__file__).parent / "strategies"
            strat_dir.mkdir(parents=True, exist_ok=True)
            snap_path = strat_dir / f"{sid}.json"
            if not snap_path.exists():
                snapshot = {
                    "strategy_id": sid,
                    "created_ts": time.time(),
                    "config": asdict(self.prod),
                    "yaml_cfg_path": str(cfg_path),
                }
                snap_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
                logger.info(f"[STRATEGY] saved snapshot {snap_path}")
            else:
                logger.info(f"[STRATEGY] snapshot exists {snap_path}")
        except Exception as e:
            logger.warning(f"[STRATEGY] failed to save snapshot: {e}")
        self.market = MarketStream(self.ex)
        self.orderbook = OrderbookStream(self.ex)
        self.feature_store = FeatureStore()
        self.regime = RegimeClassifier()
        self.ensemble = HorizonEnsemble(self.prod.horizons)
        self.edge = EdgeEngine()
        self.ev_engine = ExpectedValueEngine(taker_fee=self.cfg.get("taker_fee", 0.0006))
        self.quality_gate = QualityGate(self.prod.min_trade_quality)
        self.sizer = None
        if getattr(self.prod, "sizing_mode", "notional_sizer") != "max_exchange_qty":
            self.sizer = PositionSizer(self.prod.base_notional_usdt)
        self.exit_engine = ExitEngine()
        self.spread_guard = SpreadGuard(self.prod.max_spread_bps)
        self.slip_guard = SlippageGuard()
        self.router = SmartRouter(self.ex, self.prod.limit_timeout_ms, self.prod.requote_attempts)
        self.exec_tracker = ExecutionTracker(self.ex, log_dir="logs")
        # v7: stats collector for signal/trade logging and per-bucket aggregates.
        self.stats = StatsCollector(stats_print_every=20)
        self.cooldown = CooldownManager()
        self.exposure = ExposureLimits(self.prod.max_concurrent_positions, self.prod.max_positions_per_symbol)
        self.heat = PortfolioHeat(self.prod.max_portfolio_heat)
        self.models = {h: DirectionModel() for h in self.prod.horizons}
        # Per-symbol model cache: {symbol: (timestamp, {horizon: trained_model})}
        self._model_cache = {}
        self._model_cache_ttl_sec = 300.0  # retrain every 5 minutes per symbol
        self.meta = MetaLabelModel()
        self.last_scan = 0.0
        self._last_entry_ts_global = 0.0  # global throttle between entries
        # Signal stickiness state: {symbol: {"count": int, "direction": str, "last_conf": float}}
        self._stickiness = {}
        self._ohlcv_cache = {}  # symbol -> (ts, df)
        self.position_states = {}
        self._last_funding_refresh = 0.0
        self._funding_cache = {}
        self._last_cleanup_ts = 0.0
        self._cleanup_interval_sec = 20.0
        self._cancel_cooldown = {}
        self._reconnect_count = 0
        self._dropped_messages = 0
        self._last_heartbeat = time.time()
        self._cycle_errors = 0
        self._state_path = Path("logs/last_state.json")
        self._health_path = Path("logs/health.json")
        self._snapshot_dir = Path("logs/error_snapshots")
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _f(x, default=0.0) -> float:
        try:
            if x is None:
                return default
            return float(x)
        except Exception:
            return default

    def _hydrate_from_exchange_row(self, st: PositionState, p: dict):
        """Pull exchange-reported position metrics into local state (best-effort)."""
        lev = int(float(p.get("leverage", 0) or 0))
        if lev != st.leverage and st.leverage != 0:
            logger.info(f"[EXPOSURE] {st.symbol} leverage_exchange={lev} (was {st.leverage})")
        st.leverage = lev
        st.position_value_exchange = self._f(p.get("positionValue", 0.0))
        unreal = self._f(p.get("unrealisedPnl", p.get("unrealizedPnl", 0.0)))
        sz = Decimal(str(p.get("size", "0") or "0"))
        cum = self._f(p.get("cumRealisedPnl", 0.0)) if p.get("cumRealisedPnl") is not None else st.cum_realised_pnl
        logger.info(
            f"[EXCHANGE POS] {st.symbol} side_ex={p.get('side')} size={sz} avg={p.get('avgPrice')} "
            f"lev={st.leverage}x posVal={st.position_value_exchange:.6f} unreal={unreal:.6f} "
            f"cumRealised={cum:.6f}"
        )

    def _rebuild_brackets_for_state(self, st: PositionState):
        """Recompute TP/SL brackets from current entry + fresh ATR (handles manual size/avg changes)."""
        try:
            df = self._cached_ohlcv(st.symbol, limit=600)
            atr_v = atr(df, 14)
        except Exception:
            atr_v = st.entry_price * 0.004
        sig = {"symbol": st.symbol, "direction": st.side, "entry": st.entry_price, "atr": atr_v}
        levels = self._build_exit_levels(sig)
        st.stop_loss_price = float(levels["sl"])
        st.take_profit_levels = {
            "tp1": float(levels["tp1"]),
            "tp2": float(levels["tp2"]),
            "tp3": float(levels["tp3"]),
        }
        st.trailing_price = float(levels["tp3"])
        st.tp1_done = st.tp2_done = st.tp3_done = False

    def _request_stop(self, signum=None, frame=None):
        self._stop_requested = True
        try:
            logger.warning(f"[HEALTH] stop_requested signal={signum}")
        except Exception:
            pass

    def _cached_ohlcv(self, symbol: str, limit: int = 600):
        now = time.time()
        ts_df = self._ohlcv_cache.get(symbol)
        if ts_df and (now - ts_df[0]) <= self.prod.market_cache_ttl_sec:
            return ts_df[1]
        df = self.market.get_ohlcv(symbol, limit=limit)
        self._ohlcv_cache[symbol] = (now, df)
        return df

    def select_symbols(self):
        tickers = self.market.get_tickers()
        scored = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            vol24 = float(t.get("turnover24h", 0) or 0)
            if vol24 < self.prod.min_volume_24h_usdt:
                continue
            pct = abs(float(t.get("price24hPcnt", 0) or 0))
            h = float(t.get("highPrice24h", 0) or 0)
            l = float(t.get("lowPrice24h", 0) or 0)
            last = float(t.get("lastPrice", 0) or 0)
            if last <= 0:
                continue
            wick_ratio = (h - l) / (last + 1e-12)
            if wick_ratio > self.prod.max_wick_ratio:
                continue
            scored.append(
                {
                    "symbol": sym,
                    "rank_score": pct + wick_ratio,
                    "vol24": vol24,
                    "pct": pct,
                    "last": last,
                    "wick_ratio": wick_ratio,
                }
            )
        scored.sort(key=lambda x: x["rank_score"], reverse=True)
        return scored[: self.prod.scan_top_symbols]

    async def _fetch_ob_batch(self, symbols):
        sem = asyncio.Semaphore(self.prod.max_concurrency)

        async def one(sym):
            async with sem:
                ob = await asyncio.to_thread(self.orderbook.snapshot, sym)
                return sym, ob

        pairs = await asyncio.gather(*(one(s) for s in symbols), return_exceptions=True)
        out = {}
        for p in pairs:
            if isinstance(p, Exception):
                continue
            sym, ob = p
            out[sym] = ob
        return out

    def _tier1_pass(self, c, ob):
        # Fast stage: liquidity/spread/volatility sanity (cheap only).
        sym = c.get("symbol", "?")
        if c["vol24"] < self.prod.min_volume_24h_usdt:
            logger.debug(f"[TIER1_REJECT] {sym} reason=low_vol24 vol24={c['vol24']:.0f}<{self.prod.min_volume_24h_usdt:.0f}")
            return False, 0.0
        depth = float(ob.get("depth_usdt", 0.0))
        spread = float(ob.get("spread_bps", 999.0))
        if c["pct"] < 0.01:
            logger.debug(f"[TIER1_REJECT] {sym} reason=low_pct pct={c['pct']:.4f}<0.01")
            return False, 0.0
        # Relaxed gate: allow lower depth in tier1, spread is soft.
        if depth < self.prod.min_depth_usdt * 0.30:
            logger.info(f"[TIER1_REJECT] {sym} reason=low_depth depth={depth:.0f}<{self.prod.min_depth_usdt * 0.30:.0f} spread={spread:.1f}bps pct={c['pct']:.4f}")
            return False, 0.0
        spread_q = max(0.0, min(1.0, 1.0 - spread / max(self.prod.max_spread_bps * 1.5, 1e-6)))
        depth_q = max(0.0, min(1.0, depth / (self.prod.min_depth_usdt * 2.0)))
        vol_q = max(0.0, min(1.0, c["pct"] / 0.05))
        tier1_score = 0.4 * vol_q + 0.3 * depth_q + 0.3 * spread_q
        return True, tier1_score

    def train_and_predict(self, symbol: str, pre_ob: dict = None):
        df = self._cached_ohlcv(symbol, limit=300)
        if len(df) < 120:
            return None
        ob = pre_ob if pre_ob is not None else self.orderbook.snapshot(symbol)
        funding = self.ex.get_funding_rate(symbol)
        oi = self.ex.get_open_interest(symbol)
        x_row = self.feature_store.build(df, ob, funding=funding, oi_delta=oi)

        # Check per-symbol model cache
        now = time.time()
        cached = self._model_cache.get(symbol)
        use_cache = cached is not None and (now - cached[0]) < self._model_cache_ttl_sec

        if use_cache:
            # Use cached trained models, only predict
            trained_models = cached[1]
            horizon_probs = {h: trained_models[h].predict_proba(x_row) for h in self.prod.horizons}
        else:
            # Online train from historical rows without lookahead in current bar usage.
            feat_rows = []
            for i in range(60, len(df) - max(self.prod.horizons) - 1):
                sub = df.iloc[: i + 1]
                feat_rows.append(self.feature_store.build(sub, ob, funding=funding, oi_delta=oi))
            X = pd.DataFrame(feat_rows).fillna(0.0)
            if len(X) < 80:
                return None

            trained_models = {}
            horizon_probs = {}
            for h in self.prod.horizons:
                y = np.where(
                    (df["close"].shift(-h) / df["close"] - 1).iloc[60 : 60 + len(X)] > 0,
                    1,
                    -1,
                )
                m = copy.deepcopy(self.models[h])
                m.fit(X, y)
                trained_models[h] = m
                horizon_probs[h] = m.predict_proba(x_row)
            self._model_cache[symbol] = (now, trained_models)

        regime = self.regime.classify(df)
        direction, confidence, agreement = self.ensemble.vote(horizon_probs, regime)
        probs = horizon_probs[self.prod.horizons[0]]
        primary_dir, p_primary, unc = self.edge.compute(probs)
        if primary_dir != direction:
            confidence *= 0.8
        # Experimental: invert model direction (long<->short).
        # Justified by negative EV-PnL correlation in v1 (-0.18).
        # Note: confidence/probability values are NOT swapped — only the side of execution.
        if getattr(self.prod, "invert_signals", False):
            original_dir = direction
            direction = "short" if direction == "long" else "long"
            primary_dir = -primary_dir if isinstance(primary_dir, (int, float)) else primary_dir
            logger.debug(f"[INVERT] {symbol} {original_dir} -> {direction} (conf={confidence:.3f})")

        ob_imb = (ob.get("imbalance", 0.0) + 1.0) / 2.0
        spread_q = max(0.0, min(1.0, 1.0 - ob.get("spread_bps", 999.0) / max(self.prod.max_spread_bps, 1e-6)))
        liq_q = max(0.0, min(1.0, ob.get("depth_usdt", 0.0) / (self.prod.min_depth_usdt * 2.0)))
        trend_align = 1.0 if regime == "trend" else 0.7 if regime == "breakout" else 0.4
        vol_q = 0.5 if regime == "panic" else 1.0
        regime_q = {"trend": 1.0, "breakout": 0.8, "chop": 0.5, "panic": 0.3}.get(regime, 0.5)
        score = self.quality_gate.score(confidence, trend_align, liq_q, spread_q, regime_q, vol_q, ob_imb)

        spread_bps = ob.get("spread_bps", 999.0)
        slip = self.slip_guard.estimate(spread_bps, ob.get("depth_usdt", 0.0), self.prod.base_notional_usdt)
        atr_v = atr(df, 14)
        entry = float(df["close"].iloc[-1])
        risk = max(atr_v * self.prod.sl_atr_mult, entry * 0.001)
        avg_win = (self.prod.tp2_r * risk) / entry
        avg_loss = risk / entry
        ev = self.ev_engine.estimate(p_primary, avg_win, avg_loss, slip)
        return {
            "symbol": symbol,
            "df": df,
            "direction": direction,
            "confidence": confidence,
            "agreement": agreement,
            "uncertainty": unc,
            "score": score,
            "regime": regime,
            "spread_bps": spread_bps,
            "depth_usdt": ob.get("depth_usdt", 0.0),
            "ev": ev,
            "entry": entry,
            "atr": atr_v,
        }

    def _is_high_ev_override_candidate(self, sig) -> bool:
        return sig["ev"] >= self.prod.ev_min_decision and sig["confidence"] >= self.prod.conf_min_decision

    def _build_exit_levels(self, sig):
        # Dynamic TP scaling based on signal confidence and EV
        # Base multipliers from config
        base_tp1_r = float(self.prod.tp1_r)
        base_tp2_r = float(self.prod.tp2_r)
        base_tp3_r = float(self.prod.tp3_r)

        if getattr(self.prod, "dynamic_tp_enabled", True):
            conf = float(sig.get("confidence", 0.7))
            ev = float(sig.get("ev", 0.0))
            entry = float(sig["entry"])
            atr_val = float(sig["atr"])
            risk_pct = max(atr_val * self.prod.sl_atr_mult / max(entry, 1e-9), 0.001)

            # Confidence factor: 0.70 → 1.0x, 0.85 → 1.30x, 0.95 → 1.50x (capped at 1.6x)
            conf_factor = 1.0 + max(0.0, (conf - 0.70) * 2.0)
            conf_factor = min(conf_factor, 1.6)

            # EV-based factor: convert expected return to R-multiple
            # ev=0.01 (1%) and risk_pct=0.5% → ev_in_r = 2.0R
            ev_in_r = max(0.0, ev / max(risk_pct, 1e-9))
            # Use 80% of expected R as TP (conservative)
            ev_factor_target_tp1 = ev_in_r * 0.6
            ev_factor_target_tp2 = ev_in_r * 1.0

            # Take max of base * conf_factor and EV-derived target
            tp1_r = max(base_tp1_r * conf_factor, ev_factor_target_tp1)
            tp2_r = max(base_tp2_r * conf_factor, ev_factor_target_tp2)
            tp3_r = max(base_tp3_r * conf_factor, ev_in_r * 1.5)

            # Sanity caps to avoid extreme TPs
            tp1_r = min(tp1_r, 5.0)
            tp2_r = min(tp2_r, 8.0)
            tp3_r = min(tp3_r, 12.0)

            logger.info(
                f"[DYNAMIC_TP] {sig['symbol']} conf={conf:.3f} ev={ev:.4f} risk_pct={risk_pct:.4f} "
                f"ev_in_r={ev_in_r:.2f} conf_factor={conf_factor:.2f} "
                f"tp1_r={tp1_r:.2f} tp2_r={tp2_r:.2f} tp3_r={tp3_r:.2f}"
            )
        else:
            tp1_r = base_tp1_r
            tp2_r = base_tp2_r
            tp3_r = base_tp3_r

        brackets = self.exit_engine.compute_brackets(
            sig["direction"], sig["entry"], sig["atr"], self.prod.sl_atr_mult, tp1_r, tp2_r
        )
        # TP3 scales with ATR (same semantics as tp1_r / tp2_r in the new exit engine).
        atr_unit = max(float(sig["atr"]), float(sig["entry"]) * 0.001)
        if sig["direction"] == "long":
            tp3 = sig["entry"] + tp3_r * atr_unit
        else:
            tp3 = sig["entry"] - tp3_r * atr_unit
        brackets["tp3"] = tp3
        return brackets

    def _create_state(self, sig, qty: Decimal, ex_row: dict = None):
        fees = float(qty * Decimal(str(sig["entry"])) * Decimal(str(self.cfg.get("taker_fee", 0.0006))))
        levels = self._build_exit_levels(sig)
        st = PositionState(
            symbol=sig["symbol"],
            side=sig["direction"],
            entry_price=float(sig["entry"]),
            qty_total=Decimal(str(qty)),
            qty_closed=Decimal("0"),
            entry_fees=fees,
            exit_fees_estimate=fees,
            funding_estimate=0.0,
            stop_loss_price=float(levels["sl"]),
            take_profit_levels={"tp1": float(levels["tp1"]), "tp2": float(levels["tp2"]), "tp3": float(levels["tp3"])},
            exit_state="open",
            trailing_price=float(levels["tp3"]),
            updated_ts=time.time(),
        )
        st.last_exchange_size = Decimal(str(qty))
        st.qty_original = Decimal(str(qty))  # Store original size for TP calculations
        st.opened_ts = time.time()
        st.signal_meta = {
            "confidence": float(sig.get("confidence", 0.0) or 0.0),
            "score": float(sig.get("score", 0.0) or 0.0),
            "ev": float(sig.get("ev", 0.0) or 0.0),
            "regime": sig.get("regime", ""),
            "agreement": int(sig.get("agreement", 0) or 0),
            "uncertainty": float(sig.get("uncertainty", 0.0) or 0.0),
            "spread_bps": float(sig.get("spread_bps", 0.0) or 0.0),
            "depth_usdt": float(sig.get("depth_usdt", 0.0) or 0.0),
            "atr": float(sig.get("atr", 0.0) or 0.0),
            "adx": float(sig.get("adx", 0.0) or 0.0),
            "funding_rate": float(sig.get("funding_rate", 0.0) or 0.0),
            "size_mult": float(sig.get("_size_mult", 1.0) or 1.0),
        }
        if ex_row is not None:
            if ex_row.get("cumRealisedPnl") is not None:
                st.cum_realised_pnl = self._f(ex_row.get("cumRealisedPnl", 0.0))
                st.cum_realised_pnl_entry = st.cum_realised_pnl
            self._hydrate_from_exchange_row(st, ex_row)
        self.position_states[sig["symbol"]] = st
        logger.info(
            f"[STATE CREATE] {sig['symbol']} side={sig['direction']} qty={qty} entry={sig['entry']:.6f} "
            f"lev={st.leverage}x sl={st.stop_loss_price:.6f} tp1={st.take_profit_levels['tp1']:.6f} "
            f"tp2={st.take_profit_levels['tp2']:.6f} tp3={st.take_profit_levels['tp3']:.6f}"
        )

    def _remaining_qty(self, st: PositionState) -> Decimal:
        return max(Decimal("0"), st.qty_total - st.qty_closed)

    def _close_market_reduce_only(self, st: PositionState, qty: Decimal, reason: str):
        if qty <= 0:
            return False
        res = self.ex.market_reduce_only(st.symbol, st.side, qty)
        if int(res.get("retCode", -1)) != 0:
            logger.warning(f"[EXIT FAIL] {st.symbol} reason={reason} ret={res}")
            return False
        st.qty_closed += Decimal(str(qty))
        st.updated_ts = time.time()
        st.exit_state = "partial" if self._remaining_qty(st) > 0 else "closed"
        try:
            st.exit_reasons.append({"reason": reason, "qty": str(qty), "ts": time.time()})
        except Exception:
            pass
        logger.info(f"[EXIT] {st.symbol} reason={reason} qty={qty} remaining={self._remaining_qty(st)}")
        return True

    def _fit_exit_qty(self, st: PositionState, desired_qty: Decimal) -> Decimal:
        """
        Ensure exit qty is exchange-valid.
        If desired qty is too small by step/min rules, try remaining qty.
        """
        rem = self._remaining_qty(st)
        if rem <= 0:
            return Decimal("0")
        q = min(rem, Decimal(str(desired_qty)))
        n = self.ex.normalize_qty(st.symbol, q)
        if n > 0:
            return Decimal(str(n))
        n_rem = self.ex.normalize_qty(st.symbol, rem)
        if n_rem > 0:
            return Decimal(str(n_rem))
        return Decimal("0")

    def _sync_state_from_exchange(self, positions):
        live = {}
        for p in positions:
            sz = Decimal(str(p.get("size", "0") or "0"))
            if sz <= 0:
                continue
            sym = p.get("symbol")
            live[sym] = p
            side = "long" if p.get("side") == "Buy" else "short"
            entry = float(p.get("avgPrice", 0) or 0)
            if sym not in self.position_states:
                sig = {"symbol": sym, "direction": side, "entry": entry, "atr": entry * 0.004}
                self._create_state(sig, sz, ex_row=p)
                self.position_states[sym].exit_state = "open"
            else:
                st = self.position_states[sym]
                prev_sz = st.last_exchange_size
                # Exchange-first reconciliation.
                # If exchange state diverged from local, we DO NOT infer causes; we reset local tracking.
                side_changed = (side != st.side)
                size_changed = (sz != st.qty_total)
                avg_changed = (abs(entry - st.entry_price) > 1e-12)
                if prev_sz > 0 and sz < prev_sz:
                    logger.warning(f"[MANUAL_INTERVENTION_DETECTED] {sym} exchange_size_shrank {prev_sz} -> {sz}")
                if side_changed or size_changed or avg_changed:
                    logger.warning(
                        f"[RECONCILE_TRIGGERED] {sym} side_changed={side_changed} size_changed={size_changed} avg_changed={avg_changed}"
                    )
                    st.side = side
                    # Only update qty_total if side changed (position flipped long<->short)
                    # If only size changed (partial exits), preserve qty_total to prevent re-calculating TP percentages
                    if side_changed:
                        st.qty_total = sz
                        st.qty_original = sz  # Reset original size when position flips
                    st.entry_price = entry
                    self._rebuild_brackets_for_state(st)
                    st.entry_fees = float(sz * Decimal(str(entry)) * Decimal(str(self.cfg.get("taker_fee", 0.0006))))
                    st.exit_fees_estimate = st.entry_fees
                    st.funding_estimate = 0.0
                    st.exit_state = "open"
                    # Only reset TP flags if side changed (position flipped long<->short)
                    # If only size/avg changed, keep TP flags to prevent re-exiting
                    if side_changed:
                        st.tp1_done = st.tp2_done = st.tp3_done = False
                        st.qty_closed = Decimal("0")
                        logger.info(f"[RECONCILE] {sym} side_changed - TP flags reset")
                    logger.info(f"[RECONCILE] {sym} reconciled_to_exchange size={sz} avg={entry} side={side}")
                st.last_exchange_size = sz
                if p.get("cumRealisedPnl") is not None:
                    cum_now = self._f(p.get("cumRealisedPnl", 0.0))
                    if cum_now != st.cum_realised_pnl:
                        d = cum_now - st.cum_realised_pnl
                        logger.info(f"[PNL] {sym} cumRealisedPnl_delta={d:.6f} cum={cum_now:.6f} (exchange/sync)")
                        st.cum_realised_pnl = cum_now
                self._hydrate_from_exchange_row(st, p)
                st.updated_ts = time.time()

        for sym, st in list(self.position_states.items()):
            if sym not in live:
                st.exit_state = "closed"
                logger.info(f"[STATE CLOSED] {sym} total={st.qty_total} closed={st.qty_closed}")
                try:
                    self._record_closed_trade(st)
                except Exception as e:
                    logger.warning(f"[TRADE RECORDER] {sym} failed: {e}")
                del self.position_states[sym]

    def _record_closed_trade(self, st: PositionState):
        """Append one JSON line per closed trade to logs/trades.jsonl for post-trade analysis."""
        now = time.time()
        try:
            # Realized net PnL from exchange (cumRealisedPnl delta since entry).
            realized_net = float(st.cum_realised_pnl) - float(st.cum_realised_pnl_entry)
        except Exception:
            realized_net = 0.0
        # Fallback: if entry PnL was not captured at open, schedule async closed-pnl fetch.
        if st.cum_realised_pnl_entry == 0.0:
            threading.Thread(
                target=self._fetch_closed_pnl_async,
                args=(st.symbol, st.opened_ts),
                daemon=True,
            ).start()
        # Weighted avg exit price by qty from recorded exit reasons.
        avg_exit = 0.0
        total_qty = 0.0
        reason_counts = {}
        for er in (st.exit_reasons or []):
            try:
                q = float(er.get("qty", 0) or 0)
                reason_counts[er.get("reason", "unknown")] = reason_counts.get(er.get("reason", "unknown"), 0.0) + q
                total_qty += q
            except Exception:
                continue
        # We don't have per-exit price here reliably (market closes with slippage) – leave 0 if unknown.
        duration = max(0.0, now - float(st.opened_ts or now))
        record = {
            "schema": "selective_trade_v1",
            "strategy_id": getattr(self.prod, "strategy_id", "unknown"),
            "trade_id": f"{st.symbol}_{int(st.opened_ts or now)}",
            "symbol": st.symbol,
            "direction": st.side,
            "opened_ts": float(st.opened_ts or 0.0),
            "closed_ts": now,
            "duration_sec": duration,
            "entry_price": float(st.entry_price),
            "qty_total": str(st.qty_total),
            "qty_closed": str(st.qty_closed),
            "leverage": int(st.leverage or 0),
            "stop_loss_price": float(st.stop_loss_price),
            "take_profit_levels": dict(st.take_profit_levels or {}),
            "signal": dict(st.signal_meta or {}),
            "exit_reasons": list(st.exit_reasons or []),
            "exit_reason_qty_sum": reason_counts,
            "cum_realised_pnl_entry": float(st.cum_realised_pnl_entry),
            "cum_realised_pnl_close": float(st.cum_realised_pnl),
            "realized_pnl_net": float(realized_net),
            "entry_fees_est": float(st.entry_fees),
            "exit_fees_est": float(st.exit_fees_estimate),
            "funding_estimate": float(st.funding_estimate),
            "notional_entry": float(st.entry_price) * float(st.qty_total or 0),
        }
        try:
            # Absolute path to ensure consistent location
            trade_log_path = Path(__file__).parent / "logs" / "trades.jsonl"
            trade_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(trade_log_path, "a", encoding="utf-8") as w:
                w.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            logger.info(
                f"[TRADE RECORDED] {st.symbol} dir={st.side} realized_pnl_net={realized_net:.2f} "
                f"duration={int(duration)}s regime={record['signal'].get('regime','')} "
                f"conf={record['signal'].get('confidence',0):.3f} score={record['signal'].get('score',0):.3f} "
                f"ev={record['signal'].get('ev',0):.5f}"
            )
        except Exception as e:
            logger.warning(f"[TRADE RECORDER] write failed {st.symbol}: {e}")
        # v7: update stats collector (CSV + aggregates). Best-effort — never break close flow.
        try:
            exit_reasons_list = list(st.exit_reasons or [])
            exit_reason_label = exit_reasons_list[-1].get("reason", "") if exit_reasons_list else ""
            self.stats.log_trade_close(
                record=record,
                realized_pnl_net=float(realized_net),
                exit_reason=str(exit_reason_label),
                exit_price=0.0,
            )
        except Exception as _e_stats:
            logger.debug(f"[STATS] log_trade_close wrap failed: {_e_stats}")

    def _fetch_closed_pnl_async(self, symbol: str, opened_ts: float):
        """Fetch closed PnL from exchange after a delay and patch trades.jsonl."""
        time.sleep(5)  # Wait for Bybit to settle closed-pnl data
        try:
            resp = self.ex._request(
                "GET",
                "/v5/position/closed-pnl",
                {"category": "linear", "symbol": symbol, "limit": "1"},
                auth=True,
            )
            if resp.get("retCode") == 0:
                items = resp.get("result", {}).get("list", [])
                if items:
                    closed_pnl = float(items[0].get("closedPnl", 0))
                    self._update_trade_pnl(symbol, opened_ts, closed_pnl)
                    logger.info(f"[CLOSED_PNL] {symbol} patched realized_pnl_net={closed_pnl:.2f}")
        except Exception as e:
            logger.debug(f"[CLOSED_PNL] fallback failed {symbol}: {e}")

    def _update_trade_pnl(self, symbol: str, opened_ts: float, corrected_pnl: float):
        """Update realized_pnl_net in trades.jsonl for a closed trade."""
        try:
            trade_log_path = Path(__file__).parent / "logs" / "trades.jsonl"
            if not trade_log_path.exists():
                return
            lines = []
            updated = False
            with open(trade_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line.strip())
                    if (
                        rec.get("symbol") == symbol
                        and abs(rec.get("opened_ts", 0) - opened_ts) < 1
                        and rec.get("schema") == "selective_trade_v1"
                    ):
                        rec["realized_pnl_net"] = corrected_pnl
                        rec["_patched_by"] = "closed_pnl_fallback"
                        updated = True
                    lines.append(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            if updated:
                with open(trade_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                logger.info(f"[TRADE PATCHED] {symbol} realized_pnl_net={corrected_pnl:.2f}")
        except Exception as e:
            logger.warning(f"[TRADE PATCH] {symbol} failed: {e}")

    def _save_state(self):
        payload = {
            "timestamp": time.time(),
            "positions": {
                sym: {
                    "side": st.side,
                    "entry_price": st.entry_price,
                    "qty_total": str(st.qty_total),
                    "qty_closed": str(st.qty_closed),
                    "stop_loss_price": st.stop_loss_price,
                    "take_profit_levels": st.take_profit_levels,
                    "exit_state": st.exit_state,
                    "tp1_done": st.tp1_done,
                    "tp2_done": st.tp2_done,
                    "tp3_done": st.tp3_done,
                    "trailing_price": st.trailing_price,
                }
                for sym, st in self.position_states.items()
            },
        }
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._state_path)

    def _write_health(self, cycle_ms: int, signals_generated: int, executed_orders: int, equity: float):
        ram_mb = cpu_pct = connections = None
        if psutil:
            p = psutil.Process()
            ram_mb = round(p.memory_info().rss / (1024 * 1024), 2)
            cpu_pct = p.cpu_percent(interval=0.0)
            try:
                connections = len(p.connections(kind="inet"))
            except Exception:
                connections = None
        health = {
            "timestamp": time.time(),
            "heartbeat_age_sec": round(time.time() - self._last_heartbeat, 3),
            "cycle_ms": cycle_ms,
            "signals_generated": signals_generated,
            "executed_orders": executed_orders,
            "active_positions": len(self.position_states),
            "equity": equity,
            "reconnect_count": self._reconnect_count,
            "dropped_messages": self._dropped_messages,
            "ram_mb": ram_mb,
            "cpu_pct": cpu_pct,
            "open_connections": connections,
            "event_loop_lag_ms": max(0.0, (time.time() - self._last_heartbeat - self.prod.position_loop_interval_sec) * 1000.0),
        }
        self._health_path.write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot_error(self, reason: str, exc: Exception):
        ts = int(time.time() * 1000)
        payload = {
            "ts": ts,
            "reason": reason,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "positions": list(self.position_states.keys()),
        }
        p = self._snapshot_dir / f"snapshot_{ts}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.error(f"[RISK] snapshot_saved path={p}")
        self._send_alert(f"selective_ml_bot crash snapshot: {reason}: {exc}")

    def _send_alert(self, text: str):
        tg_token = os.getenv("TG_BOT_TOKEN")
        tg_chat = os.getenv("TG_CHAT_ID")
        discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
        try:
            if tg_token and tg_chat:
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": text[:3500]},
                    timeout=5,
                )
            if discord_webhook:
                requests.post(discord_webhook, json={"content": text[:1900]}, timeout=5)
        except Exception as e:
            logger.warning(f"[ALERT] failed: {e}")

    def _cleanup_entry_orders(self):
        now = time.time()
        if now - self._last_cleanup_ts < self._cleanup_interval_sec:
            return
        self._last_cleanup_ts = now

        for sym, st in list(self.position_states.items()):
            try:
                orders = self.ex.get_open_orders(sym).get("result", {}).get("list", [])
            except Exception as e:
                logger.warning(f"[SYNC] open_orders failed {sym}: {e}")
                continue
            canceled_this_symbol = 0
            for o in orders:
                if o.get("reduceOnly"):
                    continue
                status = str(o.get("orderStatus", ""))
                if status and status not in {"New", "PartiallyFilled", "Untriggered"}:
                    continue
                oid = o.get("orderId")
                if oid:
                    if now - self._cancel_cooldown.get(oid, 0.0) < 120.0:
                        continue
                    try:
                        self.ex.cancel_order(sym, oid)
                        logger.info(f"[SYNC] canceled non-reduce order symbol={sym} orderId={oid}")
                        self._cancel_cooldown[oid] = now
                        canceled_this_symbol += 1
                        if canceled_this_symbol >= 3:
                            break
                    except Exception as e:
                        msg = str(e)
                        self._cancel_cooldown[oid] = now
                        if "110001" in msg:
                            logger.debug(f"[SYNC] cancel stale/filled symbol={sym} orderId={oid}")
                        else:
                            logger.warning(f"[SYNC] cancel failed symbol={sym} orderId={oid}: {e}")

    def _refresh_funding_cache(self):
        now = time.time()
        if now - self._last_funding_refresh < self.prod.funding_refresh_sec:
            return
        self._last_funding_refresh = now
        for sym in self.position_states.keys():
            try:
                self._funding_cache[sym] = float(self.ex.get_funding_rate(sym))
            except Exception:
                self._funding_cache[sym] = 0.0

    def _monitor_positions(self):
        self._refresh_funding_cache()
        for sym, st in list(self.position_states.items()):
            try:
                # Poll fills to keep execution accounting up to date.
                try:
                    fills = self.exec_tracker.poll_symbol(sym, limit=100)
                    for f in fills:
                        logger.info(
                            f"[FILL] {f.symbol} side={f.side} qty={f.qty} price={f.price} fee={f.fee} "
                            f"fee_ccy={f.fee_currency} maker={f.is_maker} ts_ms={f.ts_ms} exec_id={f.exec_id}"
                        )
                except Exception as e:
                    logger.warning(f"[FILL POLL FAIL] {sym} err={e}")

                rem = self._remaining_qty(st)
                if rem <= 0:
                    st.exit_state = "closed"
                    continue
                try:
                    tk = self.ex.fetch_ticker_symbol(sym)
                    price = float(tk.get("lastPrice", 0) or 0)
                except Exception as e:
                    logger.warning(f"[MONITOR] ticker failed {sym}: {e}")
                    continue
                if price <= 0:
                    continue

                ex_row = None
                try:
                    pr = self.ex.get_positions(sym)
                    if int(pr.get("retCode", -1)) == 0:
                        for row in pr.get("result", {}).get("list", []):
                            if row.get("symbol") == sym and float(row.get("size", 0) or 0) > 0:
                                ex_row = row
                                break
                except Exception as e:
                    logger.debug(f"[MONITOR] get_positions failed {sym}: {e}")

                unreal_ex = None
                if ex_row:
                    unreal_ex = self._f(ex_row.get("unrealisedPnl", ex_row.get("unrealizedPnl", 0.0)))
                    if ex_row.get("cumRealisedPnl") is not None:
                        cum_now = self._f(ex_row.get("cumRealisedPnl", 0.0))
                        if cum_now != st.cum_realised_pnl:
                            d = cum_now - st.cum_realised_pnl
                            logger.info(
                                f"[PNL] {sym} cumRealisedPnl_delta={d:.6f} cum={cum_now:.6f} (exchange)"
                            )
                            st.cum_realised_pnl = cum_now
                    self._hydrate_from_exchange_row(st, ex_row)

                notional = float(rem) * price
                # Funding rate is an interval-based charge, not per-monitor-tick.
                # Do not accumulate it every loop; keep an estimated funding cost snapshot.
                st.funding_estimate = abs(notional) * abs(self._funding_cache.get(sym, 0.0))
                taker = float(self.cfg.get("taker_fee", 0.0006))
                maker = float(self.cfg.get("maker_fee", taker))
                # Entries are market (taker); reduce-only exits in this bot are market IOC (taker).
                st.exit_fees_estimate = abs(notional) * taker
                unreal_math = (price - st.entry_price) * float(rem) if st.side == "long" else (st.entry_price - price) * float(rem)
                unreal = unreal_ex if unreal_ex is not None else unreal_math
                net_unreal_model = unreal_math - st.entry_fees - st.exit_fees_estimate - st.funding_estimate
                net_unreal_ex = unreal - st.entry_fees - st.exit_fees_estimate - st.funding_estimate if unreal_ex is not None else net_unreal_model

                try:
                    m = self.exec_tracker.get_symbol_metrics(sym)
                    snap = build_net_expectancy(
                        symbol=sym,
                        unrealized_pnl_exchange=unreal_ex,
                        cum_realized_pnl_exchange=st.cum_realised_pnl,
                        fees_total_execution=m["fees_total"],
                        realized_pnl_execution=m["realized_pnl"],
                        slippage_estimate=0.0,
                    )
                    logger.info(
                        f"[EXPECTANCY] {sym} net_expectancy={snap.net_expectancy:.6f} "
                        f"realized_exec={snap.realized_pnl_execution:.6f} fees_exec={snap.fees_total_execution:.6f} "
                        f"unreal_ex={(snap.unrealized_pnl_exchange if snap.unrealized_pnl_exchange is not None else 0.0):.6f}"
                    )
                except Exception as e:
                    logger.debug(f"[EXPECTANCY] failed {sym}: {e}")

                sl_hit = price <= st.stop_loss_price if st.side == "long" else price >= st.stop_loss_price
                if sl_hit:
                    if self._close_market_reduce_only(st, rem, "stop_loss"):
                        st.exit_state = "closed"
                    continue

                tp1 = st.take_profit_levels["tp1"]
                tp2 = st.take_profit_levels["tp2"]
                tp3 = st.take_profit_levels["tp3"]
                tp1_hit = price >= tp1 if st.side == "long" else price <= tp1
                tp2_hit = price >= tp2 if st.side == "long" else price <= tp2
                tp3_hit = price >= tp3 if st.side == "long" else price <= tp3

                # Single-TP full-close mode (v3 clean mirror):
                # Close 100% of position on TP1 hit, skip TP2/TP3/trailing.
                single_tp_full = bool(getattr(self.prod, "single_tp_full_close", False))
                if single_tp_full:
                    if tp1_hit and not st.tp1_done:
                        q = self._fit_exit_qty(st, self._remaining_qty(st))
                        if self._close_market_reduce_only(st, q, "tp1_full"):
                            st.tp1_done = True
                            st.tp2_done = True  # prevent later partial logic
                            st.tp3_done = True
                            st.exit_state = "closed"
                            continue
                else:
                    if tp1_hit and not st.tp1_done:
                        q = self._fit_exit_qty(st, st.qty_original * Decimal("0.50"))
                        if self._close_market_reduce_only(st, q, "tp1"):
                            st.tp1_done = True
                    if tp2_hit and not st.tp2_done:
                        q = self._fit_exit_qty(st, st.qty_original * Decimal("0.25"))
                        if self._close_market_reduce_only(st, q, "tp2"):
                            st.tp2_done = True

                rem = self._remaining_qty(st)
                if rem <= 0:
                    st.exit_state = "closed"
                    continue

                if tp3_hit:
                    if st.side == "long":
                        st.trailing_price = max(st.trailing_price, price - st.entry_price * 0.002)
                        trail_hit = price <= st.trailing_price
                    else:
                        st.trailing_price = min(st.trailing_price, price + st.entry_price * 0.002)
                        trail_hit = price >= st.trailing_price
                    if trail_hit:
                        q = self._fit_exit_qty(st, rem)
                        if self._close_market_reduce_only(st, q, "trailing_exit"):
                            st.tp3_done = True

                unreal_ex_s = "na" if unreal_ex is None else f"{unreal_ex:.6f}"
                logger.info(
                    f"[POSITION] {sym} side={st.side} lev={st.leverage}x price={price:.6f} rem={self._remaining_qty(st)} "
                    f"unreal_ex={unreal_ex_s} "
                    f"net_unreal_ex={net_unreal_ex:.6f} net_unreal_model={net_unreal_model:.6f} "
                    f"fees_in={st.entry_fees:.6f} fees_out_est={st.exit_fees_estimate:.6f} fund_est={st.funding_estimate:.6f} "
                    f"taker_fee={taker} maker_fee_cfg={maker} state={st.exit_state}"
                )
            except Exception as e:
                logger.error(f"[MONITOR] exception symbol={sym} err={e}\n{traceback.format_exc()}")
                continue

    def allowed(self, sig, open_positions, equity, used_notional):
        override = self._is_high_ev_override_candidate(sig)
        if not self.cooldown.allow(sig["symbol"]):
            return False, "cooldown", 1.0
        if not self.exposure.allow(open_positions, sig["symbol"]):
            return False, "exposure", 1.0
        # Correlation filter: block stacking same-direction positions across symbols
        if getattr(self.prod, "block_same_direction_stack", False):
            new_dir = sig.get("direction", "")
            for p in open_positions:
                try:
                    if float(p.get("size", 0) or 0) <= 0:
                        continue
                    p_sym = p.get("symbol", "")
                    if p_sym == sig["symbol"]:
                        continue  # same symbol covered by exposure
                    p_side = "long" if p.get("side") == "Buy" else "short"
                    if p_side == new_dir:
                        return False, f"correlation_stack(existing={p_sym}_{p_side})", 1.0
                except Exception:
                    continue
        if getattr(self.prod, "enable_risk_engine", True):
            sym_val = 0.0
            tot_val = 0.0
            for p in open_positions:
                try:
                    if float(p.get("size", 0) or 0) <= 0:
                        continue
                    v = float(p.get("positionValue", 0) or 0)
                    tot_val += v
                    if p.get("symbol") == sig["symbol"]:
                        sym_val += v
                except Exception:
                    continue
            if sym_val >= float(getattr(self.prod, "max_exposure_per_symbol_usdt", 250000.0)):
                return False, "risk_symbol_exposure", 1.0
            if tot_val >= float(getattr(self.prod, "max_total_exposure_usdt", 1000000.0)):
                return False, "risk_total_exposure", 1.0
        if sig["agreement"] < 2:
            return False, f"horizon_disagree(agreement={sig['agreement']}<2)", 1.0
        regime_thr = self.prod.regime_thresholds.get(sig["regime"], self.prod.prob_threshold_base)
        regime_allowed = sig["confidence"] >= regime_thr
        if (not regime_allowed) and (not override):
            return False, f"low_conf(conf={sig['confidence']:.3f}<thr={regime_thr:.2f}@{sig['regime']})", 1.0
        if sig["uncertainty"] < self.prod.uncertainty_filter:
            return False, f"uncertain(unc={sig['uncertainty']:.3f}<{self.prod.uncertainty_filter:.2f})", 1.0
        # Adaptive quality gate per regime (falls back to global min_trade_quality).
        regime_quality_thr = getattr(self.prod, "regime_quality_thresholds", {}).get(
            sig["regime"], self.prod.min_trade_quality
        )
        if sig["score"] < regime_quality_thr:
            return False, f"quality(score={sig['score']:.3f}<thr={regime_quality_thr:.2f}@{sig['regime']})", 1.0
        if sig["ev"] < self.prod.min_ev:
            return False, f"ev(ev={sig['ev']:.5f}<{self.prod.min_ev:.4f})", 1.0

        # Spread/depth are now soft penalties, not hard rejects.
        spread_ok = self.spread_guard.allow(sig["spread_bps"])
        depth_ok = sig["depth_usdt"] >= self.prod.min_depth_usdt
        
        # ADX filter for trend confirmation
        min_adx = getattr(self.prod, "min_adx", 0.0)
        if min_adx > 0:
            adx = self._calculate_adx(sig["symbol"])
            if adx < min_adx:
                return False, f"adx(adx={adx:.2f}<thr={min_adx})", 1.0
            logger.info(f"[ADX] {sig['symbol']} ADX={adx:.2f} (threshold={min_adx})")
        
        size_mult = 1.0
        if not spread_ok:
            ratio = self.prod.max_spread_bps / max(sig["spread_bps"], 1e-9)
            spread_mult = max(self.prod.spread_penalty_floor, min(self.prod.spread_penalty_cap, ratio))
            size_mult *= spread_mult
        if not depth_ok:
            ratio = sig["depth_usdt"] / max(self.prod.min_depth_usdt, 1e-9)
            depth_mult = max(self.prod.depth_penalty_floor, min(self.prod.depth_penalty_cap, ratio))
            size_mult *= depth_mult
        # Funding rate penalty: if funding works against direction, reduce size
        funding_thr = float(getattr(self.prod, "funding_penalty_threshold", 0.0005))
        funding_mult = float(getattr(self.prod, "funding_penalty_mult", 0.5))
        if funding_thr > 0:
            try:
                funding_rate = float(self._funding_cache.get(sig["symbol"]) or self.ex.get_funding_rate(sig["symbol"]) or 0.0)
            except Exception:
                funding_rate = 0.0
            # For long: positive funding means longs pay shorts (bad for long)
            # For short: negative funding means shorts pay longs (bad for short)
            unfavorable = (sig["direction"] == "long" and funding_rate > funding_thr) or \
                          (sig["direction"] == "short" and funding_rate < -funding_thr)
            if unfavorable:
                logger.info(f"[FUNDING PENALTY] {sig['symbol']} dir={sig['direction']} funding={funding_rate:.5f} mult={funding_mult}")
                size_mult *= funding_mult

        # Risk-based sizing limits disabled in "max_exchange_qty" mode.
        if getattr(self.prod, "sizing_mode", "notional_sizer") != "max_exchange_qty":
            notional = self.sizer.size_notional(sig["confidence"], sig["atr"] / (sig["entry"] + 1e-12), 0.5, 1.0) * size_mult
            if not self.heat.can_open(used_notional, equity, notional):
                return False, "heat", 1.0
        if override and (not spread_ok or not depth_ok):
            return True, "override_high_ev", size_mult
        return True, "ok", 1.0

    def _ensure_leverage_1x(self, symbol: str):
        """Safeguard: ensure leverage is set to 1x before opening position."""
        if not getattr(self.prod, "force_leverage_1x", False):
            return True
        try:
            # Get current position info to check leverage
            positions = self.ex.get_positions(symbol)
            if positions and positions.get("result", {}).get("list"):
                pos = positions["result"]["list"][0]
                current_lev = int(float(pos.get("leverage", 1)))
                if current_lev != 1:
                    logger.warning(f"[LEVERAGE SAFEGUARD] {symbol} current leverage={current_lev}x, setting to 1x")
                    self.ex.set_leverage(1, symbol)
                    logger.info(f"[LEVERAGE SAFEGUARD] {symbol} leverage set to 1x")
            else:
                # No position exists, set leverage proactively
                self.ex.set_leverage(1, symbol)
                logger.info(f"[LEVERAGE SAFEGUARD] {symbol} leverage set to 1x (proactive)")
            return True
        except Exception as e:
            logger.error(f"[LEVERAGE SAFEGUARD] Failed to set leverage for {symbol}: {e}")
            return False

    def _calculate_adx(self, symbol: str) -> float:
        """Calculate ADX(14) for trend confirmation using cached OHLCV data."""
        try:
            df = self._cached_ohlcv(symbol, limit=50)
            if df is None or len(df) < 15:
                return 0.0
            # Use last 15 candles for ADX(14) calculation
            df = df.tail(15)
            # Simple ADX calculation (14-period)
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            
            tr = np.zeros(len(high))
            plus_dm = np.zeros(len(high))
            minus_dm = np.zeros(len(high))
            
            for i in range(1, len(high)):
                tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
                up = high[i] - high[i-1]
                down = low[i-1] - low[i]
                plus_dm[i] = up if up > down and up > 0 else 0
                minus_dm[i] = down if down > up and down > 0 else 0
            
            atr = np.mean(tr)
            plus_di = 100 * np.mean(plus_dm) / atr if atr > 0 else 0
            minus_di = 100 * np.mean(minus_dm) / atr if atr > 0 else 0
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            adx = np.mean(dx)
            
            return adx
        except Exception as e:
            logger.error(f"[ADX] Failed to calculate ADX for {symbol}: {e}")
            return 0.0

    def _entry_qty(self, sig, size_mult: float, equity: float = None):
        """
        Compute entry quantity.
        - max_exchange_qty: use Bybit lotSizeFilter.maxMktOrderQty (floored to step via normalize_qty in router)
        - notional_sizer: legacy PositionSizer path
        - risk_based: risk-based sizing using risk_per_trade % of equity
        """
        mode = getattr(self.prod, "sizing_mode", "notional_sizer")

        # v7: fixed notional sizing — every trade has the same USDT exposure.
        if mode == "fixed_notional":
            fixed_notional = float(getattr(self.prod, "base_notional_usdt", 10000.0) or 10000.0)
            entry_px = float(sig.get("entry", 0) or 0)
            if entry_px <= 0:
                logger.warning(f"[SIZING FIXED] {sig['symbol']} invalid entry_px={entry_px}")
                return Decimal("0")
            qty = Decimal(str(fixed_notional / entry_px))
            # Respect hard cap (should equal base_notional in v7 but stay safe).
            cap_usd = float(getattr(self.prod, "max_position_notional_usdt", 0.0) or 0.0)
            if cap_usd > 0:
                q_cap = Decimal(str(cap_usd / entry_px))
                if qty > q_cap:
                    qty = q_cap
            logger.info(
                f"[SIZING FIXED] {sig['symbol']} fixed_notional={fixed_notional:.2f} entry={entry_px} "
                f"qty={qty} notional={float(qty) * entry_px:.2f}"
            )
            return qty

        # Risk-based sizing implementation
        if mode == "risk_based":
            risk_per_trade = getattr(self.prod, "risk_per_trade", 0.003)  # 0.3% default
            if equity is None:
                equity = float(self.ex.get_wallet_balance().get("result", {}).get("totalWalletBalance", 0) or 0)
            
            atr = sig.get("atr", 0)
            entry_price = sig.get("entry", 0)
            stop_distance = atr * self.prod.sl_atr_mult
            
            if stop_distance > 0 and entry_price > 0:
                # Position size = (equity * risk_per_trade) / stop_distance
                risk_amount = equity * risk_per_trade
                qty = Decimal(str(risk_amount / stop_distance))
                
                # Apply size_mult
                qty = qty * Decimal(str(size_mult))
                
                # Hard cap by max_position_notional_usdt
                cap_usd = float(getattr(self.prod, "max_position_notional_usdt", 0.0) or 0.0)
                if cap_usd > 0:
                    q_cap = Decimal(str(cap_usd / entry_price))
                    if qty > q_cap:
                        qty = q_cap
                
                logger.info(
                    f"[SIZING RISK_BASED] {sig['symbol']} equity={equity:.2f} risk_per_trade={risk_per_trade:.1%} "
                    f"risk_amount={risk_amount:.2f} stop_distance={stop_distance:.6f} "
                    f"qty={qty} notional={float(qty) * entry_price:.2f}"
                )
                return qty
            else:
                logger.warning(f"[SIZING RISK_BASED] Invalid ATR or entry price for {sig['symbol']}")
                return Decimal("0")
        
        if mode == "max_exchange_qty":
            rules = self.ex._get_symbol_rules(sig["symbol"])
            # Some exchange wrappers expose only max_qty (no max_mkt_qty).
            max_qty = rules.get("max_mkt_qty", None)
            if max_qty is None:
                max_qty = rules.get("max_qty", None)
            if max_qty is None:
                return Decimal("0")
            # Apply soft liquidity penalties, but never exceed exchange max.
            q = Decimal(str(max_qty)) * Decimal(str(size_mult))
            if q > Decimal(str(max_qty)):
                q = Decimal(str(max_qty))
            # Hard cap by max_position_notional_usdt (production safety).
            cap_usd = float(getattr(self.prod, "max_position_notional_usdt", 0.0) or 0.0)
            q_before_cap = q
            if cap_usd > 0:
                entry_px = float(sig.get("entry", 0) or 0)
                if entry_px > 0:
                    q_cap = Decimal(str(cap_usd / entry_px))
                    if q > q_cap:
                        q = q_cap
            logger.info(
                f"[SIZING] {sig['symbol']} mode=max_exchange_qty max_qty={max_qty} "
                f"size_mult={size_mult} q_before_cap={q_before_cap} "
                f"entry_px={sig.get('entry')} cap_usd={cap_usd} q_final={q}"
            )
            return q

        if self.sizer is None:
            return Decimal("0")
        notional = self.sizer.size_notional(sig["confidence"], sig["atr"] / (sig["entry"] + 1e-12), 0.5, 1.0) * size_mult
        return Decimal(str(notional / max(sig["entry"], 1e-12)))

    async def run(self):
        try:
            signal.signal(signal.SIGTERM, self._request_stop)
            signal.signal(signal.SIGINT, self._request_stop)
        except Exception:
            # Signal handling may be unavailable on some platforms/loops.
            pass
        while True:
            if self._stop_requested:
                try:
                    self._save_state()
                except Exception:
                    pass
                logger.warning("[HEALTH] graceful_shutdown")
                return
            cycle_started = time.time()
            signals_generated = 0
            executed_orders = 0
            equity = 0.0
            try:
                try:
                    positions_resp = self.ex.get_positions()
                    if int(positions_resp.get("retCode", -1)) != 0:
                        raise RuntimeError(f"get_positions ret={positions_resp}")
                    positions = positions_resp.get("result", {}).get("list", [])
                except Exception as e:
                    logger.warning(f"[LOOP] get_positions failed: {e}")
                    self._reconnect_count += 1
                    positions = []

                self._sync_state_from_exchange(positions)
                self._cleanup_entry_orders()
                self._monitor_positions()

                now = time.time()
                if now - self.last_scan < 60:
                    self._last_heartbeat = time.time()
                    await asyncio.sleep(self.prod.position_loop_interval_sec)
                    continue
                self.last_scan = now

                candidates = self.select_symbols()
                logger.info(f"[SELECT] symbols={len(candidates)}")
                candidate_symbols = [c["symbol"] for c in candidates]
                ob_map = await self._fetch_ob_batch(candidate_symbols)
                signals_after_tier1 = 0
                signals_allowed = 0
                override_count = 0

                tier1_passed = []
                for c in candidates:
                    ob = ob_map.get(c["symbol"], {"spread_bps": 999.0, "depth_usdt": 0.0, "imbalance": 0.0})
                    ok, tscore = self._tier1_pass(c, ob)
                    if ok:
                        cc = dict(c)
                        cc["tier1_score"] = tscore
                        tier1_passed.append(cc)
                tier1_passed.sort(key=lambda x: x["tier1_score"], reverse=True)
                symbols = [x["symbol"] for x in tier1_passed[: self.prod.deep_eval_top_n]]
                # Force-include open positions in evaluation for reversal exit logic
                open_position_syms = list(self.position_states.keys())
                for op_sym in open_position_syms:
                    if op_sym not in symbols:
                        symbols.append(op_sym)
                        # Also need orderbook for it
                        if op_sym not in ob_map:
                            try:
                                ob_map[op_sym] = self.orderbook.snapshot(op_sym)
                            except Exception:
                                ob_map[op_sym] = {"spread_bps": 999.0, "depth_usdt": 0.0, "imbalance": 0.0}
                signals_after_tier1 = len(symbols)

                try:
                    bal = self.ex.get_wallet_balance()
                    if int(bal.get("retCode", -1)) == 0:
                        equity = float(bal.get("result", {}).get("list", [{}])[0].get("totalEquity", 0) or 0)
                except Exception:
                    equity = 0.0
                used = sum(float(p.get("positionValue", 0) or 0) for p in positions if float(p.get("size", 0) or 0) > 0)

                sem = asyncio.Semaphore(self.prod.max_concurrency)

                async def eval_one(sym):
                    async with sem:
                        return await asyncio.to_thread(self.train_and_predict, sym, ob_map.get(sym))

                sigs = await asyncio.gather(*(eval_one(sym) for sym in symbols), return_exceptions=True)
                evaluated = []
                for s in sigs:
                    if isinstance(s, Exception) or (s is None):
                        self._dropped_messages += 1
                        continue
                    evaluated.append(s)
                signals_generated = len(evaluated)

                # --- Signal Reversal Exit ---
                # Close position early if ML model predicts strong reversal
                reversal_conf_threshold = getattr(self.prod, "reversal_conf_threshold", 0.70)
                reversal_exit_count = 0
                for sig in evaluated:
                    sym = sig["symbol"]
                    st = self.position_states.get(sym)
                    if st is None or st.exit_state != "open":
                        continue
                    rem = self._remaining_qty(st)
                    if rem <= 0:
                        continue
                    # Check for opposite direction with high confidence
                    sig_dir = sig.get("direction", "")
                    sig_conf = float(sig.get("confidence", 0.0) or 0.0)
                    is_reversal = (st.side == "long" and sig_dir == "short") or \
                                  (st.side == "short" and sig_dir == "long")
                    if is_reversal and sig_conf >= reversal_conf_threshold:
                        logger.warning(
                            f"[REVERSAL EXIT] {sym} position_side={st.side} "
                            f"new_signal={sig_dir} conf={sig_conf:.3f}>={reversal_conf_threshold:.2f} "
                            f"ev={sig.get('ev', 0):.4f} regime={sig.get('regime', '?')}"
                        )
                        if self._close_market_reduce_only(st, rem, "signal_reversal"):
                            st.exit_state = "closed"
                            reversal_exit_count += 1
                if reversal_exit_count > 0:
                    logger.info(f"[REVERSAL EXIT] Closed {reversal_exit_count} positions due to signal reversal")

                # Per-cycle and global throttles for new entries.
                max_new_per_cycle = int(getattr(self.prod, "max_new_positions_per_cycle", 999))
                min_gap_sec = float(getattr(self.prod, "min_minutes_between_entries_global", 0)) * 60.0
                stickiness_required = int(getattr(self.prod, "stickiness_required_cycles", 1))
                stickiness_drop_thr = float(getattr(self.prod, "stickiness_conf_drop_threshold", 0.15))
                # Track which symbols had a signal this cycle so we can decay stickiness elsewhere.
                seen_symbols_this_cycle = set()
                for sig in evaluated:
                    try:
                        sym = sig["symbol"]
                        seen_symbols_this_cycle.add(sym)
                        ok, reason, size_mult = self.allowed(sig, positions, equity, used)
                        logger.info(
                            f"[SIGNAL] {sym} dir={sig['direction']} conf={sig['confidence']:.3f} score={sig['score']:.3f} "
                            f"ev={sig['ev']:.5f} regime={sig['regime']} allow={ok} reason={reason} size_mult={size_mult:.2f}"
                        )
                        # v7: record every evaluated signal for post-hoc analysis.
                        try:
                            self.stats.log_signal(sig, ok, reason)
                        except Exception as _e_stats:
                            logger.debug(f"[STATS] log_signal wrap failed: {_e_stats}")
                        if not ok:
                            # Reset stickiness on hard reject.
                            if sym in self._stickiness:
                                logger.info(f"[STICKINESS_RESET] {sym} reason=signal_rejected_{reason}")
                                self._stickiness.pop(sym, None)
                            continue
                        # --- Signal stickiness gate ---
                        prev = self._stickiness.get(sym)
                        if prev is None:
                            self._stickiness[sym] = {
                                "count": 1,
                                "direction": sig["direction"],
                                "last_conf": float(sig["confidence"]),
                            }
                        else:
                            if prev["direction"] != sig["direction"]:
                                logger.info(
                                    f"[STICKINESS_RESET] {sym} reason=direction_flip "
                                    f"prev={prev['direction']} new={sig['direction']}"
                                )
                                self._stickiness[sym] = {
                                    "count": 1,
                                    "direction": sig["direction"],
                                    "last_conf": float(sig["confidence"]),
                                }
                            elif (prev["last_conf"] - float(sig["confidence"])) >= stickiness_drop_thr:
                                logger.info(
                                    f"[STICKINESS_RESET] {sym} reason=conf_drop "
                                    f"prev_conf={prev['last_conf']:.3f} new_conf={sig['confidence']:.3f}"
                                )
                                self._stickiness[sym] = {
                                    "count": 1,
                                    "direction": sig["direction"],
                                    "last_conf": float(sig["confidence"]),
                                }
                            else:
                                self._stickiness[sym] = {
                                    "count": prev["count"] + 1,
                                    "direction": sig["direction"],
                                    "last_conf": float(sig["confidence"]),
                                }
                        st_count = self._stickiness[sym]["count"]
                        if st_count < stickiness_required:
                            logger.info(
                                f"[STICKINESS] {sym} {sig['direction']} {st_count}/{stickiness_required}"
                            )
                            continue
                        logger.info(
                            f"[STICKINESS] {sym} {sig['direction']} {st_count}/{stickiness_required} CONFIRMED"
                        )
                        # Per-cycle execution cap.
                        if executed_orders >= max_new_per_cycle:
                            logger.info(f"[RATE] {sym} skipped reason=cycle_cap executed={executed_orders}/{max_new_per_cycle}")
                            continue
                        # Global min gap between entries.
                        if min_gap_sec > 0 and (time.time() - self._last_entry_ts_global) < min_gap_sec:
                            wait_s = int(min_gap_sec - (time.time() - self._last_entry_ts_global))
                            logger.info(f"[RATE] {sym} skipped reason=global_cooldown wait={wait_s}s")
                            continue
                        signals_allowed += 1
                        if reason == "override_high_ev":
                            override_count += 1

                        # Ensure leverage is 1x before opening position
                        if not self._ensure_leverage_1x(sym):
                            logger.warning(f"[ENTRY SKIP] {sym} leverage safeguard failed")
                            continue
                        
                        qty = self._entry_qty(sig, size_mult, equity)
                        entry_res = self.router.enter(sym, "long" if sig["direction"] == "long" else "short", qty)
                        if int(entry_res.get("retCode", -1)) != 0:
                            logger.warning(f"[ENTRY FAIL] {sym} ret={entry_res}")
                            continue
                        sig["_size_mult"] = float(size_mult)
                        # Fetch current position from exchange to get cumRealisedPnl (symbol-specific for speed)
                        pos_resp = self.ex.get_positions(sym)
                        ex_row = None
                        if pos_resp and pos_resp.get("retCode") == 0:
                            positions = pos_resp.get("result", {}).get("list", [])
                            if positions:
                                ex_row = positions[0]
                        self._create_state(sig, qty, ex_row=ex_row)
                        executed_orders += 1
                        self._last_entry_ts_global = time.time()
                        # Reset stickiness on entry so next signal builds fresh.
                        self._stickiness.pop(sym, None)
                        lv = self.position_states[sym].take_profit_levels
                        st = self.position_states[sym]
                        
                        # Detailed risk engine logging
                        entry_px = float(sig.get('entry', 0))
                        sl_px = st.stop_loss_price
                        atr = sig.get('atr', 0)
                        stop_distance_pct = abs(sl_px - entry_px) / entry_px * 100 if entry_px > 0 else 0
                        notional = float(qty * entry_px)
                        equity_risk_pct = notional / equity * 100 if equity > 0 else 0
                        expected_loss_at_sl = abs(qty * (sl_px - entry_px)) if sl_px and entry_px else 0
                        
                        logger.info(
                            f"[OPEN] {sym} {sig['direction']} qty={qty} entry={sig['entry']:.6f} "
                            f"notional_cap={getattr(self.prod, 'max_position_notional_usdt', 0):.0f} "
                            f"tp1={lv['tp1']:.6f} tp2={lv['tp2']:.6f} tp3={lv['tp3']:.6f} "
                            f"sl={sl_px:.6f}"
                        )
                        logger.info(
                            f"[RISK ENGINE] {sym} leverage=1x notional={notional:.2f} equity_risk={equity_risk_pct:.2f}% "
                            f"stop_distance={stop_distance_pct:.2f}% ATR={atr:.6f} expected_loss_at_sl={expected_loss_at_sl:.2f} "
                            f"risk_per_trade={getattr(self.prod, 'risk_per_trade', 0):.1%}"
                        )
                        self.cooldown.set_symbol_cooldown(sym, self.prod.symbol_reuse_cooldown_minutes)
                    except Exception as e:
                        logger.error(f"[ENTRY EXCEPTION] symbol={sig.get('symbol')} err={e}\n{traceback.format_exc()}")
                        self._snapshot_error("entry_exception", e)
                        continue

                if executed_orders == 0 and self.prod.enable_topk_fallback and evaluated:
                    ranked = sorted(evaluated, key=lambda x: x["ev"], reverse=True)
                    for sig in ranked[: self.prod.fallback_top_k]:
                        if sig["ev"] <= 0:
                            continue
                        if not self.cooldown.allow(sig["symbol"]) or not self.exposure.allow(positions, sig["symbol"]):
                            continue
                        if getattr(self.prod, "sizing_mode", "notional_sizer") != "max_exchange_qty":
                            notional = self.sizer.size_notional(
                                sig["confidence"], sig["atr"] / (sig["entry"] + 1e-12), 0.5, 1.0
                            ) * self.prod.fallback_micro_size_mult
                            if not self.heat.can_open(used, equity, notional):
                                continue
                        qty = self._entry_qty(sig, self.prod.fallback_micro_size_mult)
                        entry_res = self.router.enter(sig["symbol"], "long" if sig["direction"] == "long" else "short", qty)
                        if int(entry_res.get("retCode", -1)) != 0:
                            logger.warning(f"[ENTRY FAIL] {sig['symbol']} ret={entry_res}")
                            continue
                        # Fetch current position from exchange to get cumRealisedPnl (symbol-specific for speed)
                        pos_resp = self.ex.get_positions(sig["symbol"])
                        ex_row = None
                        if pos_resp and pos_resp.get("retCode") == 0:
                            positions = pos_resp.get("result", {}).get("list", [])
                            if positions:
                                ex_row = positions[0]
                        self._create_state(sig, qty, ex_row=ex_row)
                        executed_orders += 1
                        logger.info(
                            f"[FALLBACK OPEN] {sig['symbol']} dir={sig['direction']} ev={sig['ev']:.5f} "
                            f"qty={qty} size_mult={self.prod.fallback_micro_size_mult:.2f}"
                        )
                        break

                # Decay stickiness for symbols that disappeared from this cycle's evaluation set.
                stale_syms = [s for s in list(self._stickiness.keys()) if s not in seen_symbols_this_cycle]
                for s in stale_syms:
                    logger.info(f"[STICKINESS_RESET] {s} reason=signal_absent_this_cycle")
                    self._stickiness.pop(s, None)

                cycle_ms = int((time.time() - cycle_started) * 1000)
                logger.info(
                    f"[CYCLE METRICS] scan_cycle_time_ms={cycle_ms} signals_generated={signals_generated} "
                    f"signals_after_tier1={signals_after_tier1} signals_allowed={signals_allowed} "
                    f"override_count={override_count} executed_orders={executed_orders} "
                    f"stickiness_active={len(self._stickiness)} "
                    f"state_positions={len(self.position_states)}"
                )
                self._last_heartbeat = time.time()
                self._cycle_errors = 0
                self._save_state()
                self._write_health(cycle_ms, signals_generated, executed_orders, equity)
            except Exception as e:
                self._cycle_errors += 1
                logger.error(f"[LOOP EXCEPTION] err={e}\n{traceback.format_exc()}")
                self._snapshot_error("loop_exception", e)
                if self._cycle_errors >= self.prod.circuit_breaker_errors:
                    logger.error(f"[RISK] circuit_breaker_triggered errors={self._cycle_errors}, cooling down")
                    await asyncio.sleep(self.prod.circuit_breaker_cooldown_sec)
                    self._cycle_errors = 0
                    continue
            await asyncio.sleep(self.prod.position_loop_interval_sec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    bot = SelectiveMLBot(args.config)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()

