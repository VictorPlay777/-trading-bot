"""
V10 Research Framework Config
=============================
Strategy: NOT optimised for PnL. Designed to gather data, log everything, and
discover edge through statistics rather than tweaks.

Key principles:
- One signal == one trade (no DCA, pyramiding, reversals).
- Universe = TOP-40 Bybit linear-perp USDT by Volume * Volatility.
- Fixed $10k notional, 1x leverage.
- TP = SL = 0.5 ATR (R:R = 1:1).
- Confidence threshold = 0.75 (act), but log every confidence bucket.
- Persist V9.1 state machinery (no regression).
- Shadow-trade rejected signals for 24h max to estimate counterfactual.
- MFE/MAE tracked in R-units for every real trade.
- Feature snapshot saved on every entry with content hash.

DO NOT change config mid-run unless you bump strategy_id. Statistical
significance requires stable parameters across at least 300-500 trades.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class V10ProductionConfig:
    # Identity. NEVER reuse across config tweaks; bump the date or suffix.
    strategy_id: str = "v10_research_2026-05-12b_conf051"
    strategy_notes: str = (
        "v10b: research framework. Goal = data, not PnL. "
        "Logs every signal (allowed + rejected), shadow-trades rejects, "
        "tracks MFE/MAE per trade, snapshots features on entry. "
        "Universe TOP-40 by volume*volatility. R:R = 1:1, conf 0.51, $10k fixed. "
        "NO correlation_stack, NO concurrent limit, unconditional ADX/EV/Quality logging. "
        "Inherits V9.1 persistent state, orphan handling, and state-healing."
    )

    # ------------------------------------------------------------------ Universe
    # v10c: lowered min_turnover from $50M -> $10M to capture mid-cap pumps
    # (TRUTH, GIGA, UB, PEAQ, USELESS, IRYS, etc were excluded at $50M).
    # At $10M we typically get ~75 candidates and fill all 40 slots with high-volatility names.
    # Refresh every 15min instead of 60min so fast pumps aren't missed.
    scan_top_symbols: int = 40
    universe_min_volume_usdt: float = 10_000_000.0
    universe_min_range_pct: float = 0.005   # 0.5% minimum daily range
    universe_refresh_sec: int = 900         # rebuild every 15 minutes
    horizons: List[int] = field(default_factory=lambda: [3, 5, 10])

    # ------------------------------------------------------------------ Entry
    invert_signals: bool = False
    model: str = "catboost"
    prob_threshold_base: float = 0.51
    conf_min_decision: float = 0.51
    # v10b: lowered threshold to 0.51 to gather data across the full confidence
    # spectrum. Confidence is still logged per-signal; analytics will bucketise.
    regime_thresholds: Dict[str, float] = field(
        default_factory=lambda: {"trend": 0.51, "breakout": 0.51, "chop": 0.51, "panic": 0.51}
    )
    regime_quality_thresholds: Dict[str, float] = field(
        default_factory=lambda: {"trend": 0.0, "breakout": 0.0, "chop": 0.0, "panic": 0.0}
    )
    min_ev: float = -999.0
    ev_min_decision: float = -999.0
    uncertainty_filter: float = 0.0
    min_trade_quality: float = 0.0
    min_adx: float = 0.0

    # ------------------------------------------------------------------ Sizing
    sizing_mode: str = "fixed_notional"
    base_notional_usdt: float = 10000.0
    max_position_notional_usdt: float = 10000.0
    risk_per_trade: float = 0.0
    force_leverage_1x: bool = True
    max_concurrent_positions: int = 10000   # v10b: effectively unbounded; universe caps at ~40 symbols

    # ------------------------------------------------------------------ Exit (R = 1:1)
    # Note: tp{1,2,3}_r are ATR multipliers; in R-units (where 1R = sl_atr_mult * ATR),
    # tp1_r=1.0 means TP at +2R (since SL is at -1R = -0.5 ATR).
    # v10c calibration (backtest on 189 trades + BE-stop@0.3R + trailing):
    #   - TP=2R   (= tp1_r 1.0) leaves room for the trailing-stop to capture pumps.
    #   - Backtest projection: TP=2R + trail@1R/0.4R = +$6,268 vs +$4,951 (TP=1R baseline).
    single_tp_full_close: bool = True
    sl_atr_mult: float = 0.5
    tp1_r: float = 1.0   # = +2R (was 0.5 = +1R)
    tp2_r: float = 1.0   # = +2R (was 0.5)
    tp3_r: float = 3.0
    trailing_atr_mult: float = 1.0
    dynamic_tp_enabled: bool = False
    reversal_conf_threshold: float = 999.0  # disabled

    # ------------------------------------------------------------------ Cooldowns / pacing
    signal_cooldown_minutes: int = 0
    symbol_reuse_cooldown_minutes: int = 0
    loss_streak_pause_minutes: int = 0
    loss_streak_threshold: int = 999
    stickiness_required_cycles: int = 1
    stickiness_conf_drop_threshold: float = 0.15
    max_new_positions_per_cycle: int = 999
    min_minutes_between_entries_global: int = 0

    # ------------------------------------------------------------------ One-position-per-symbol enforcement
    max_positions_per_symbol: int = 1
    allow_add_to_position: bool = False
    allow_dca: bool = False
    allow_pyramiding: bool = False
    # v10b: REMOVE correlation_stack. Each symbol independently traded; we want
    # raw signal-level data, not correlation-blocked subsets.
    block_same_direction_stack: bool = False

    # ------------------------------------------------------------------ Execution
    limit_timeout_ms: int = 600
    requote_attempts: int = 3
    max_spread_bps: float = 4.0
    min_depth_usdt: float = 7000.0
    min_volume_24h_usdt: float = 5_000_000.0
    max_wick_ratio: float = 2.5
    max_concurrency: int = 15
    market_cache_ttl_sec: int = 3
    deep_eval_top_n: int = 25
    spread_penalty_floor: float = 0.2
    spread_penalty_cap: float = 0.7
    depth_penalty_floor: float = 0.2
    depth_penalty_cap: float = 0.7
    enable_topk_fallback: bool = False
    fallback_top_k: int = 1
    fallback_micro_size_mult: float = 0.2

    # ------------------------------------------------------------------ Position monitoring
    position_loop_interval_sec: float = 2.0
    funding_refresh_sec: int = 45
    circuit_breaker_errors: int = 8
    circuit_breaker_cooldown_sec: int = 30
    emergency_close_on_mismatch: bool = True
    high_ev_override_ev: float = 0.003
    high_ev_override_conf: float = 0.62
    override_size_mult_min: float = 0.30
    override_size_mult_max: float = 0.60
    override_size_mult_default: float = 0.50

    # ------------------------------------------------------------------ Risk engine
    enable_risk_engine: bool = True
    enable_kill_switch: bool = True
    daily_max_drawdown: float = 0.03
    max_exposure_per_symbol_usdt: float = 10000.0   # one trade-sized cap
    max_total_exposure_usdt: float = 400000.0       # ~40 simultaneous positions max
    max_daily_drawdown_usdt: float = 0.0
    max_consecutive_losses: int = 0
    max_portfolio_heat: float = 1.0

    # ------------------------------------------------------------------ Funding gating
    funding_penalty_threshold: float = 0.0005
    funding_penalty_mult: float = 0.5

    # ------------------------------------------------------------------ V9.1 state machinery (kept)
    orphan_profit_close_pct: float = 0.01
    disable_blacklist: bool = True
    # V10: also disable the winrate-based runtime filter — we want fresh data,
    # not v9 stats inherited via stats_by_symbol.json.
    disable_winrate_filter: bool = True

    # ------------------------------------------------------------------ V10 research-mode flags
    log_all_signals: bool = True              # always write signals_all.jsonl
    paper_trade_all_signals: bool = True      # run shadow trades for rejects
    shadow_max_hold_sec: int = 24 * 3600      # 24h cap for shadow holds
    shadow_max_open: int = 5000               # safety cap on memory
    mfe_mae_tracking: bool = True             # update MFE/MAE every monitor tick
    feature_snapshot_on_entry: bool = True    # save features on every real entry
    # v10c: break-even stop. When MFE >= arm_threshold_r, move SL to entry +/- offset_r.
    # Backtest on 189 trades: BE-stop @ 0.3R flips PnL from -$4.3k to +$5.3k (WR 45%->73%).
    be_stop_arm_threshold_r: float = 0.3      # arm when favorable excursion reaches this R-level
    be_stop_offset_r: float = 0.05            # post-arm SL = entry +/- offset_r * R (covers fees)
    # v10c: trailing stop. When MFE >= trail_arm_threshold_r, SL trails at MFE - trail_dist_r.
    # Captures pumps without giving back too much. 0 disables.
    trail_arm_threshold_r: float = 1.0        # arm trailing once MFE reaches this R-level
    trail_dist_r: float = 0.4                 # trailing stop distance below MFE (in R-units)
    # v10c: phase-aware gating. Modifies size_mult / blocks entries based on market_phase.
    # See V10MLBot.PHASE_RULES for the full matrix. Set False to revert to v9.1 gates.
    phase_gating_enabled: bool = True
    # v10b: always compute ADX even though min_adx=0 (filter off). Stored in
    # signal_meta + signals_all.jsonl for post-hoc analytics.
    always_compute_research_metrics: bool = True

    # ------------------------------------------------------------------ Output paths (relative to bot cwd)
    v10_log_dir: str = "logs/v10"
    v10_signals_path: str = "logs/v10/signals_all.jsonl"
    v10_trades_path: str = "logs/v10/trades_v10.jsonl"
    v10_shadow_path: str = "logs/v10/shadow_trades.jsonl"
    v10_state_path: str = "logs/v10/last_state.json"
    v10_health_path: str = "logs/v10/health.json"
    v10_features_dir: str = "logs/v10/feature_snapshots"
    v10_strategies_dir: str = "logs/v10/strategies"
