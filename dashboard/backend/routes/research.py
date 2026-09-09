from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from statistics import median, pstdev

from fastapi import APIRouter, Query, Request

from dashboard.backend.routes.common import User

router = APIRouter(prefix="/api/research", tags=["research"])

# How many rows to pull for aggregation. Signals are ~20-40 per scan cycle
# (~1/min) so this covers several days of data.
MAX_ROWS = 100000

CONF_ORDER = ["<0.50", "0.50-0.55", "0.55-0.60", "0.60-0.65", "0.65-0.70",
              "0.70-0.75", "0.75-0.80", "0.80-0.85", "0.85-0.90", "0.90+"]
ADX_ORDER = ["<10", "10-15", "15-20", "20-25", "25-30", "30-40", "40+"]
GENERIC_ORDER = ["low", "normal", "high", "extreme"]
FUNDING_ORDER = ["strong_negative", "negative", "neutral", "positive", "strong_positive"]
OI_ORDER = ["strong_falling", "falling", "neutral", "rising", "strong_rising"]
DEPTH_ORDER = ["<2k", "2k-7k", "7k-20k", "20k-50k", "50k+"]
REGIME_ORDER = ["trend", "breakout", "chop", "panic"]


def _sample_label(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT SAMPLE"
    if n < 100:
        return "LOW CONFIDENCE"
    if n < 300:
        return "MODERATE"
    return "STRONGER SAMPLE"


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _trade_stats(trades, signals_count=None):
    """Aggregate metrics for a set of trade rows (dicts from trades table)."""
    n = len(trades)
    pnls = [_f(t.get("pnl")) for t in trades]
    gross_wins = sum(p for p in pnls if p > 0)
    gross_losses = -sum(p for p in pnls if p < 0)
    wins = sum(1 for p in pnls if p > 0)
    r_mults = [_f(t.get("r_multiple")) for t in trades if t.get("r_multiple") is not None]
    out = {
        "signals": signals_count,
        "trades": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": wins / n if n else None,
        "loss_rate": (n - wins) / n if n else None,
        "profit_factor": (gross_wins / gross_losses) if gross_losses > 0 else None,
        "expectancy": sum(pnls) / n if n else None,
        "expectancy_r": sum(r_mults) / len(r_mults) if r_mults else None,
        "avg_pnl": sum(pnls) / n if n else None,
        "median_pnl": median(pnls) if pnls else None,
        "gross_pnl": sum(pnls),
        "net_pnl": sum(pnls),
        "avg_win": gross_wins / wins if wins else None,
        "avg_loss": gross_losses / (n - wins) if (n - wins) else None,
        "max_win": max(pnls) if pnls else None,
        "max_loss": min(pnls) if pnls else None,
        "avg_mae": (sum(_f(t.get("mae")) for t in trades) / n) if n else None,
        "avg_mfe": (sum(_f(t.get("mfe")) for t in trades) / n) if n else None,
        "sample_size": n,
        "sample_label": _sample_label(n),
    }
    if n >= 2:
        sd = pstdev(pnls)
        mean = sum(pnls) / n
        out["sharpe"] = (mean / sd) if sd > 0 else None
        downside = [p for p in pnls if p < 0]
        dd_sd = pstdev(downside) if len(downside) >= 2 else None
        out["sortino"] = (mean / dd_sd) if dd_sd and dd_sd > 0 else None
        # max drawdown on cumulative pnl sorted by close time
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(trades, key=lambda r: _f(r.get("closed_ts") or r.get("opened_ts"))):
            cum += _f(t.get("pnl"))
            peak = max(peak, cum)
            max_dd = max(max_dd, peak - cum)
        out["max_drawdown"] = max_dd
    else:
        out["sharpe"] = out["sortino"] = None
        out["max_drawdown"] = abs(min(pnls)) if pnls else None
    return out


def _load(store):
    signals = store.list_signal_snapshots({}, MAX_ROWS, 0)
    trades, _ = store.list_trades({}, MAX_ROWS, 0)
    snap_by_id = {s["id"]: s for s in signals}
    for t in trades:
        snap = snap_by_id.get(t.get("signal_snapshot_id"))
        t["_signal"] = snap  # may be None for unlinked/old trades
        # fall back to trade's own signal metadata columns when no snapshot row
        if snap is None:
            raw = t.get("signal_json")
            try:
                meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except json.JSONDecodeError:
                meta = {}
            t["_signal"] = {
                "regime": t.get("regime") or meta.get("regime"),
                "confidence": t.get("confidence") or meta.get("confidence"),
                "direction": t.get("side"),
                "confidence_bucket": _conf_bucket(_f(t.get("confidence") or meta.get("confidence"))),
                "adx": meta.get("adx"),
                "adx_bucket": _adx_bucket(_f(meta.get("adx"))),
                "atr_pct": (meta.get("atr") / _f(t.get("entry_price")) * 100) if _f(t.get("entry_price")) else None,
                "atr_bucket": _atr_bucket((meta.get("atr") or 0) / _f(t.get("entry_price")) * 100 if _f(t.get("entry_price")) else 0),
                "symbol": t.get("symbol"),
            }
    return signals, trades


def _conf_bucket(c):
    from dashboard.bot_bridge import bucket_confidence
    return bucket_confidence(c)


def _adx_bucket(v):
    from dashboard.bot_bridge import bucket_adx
    return bucket_adx(v)


def _atr_bucket(v):
    from dashboard.bot_bridge import bucket_atr_pct
    return bucket_atr_pct(v)


def _sig_count(signals, **kw):
    n = 0
    for s in signals:
        if all(s.get(k) == v for k, v in kw.items()):
            n += 1
    return n


def _group_stats(trades, key_fn, order=None, signals=None, sig_key_fn=None):
    groups = defaultdict(list)
    for t in trades:
        k = key_fn(t)
        if k is not None:
            groups[k].append(t)
    sig_counts = defaultdict(int)
    if signals is not None and sig_key_fn is not None:
        for s in signals:
            k = sig_key_fn(s)
            if k is not None:
                sig_counts[k] += 1
    rows = []
    keys = order if order else sorted(groups.keys(), key=str)
    for k in keys:
        if k not in groups and k not in sig_counts:
            continue
        st = _trade_stats(groups.get(k, []), signals_count=sig_counts.get(k))
        st["key"] = k
        rows.append(st)
    for k, v in groups.items():
        if order and k not in order:
            st = _trade_stats(v, signals_count=sig_counts.get(k))
            st["key"] = k
            rows.append(st)
    return rows


@router.get("/overview")
async def overview(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    stats = _trade_stats(trades, signals_count=len(signals))
    stats["allowed_signals"] = sum(1 for s in signals if s.get("allowed"))
    stats["rejected_signals"] = sum(1 for s in signals if not s.get("allowed"))
    return stats


@router.get("/direction")
async def direction(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    out = {}
    for d in ("long", "short"):
        sel = [t for t in trades if (t.get("side") or "").lower() == d]
        sig_n = sum(1 for s in signals if (s.get("direction") or "").lower() == d and s.get("allowed"))
        st = _trade_stats(sel, signals_count=sig_n)
        out[d] = st
    out["all"] = _trade_stats(trades, signals_count=len(signals))
    return out


@router.get("/confidence")
async def confidence(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    return {"rows": _group_stats(
        trades,
        lambda t: (t["_signal"] or {}).get("confidence_bucket"),
        order=CONF_ORDER,
        signals=[s for s in signals if s.get("allowed")],
        sig_key_fn=lambda s: s.get("confidence_bucket"),
    )}


@router.get("/regime")
async def regime(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    return {"rows": _group_stats(
        trades,
        lambda t: (t["_signal"] or {}).get("regime"),
        order=REGIME_ORDER,
        signals=[s for s in signals if s.get("allowed")],
        sig_key_fn=lambda s: s.get("regime"),
    )}


@router.get("/regime-direction")
async def regime_direction(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    rows = _group_stats(
        trades,
        lambda t: ((t["_signal"] or {}).get("regime"), (t.get("side") or "").lower())
        if (t["_signal"] or {}).get("regime")
        else None,
    )
    # reshape to matrix
    matrix = {}
    for r in REGIME_ORDER:
        matrix[r] = {}
        for d in ("long", "short"):
            matrix[r][d] = {"trades": 0, "win_rate": None, "expectancy_r": None, "profit_factor": None, "sample_label": _sample_label(0)}
    for row in rows:
        reg, d = row["key"]
        matrix.setdefault(reg, {})[d] = {
            "trades": row["trades"], "win_rate": row["win_rate"],
            "expectancy": row["expectancy"], "expectancy_r": row["expectancy_r"],
            "profit_factor": row["profit_factor"], "net_pnl": row["net_pnl"],
            "sample_label": row["sample_label"],
        }
    return {"matrix": matrix}


@router.get("/confidence-regime")
async def confidence_regime(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    rows = _group_stats(
        trades,
        lambda t: ((t["_signal"] or {}).get("confidence_bucket"), (t["_signal"] or {}).get("regime"))
        if (t["_signal"] or {}).get("confidence_bucket") and (t["_signal"] or {}).get("regime")
        else None,
    )
    for row in rows:
        row["confidence_bucket"], row["regime"] = row["key"]
        del row["key"]
    return {"rows": rows}


@router.get("/symbols")
async def symbols(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t.get("symbol")].append(t)
    sig_n = defaultdict(int)
    for s in signals:
        sig_n[s.get("symbol")] += 1
    rows = []
    for sym, sel in by_sym.items():
        st = _trade_stats(sel, signals_count=sig_n.get(sym, 0))
        st["symbol"] = sym
        st["long_wr"] = _trade_stats([t for t in sel if (t.get("side") or "").lower() == "long"])["win_rate"]
        st["short_wr"] = _trade_stats([t for t in sel if (t.get("side") or "").lower() == "short"])["win_rate"]
        rows.append(st)
    rows.sort(key=lambda r: -(r["net_pnl"] or 0))
    return {"rows": rows}


@router.get("/filters")
async def filters(request: Request, _user: User):
    signals, _trades = _load(request.app.state.store)
    counts = defaultdict(lambda: {"rejected": 0, "sole_reason": 0})
    for s in signals:
        if s.get("allowed"):
            continue
        reasons = []
        raw = s.get("rejection_reasons_json")
        try:
            reasons = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (TypeError, json.JSONDecodeError):
            reasons = []
        if not reasons and s.get("rejection_reason"):
            reasons = [s["rejection_reason"]]
        # normalize: strip specifics like horizon_disagree(...) into base code
        norm = []
        for r in reasons:
            base = str(r).split("(")[0].upper()
            norm.append(base)
        for r in set(norm):
            counts[r]["rejected"] += 1
        if len(set(norm)) == 1:
            counts[norm[0]]["sole_reason"] += 1
    total_rej = sum(1 for s in signals if not s.get("allowed"))
    rows = [
        {"filter": k, "rejected": v["rejected"], "sole_reason": v["sole_reason"],
         "share_of_rejected": v["rejected"] / total_rej if total_rej else None}
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]["rejected"])
    ]
    return {"rows": rows, "total_signals": len(signals), "total_rejected": total_rej}


@router.get("/time")
async def time_analysis(request: Request, _user: User):
    signals, trades = _load(request.app.state.store)

    def hour_of(t):
        snap = t.get("_signal") or {}
        ts = snap.get("ts") or t.get("opened_ts")
        return time.gmtime(_f(ts)).tm_hour if ts else None

    def dow_of(t):
        snap = t.get("_signal") or {}
        ts = snap.get("ts") or t.get("opened_ts")
        return time.gmtime(_f(ts)).tm_wday if ts else None

    by_hour = _group_stats(trades, hour_of, order=list(range(24)))
    by_dow = _group_stats(trades, dow_of, order=list(range(7)))
    hour_dir = _group_stats(trades, lambda t: (hour_of(t), (t.get("side") or "").lower()))
    hour_regime = _group_stats(trades, lambda t: (hour_of(t), (t["_signal"] or {}).get("regime")))
    dow_dir = _group_stats(trades, lambda t: (dow_of(t), (t.get("side") or "").lower()))
    return {
        "by_hour": by_hour, "by_dow": by_dow,
        "hour_direction": hour_dir, "hour_regime": hour_regime, "dow_direction": dow_dir,
    }


@router.get("/buckets")
async def buckets(request: Request, _user: User, field: str = "atr_bucket"):
    """Generic bucketed stats for volatility/funding/oi/volume/depth."""
    allowed_fields = {
        "atr_bucket", "volatility_bucket", "volume_bucket", "funding_bucket",
        "oi_bucket", "depth_bucket", "adx_bucket", "confidence_bucket",
    }
    if field not in allowed_fields:
        field = "atr_bucket"
    orders = {
        "atr_bucket": GENERIC_ORDER, "volatility_bucket": GENERIC_ORDER,
        "volume_bucket": GENERIC_ORDER, "funding_bucket": FUNDING_ORDER,
        "oi_bucket": OI_ORDER, "depth_bucket": DEPTH_ORDER,
        "adx_bucket": ADX_ORDER, "confidence_bucket": CONF_ORDER,
    }
    signals, trades = _load(request.app.state.store)
    return {"field": field, "rows": _group_stats(
        trades,
        lambda t: (t["_signal"] or {}).get(field),
        order=orders[field],
        signals=[s for s in signals if s.get("allowed")],
        sig_key_fn=lambda s: s.get(field),
    )}


@router.get("/edge-matrix")
async def edge_matrix(request: Request, _user: User, min_trades: int = Query(5, ge=1)):
    _signals, trades = _load(request.app.state.store)
    groups = defaultdict(list)
    for t in trades:
        s = t.get("_signal") or {}
        key = (
            s.get("regime") or "unknown",
            (t.get("side") or "?").lower(),
            s.get("confidence_bucket") or "?",
            s.get("adx_bucket") or "?",
            s.get("atr_bucket") or "?",
        )
        groups[key].append(t)
    rows = []
    for key, sel in groups.items():
        if len(sel) < min_trades:
            continue
        st = _trade_stats(sel)
        exp_r = st.get("expectancy_r")
        exp = st.get("expectancy")
        if st["trades"] < 30:
            status = "INSUFFICIENT"
        elif exp is not None and exp > 0:
            status = "PROMISING"
        elif exp is not None and exp < 0:
            status = "BAD"
        else:
            status = "NEUTRAL"
        rows.append({
            "regime": key[0], "direction": key[1], "confidence": key[2],
            "adx": key[3], "atr": key[4],
            "trades": st["trades"], "win_rate": st["win_rate"],
            "profit_factor": st["profit_factor"], "expectancy": exp,
            "expectancy_r": exp_r, "net_pnl": st["net_pnl"],
            "sample_label": st["sample_label"], "status": status,
        })
    rows.sort(key=lambda r: (-(r["expectancy_r"] if r["expectancy_r"] is not None else -math.inf)))
    return {"rows": rows, "min_trades": min_trades}


# ---------------------------------------------------------------------------
# Edge discovery — counterfactual analysis over ALL signals (allowed or not)
# ---------------------------------------------------------------------------

def _cf_r(s):
    """Counterfactual R for a signal+outcome row. tp_first → ±1R (TP=SL=0.5ATR);
    otherwise normalize future_return_10 by the signal's own risk."""
    if s.get("tp_first") is not None:
        return _f(s.get("cf_r"), 0.0) or 0.0
    fr = s.get("future_return_10")
    atr_pct = s.get("atr_pct")
    if fr is None or not atr_pct:
        return None
    risk_pct = max(atr_pct / 2.0, 1e-6)  # risk = 0.5*ATR
    return _f(fr) / (risk_pct / 100.0)


def _evidence_label(n, exp_r, oos_exp_r, breadth):
    """Evidence classification: combines sample size, OOS sign agreement and
    symbol breadth. Does not claim causality."""
    if n < 30:
        return "INSUFFICIENT DATA"
    if exp_r is None:
        return "NO EVIDENCE"
    stable = oos_exp_r is not None and (exp_r > 0) == (oos_exp_r > 0)
    broad = breadth is not None and breadth >= 0.5
    if exp_r > 0:
        if n >= 100 and stable and broad:
            return "OBSERVED EDGE"
        if stable:
            return "POSSIBLE EDGE"
        return "WEAK EVIDENCE"
    if exp_r < 0:
        if n >= 30 and stable:
            return "NEGATIVE EDGE"
        return "NO EVIDENCE"
    return "NO EVIDENCE"


def _cf_group(rows, key_fn, order=None, min_n=1):
    groups = defaultdict(list)
    for s in rows:
        k = key_fn(s)
        if k is None or (isinstance(k, tuple) and any(x is None for x in k)):
            continue
        groups[k].append(s)
    out = []
    for k, sel in groups.items():
        if len(sel) < min_n:
            continue
        rs = [r for r in (_cf_r(s) for s in sel) if r is not None]
        if not rs:
            continue
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        gross_w = sum(r for r in rs if r > 0)
        gross_l = -sum(r for r in rs if r < 0)
        ts_sorted = sorted(sel, key=lambda s: _f(s.get("ts")))
        mid = len(ts_sorted) // 2
        ins = [x for x in (_cf_r(s) for s in ts_sorted[:mid]) if x is not None]
        oos = [x for x in (_cf_r(s) for s in ts_sorted[mid:]) if x is not None]
        ins_exp = sum(ins) / len(ins) if ins else None
        oos_exp = sum(oos) / len(oos) if oos else None
        syms = defaultdict(list)
        for s in sel:
            syms[s.get("symbol")].append(s)
        pos_syms = 0
        tot_syms = 0
        for sym, ss in syms.items():
            sr = [x for x in (_cf_r(s2) for s2 in ss) if x is not None]
            if len(sr) >= 3:
                tot_syms += 1
                if sum(sr) / len(sr) > 0:
                    pos_syms += 1
        breadth = pos_syms / tot_syms if tot_syms else None
        exp_r = sum(rs) / n
        out.append({
            "key": k,
            "n": n,
            "wins": wins,
            "win_rate": wins / n,
            "profit_factor": (gross_w / gross_l) if gross_l > 0 else None,
            "expectancy_r": exp_r,
            "in_sample_r": ins_exp,
            "oos_r": oos_exp,
            "symbol_breadth": breadth,
            "symbols": tot_syms,
            "sample_label": _sample_label(n),
            "evidence": _evidence_label(n, exp_r, oos_exp, breadth),
        })
    keys_order = order or []
    out.sort(key=lambda r: (keys_order.index(r["key"]) if r["key"] in keys_order else 99,
                            -(r["expectancy_r"] or 0)))
    return out


@router.get("/edge-discovery")
async def edge_discovery(request: Request, _user: User):
    rows = request.app.state.store.list_outcomes(MAX_ROWS)
    baseline_rs = [r for r in (_cf_r(s) for s in rows) if r is not None]
    baseline = {
        "n": len(baseline_rs),
        "win_rate": (sum(1 for r in baseline_rs if r > 0) / len(baseline_rs)) if baseline_rs else None,
        "expectancy_r": (sum(baseline_rs) / len(baseline_rs)) if baseline_rs else None,
    }

    level1 = {}
    for name, fn, order in [
        ("direction", lambda s: s.get("direction"), ["long", "short"]),
        ("regime", lambda s: s.get("regime"), REGIME_ORDER),
        ("confidence", lambda s: s.get("confidence_bucket"), CONF_ORDER),
        ("adx", lambda s: s.get("adx_bucket"), ADX_ORDER),
        ("atr", lambda s: s.get("atr_bucket"), GENERIC_ORDER),
        ("volume", lambda s: s.get("volume_bucket"), GENERIC_ORDER),
        ("funding", lambda s: s.get("funding_bucket"), FUNDING_ORDER),
        ("oi", lambda s: s.get("oi_bucket"), OI_ORDER),
        ("depth", lambda s: s.get("depth_bucket"), DEPTH_ORDER),
        ("imbalance", lambda s: "bullish" if _f(s.get("imbalance")) > 0.1 else "bearish" if _f(s.get("imbalance")) < -0.1 else "neutral", None),
        ("momentum", lambda s: "up" if _f(s.get("ret_10")) > 0 else "down" if _f(s.get("ret_10")) < 0 else None, None),
    ]:
        level1[name] = _cf_group(rows, fn, order)

    level2 = {}
    for name, fn in [
        ("regime_direction", lambda s: (s.get("regime"), s.get("direction"))),
        ("confidence_direction", lambda s: (s.get("confidence_bucket"), s.get("direction"))),
        ("adx_direction", lambda s: (s.get("adx_bucket"), s.get("direction"))),
        ("atr_direction", lambda s: (s.get("atr_bucket"), s.get("direction"))),
        ("volume_direction", lambda s: (s.get("volume_bucket"), s.get("direction"))),
        ("confidence_regime", lambda s: (s.get("confidence_bucket"), s.get("regime"))),
        ("adx_regime", lambda s: (s.get("adx_bucket"), s.get("regime"))),
    ]:
        level2[name] = _cf_group(rows, fn)

    level3 = {}
    for name, fn in [
        ("dir_regime_conf_adx", lambda s: (s.get("direction"), s.get("regime"), s.get("confidence_bucket"), s.get("adx_bucket"))),
        ("dir_regime_atr_vol", lambda s: (s.get("direction"), s.get("regime"), s.get("atr_bucket"), s.get("volume_bucket"))),
        ("dir_conf_imbalance", lambda s: (s.get("direction"), s.get("confidence_bucket"),
                                          "bullish" if _f(s.get("imbalance")) > 0.1 else "bearish" if _f(s.get("imbalance")) < -0.1 else "neutral")),
        ("symbol_dir_regime", lambda s: (s.get("symbol"), s.get("direction"), s.get("regime"))),
    ]:
        level3[name] = _cf_group(rows, fn, min_n=3)

    # Top observed edges = level3 combos sorted by expectancy_r, plus best of level1/2
    all_combos = []
    for grp_name, grp in level3.items():
        for row in grp:
            all_combos.append({**row, "group": grp_name,
                               "label": " + ".join(str(x).upper() for x in row["key"])})
    all_combos.sort(key=lambda r: -(r["expectancy_r"] or -999))
    top_edges = all_combos[:15]
    worst_edges = [r for r in reversed(all_combos[-15:]) if (r["expectancy_r"] or 0) < 0]

    return {
        "baseline": baseline,
        "level1": level1,
        "level2": level2,
        "level3": {k: v[:50] for k, v in level3.items()},
        "top_edges": top_edges,
        "worst_edges": worst_edges,
    }


@router.get("/symbol-edge")
async def symbol_edge(request: Request, _user: User):
    rows = request.app.state.store.list_outcomes(MAX_ROWS)
    groups = defaultdict(lambda: defaultdict(list))
    for s in rows:
        d = (s.get("direction") or "").lower()
        if d in ("long", "short"):
            groups[s.get("symbol")][d].append(s)
    out = []
    for sym, by_dir in groups.items():
        entry = {"symbol": sym}
        for d in ("long", "short"):
            rs = [r for r in (_cf_r(s) for s in by_dir.get(d, [])) if r is not None]
            n = len(rs)
            entry[d] = {
                "n": n,
                "win_rate": (sum(1 for r in rs if r > 0) / n) if n else None,
                "expectancy_r": (sum(rs) / n) if n else None,
                "sample_label": _sample_label(n),
            }
        out.append(entry)
    out.sort(key=lambda r: -max(_f(r["long"]["expectancy_r"], -99), _f(r["short"]["expectancy_r"], -99)))
    return {"rows": out}


@router.get("/filter-value")
async def filter_value(request: Request, _user: User):
    """For each rejection reason: how many signals it blocked and what their
    counterfactual outcome would have been (would-win / would-lose)."""
    rows = request.app.state.store.list_outcomes(MAX_ROWS)
    rejected = [s for s in rows if not s.get("allowed")]
    by_reason = defaultdict(list)
    for s in rejected:
        reasons = []
        raw = s.get("rejection_reasons_json")
        try:
            reasons = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (TypeError, json.JSONDecodeError):
            reasons = []
        if not reasons and s.get("rejection_reason"):
            reasons = [s["rejection_reason"]]
        for r in set(str(x).split("(")[0].upper() for x in reasons):
            by_reason[r].append(s)
    out = []
    for reason, sel in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        rs = [r for r in (_cf_r(s) for s in sel) if r is not None]
        n = len(rs)
        would_win = sum(1 for r in rs if r > 0)
        out.append({
            "filter": reason,
            "rejected": len(sel),
            "with_outcome": n,
            "would_win": would_win,
            "would_lose": n - would_win,
            "would_win_rate": would_win / n if n else None,
            "cf_expectancy_r": (sum(rs) / n) if n else None,
            "verdict": ("FILTER HELPS" if (n and sum(rs) / n < 0)
                        else "FILTER HURTS" if (n and sum(rs) / n > 0)
                        else "NO DATA"),
            "sample_label": _sample_label(n),
        })
    return {"rows": out}


@router.get("/trade-explain")
async def trade_explain(request: Request, _user: User, trade_id: str = ""):
    store = request.app.state.store
    trades, _ = store.list_trades({}, MAX_ROWS, 0)
    t = next((x for x in trades if str(x.get("trade_id")) == str(trade_id)), None)
    if t is None:
        return {"error": "trade not found"}
    snap = None
    if t.get("signal_snapshot_id"):
        snaps = {s["id"]: s for s in store.list_signal_snapshots({}, MAX_ROWS, 0)}
        snap = snaps.get(t["signal_snapshot_id"])
    s = snap or {}
    # Factor checklist vs rough quality marks
    def mark(good):
        return "good" if good else "warn"

    conf = _f(s.get("confidence"), _f(t.get("confidence")))
    adx = _f(s.get("adx"))
    rel_vol = _f(s.get("rel_volume"))
    imb = _f(s.get("imbalance"))
    spread = _f(s.get("spread_bps"))
    funding = _f(s.get("funding_rate"))
    side = (t.get("side") or "").lower()
    funding_bad = (side == "long" and funding > 0.0005) or (side == "short" and funding < -0.0005)
    checks = [
        {"factor": "Confidence", "value": round(conf, 3), "mark": mark(conf >= 0.70)},
        {"factor": "Agreement", "value": f"{s.get('agreement')}/3" if s.get("agreement") is not None else "—", "mark": mark(_f(s.get("agreement")) >= 3)},
        {"factor": "Regime", "value": s.get("regime") or t.get("regime") or "—", "mark": mark((s.get("regime") or t.get("regime")) in ("trend", "breakout"))},
        {"factor": "ADX", "value": round(adx, 1), "mark": mark(adx >= 20)},
        {"factor": "Relative volume", "value": f"{rel_vol:.2f}x" if rel_vol else "—", "mark": mark(rel_vol >= 1.0)},
        {"factor": "Orderbook", "value": ("bullish" if imb > 0.1 else "bearish" if imb < -0.1 else "neutral"), "mark": mark((side == "long" and imb > 0) or (side == "short" and imb < 0))},
        {"factor": "Funding", "value": "neutral" if not funding_bad else "against", "mark": mark(not funding_bad)},
        {"factor": "ATR bucket", "value": s.get("atr_bucket") or "—", "mark": mark(s.get("atr_bucket") in ("normal", "high"))},
        {"factor": "Spread", "value": f"{spread:.1f} bps" if spread else "—", "mark": mark(spread <= 4.0)},
    ]
    return {
        "trade": t,
        "signal": snap,
        "checks": checks,
        "result_r": t.get("r_multiple"),
        "result": t.get("result"),
    }


@router.get("/edge-report")
async def edge_report(request: Request, _user: User):
    rows = request.app.state.store.list_outcomes(MAX_ROWS)
    now = time.time()

    def _period_stats(days=None):
        sel = rows if days is None else [s for s in rows if _f(s.get("ts")) >= now - days * 86400]
        rs = [r for r in (_cf_r(s) for s in sel) if r is not None]
        return {
            "n": len(rs),
            "win_rate": (sum(1 for r in rs if r > 0) / len(rs)) if rs else None,
            "expectancy_r": (sum(rs) / len(rs)) if rs else None,
        }

    disc = await edge_discovery(request, _user)
    return {
        "period": "all time",
        "by_period": {"24h": _period_stats(1), "7d": _period_stats(7), "all": _period_stats(None)},
        "top_edges": disc["top_edges"][:10],
        "worst_edges": disc["worst_edges"][:10],
        "baseline": disc["baseline"],
    }


@router.get("/signals")
async def research_signals(request: Request, _user: User, limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
    rows = request.app.state.store.list_signal_snapshots({}, limit, offset)
    return {"items": rows}


@router.get("/equity-curve")
async def equity_curve(request: Request, _user: User):
    now = time.time()
    snaps = request.app.state.store.list_equity(0, now, limit=2000)
    cum = []
    total = 0.0
    trades, _ = request.app.state.store.list_trades({}, MAX_ROWS, 0)
    for t in sorted(trades, key=lambda r: _f(r.get("closed_ts") or r.get("opened_ts"))):
        total += _f(t.get("pnl"))
        cum.append({"ts": t.get("closed_ts") or t.get("opened_ts"), "cum_pnl": total})
    return {"equity": snaps, "cumulative_pnl": cum}
