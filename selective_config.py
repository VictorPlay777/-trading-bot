from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ProductionConfig:
    # Strategy versioning: identifier persisted into each trade record and
    # used to snapshot the active config to strategies/<strategy_id>.json.
    # Bump this whenever you change parameters that should be tracked separately.
    strategy_id: str = "v6_equal_tp_sl_0.5atr_noinvert_2026-05-05"
    strategy_notes: str = "v6: TP=SL=0.5*ATR (more achievable vs model EV 1-4%), NO invert, NO concurrent-position cap."
    # v5: trade actual model direction (long=long, short=short) for pure winrate measurement.
    # Previously inverted due to negative EV-PnL correlation in v1; now testing raw model edge.
    invert_signals: bool = False
    # Clean-mirror mode: close 100% of position on TP1 hit (no TP2/TP3 partials).
    single_tp_full_close: bool = True
    model: str = "catboost"
    scan_top_symbols: int = 40
    horizons: List[int] = field(default_factory=lambda: [3, 5, 10])
    prob_threshold_base: float = 0.75
    uncertainty_filter: float = 0.08
    min_trade_quality: float = 0.72
    # v6: EQUAL TP/SL = 0.5 ATR for higher achievability.
    # Model EV typically 1-4% per signal, 1 ATR was often too far (1.4-5%).
    # 0.5 ATR (0.7-2.5%) brings target within model's expected move range.
    # Fees ~0.12%, so 0.5 ATR keeps fee-eat at 5-17% (acceptable).
    sl_atr_mult: float = 0.5      # v6: SL = 0.5*ATR
    tp1_r: float = 0.5            # v6: TP = 0.5*ATR
    tp2_r: float = 0.5            # unused when single_tp_full_close=True
    trailing_atr_mult: float = 1.0  # unused
    max_concurrent_positions: int = 999  # v4: effectively no cap
    enable_kill_switch: bool = True
    daily_max_drawdown: float = 0.03
    signal_cooldown_minutes: int = 20
    symbol_reuse_cooldown_minutes: int = 60
    loss_streak_pause_minutes: int = 15
    loss_streak_threshold: int = 3
    limit_timeout_ms: int = 600
    requote_attempts: int = 3
    max_spread_bps: float = 4.0
    min_depth_usdt: float = 7000.0  # Testnet: tier1 gate = 30% = 2100 USDT
    min_volume_24h_usdt: float = 5_000_000.0
    max_wick_ratio: float = 2.5
    max_positions_per_symbol: int = 1
    # Legacy sizing base. Not used when sizing is set to "max_exchange_qty".
    base_notional_usdt: float = 10000.0
    max_portfolio_heat: float = 1.0  # v4: effectively no heat cap (full equity usable)
    min_ev: float = 0.001  # Require minimum EV of 0.1%

    # --- Production risk controls (exchange-first) ---
    # These are enforced in the bot loop; keep defaults permissive to avoid breaking existing flow.
    enable_risk_engine: bool = True
    max_exposure_per_symbol_usdt: float = 250000.0
    max_total_exposure_usdt: float = 1000000.0
    max_daily_drawdown_usdt: float = 0.0  # 0 disables
    max_consecutive_losses: int = 0  # 0 disables

    # Sizing mode: risk-based sizing
    sizing_mode: str = "risk_based"  # "max_exchange_qty" | "notional_sizer" | "risk_based"
    risk_per_trade: float = 0.003  # 0.3% equity risk per trade
    # Decision/execution optimization
    max_concurrency: int = 15
    market_cache_ttl_sec: int = 3
    deep_eval_top_n: int = 25
    ev_min_decision: float = 0.003  # Require reasonable EV for override
    conf_min_decision: float = 0.55  # Require min 55% confidence for override
    spread_penalty_floor: float = 0.2
    spread_penalty_cap: float = 0.7
    depth_penalty_floor: float = 0.2
    depth_penalty_cap: float = 0.7
    enable_topk_fallback: bool = False
    fallback_top_k: int = 1
    fallback_micro_size_mult: float = 0.2
    # Bot-controlled exit engine / state sync
    position_loop_interval_sec: float = 2.0
    funding_refresh_sec: int = 45
    circuit_breaker_errors: int = 8
    circuit_breaker_cooldown_sec: int = 30
    tp3_r: float = 3.0  # was 4.0
    emergency_close_on_mismatch: bool = True
    high_ev_override_ev: float = 0.003  # High EV threshold for override
    high_ev_override_conf: float = 0.62
    override_size_mult_min: float = 0.30
    override_size_mult_max: float = 0.60
    override_size_mult_default: float = 0.50
    regime_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.68,
            "breakout": 0.65,
            "chop": 999.0,  # DISABLED: chop regime rejected
            "panic": 0.72,
        }
    )
    # Adaptive per-regime quality gate (overrides min_trade_quality when present).
    regime_quality_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.60,
            "breakout": 0.60,
            "chop": 0.65,
            "panic": 0.65,
        }
    )
    # Execution rate limits.
    max_new_positions_per_cycle: int = 999  # v4: unlimited entries per cycle
    min_minutes_between_entries_global: int = 0  # v4: no global gap between entries
    # Signal stickiness: require N consecutive cycles with allow=True before entry.
    stickiness_required_cycles: int = 1
    stickiness_conf_drop_threshold: float = 0.15
    # Hard cap for position notional (applies even in max_exchange_qty mode).
    max_position_notional_usdt: float = 25000.0
    # ADX filter for trend confirmation
    min_adx: float = 22.0
    # Force leverage to 1x for all symbols
    force_leverage_1x: bool = True
    # Signal reversal exit: close position if model predicts strong opposite direction
    # DISABLED in v2: was 0% WR over 53 trades, -$48k loss attribution
    reversal_conf_threshold: float = 999.0  # was 0.70
    # Funding rate filter: reduce size when funding works against position direction
    funding_penalty_threshold: float = 0.0005  # 0.05% per 8h
    funding_penalty_mult: float = 0.5  # Apply 50% size reduction when unfavorable
    # Correlation filter: prevent stacking same-direction positions
    block_same_direction_stack: bool = False
    # Dynamic TP: scale TPs based on model confidence and EV
    # DISABLED in v3: with inversion, "high confidence" no longer means "high upside"
    dynamic_tp_enabled: bool = False  # was True

