from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ProductionConfig:
    model: str = "catboost"
    scan_top_symbols: int = 40
    horizons: List[int] = field(default_factory=lambda: [3, 5, 10])
    prob_threshold_base: float = 0.60
    uncertainty_filter: float = 0.12
    min_trade_quality: float = 0.55
    sl_atr_mult: float = 0.8
    tp1_r: float = 1.0
    tp2_r: float = 1.5
    trailing_atr_mult: float = 1.1
    max_concurrent_positions: int = 3
    enable_kill_switch: bool = True
    daily_max_drawdown: float = 0.03
    signal_cooldown_minutes: int = 10
    symbol_reuse_cooldown_minutes: int = 10
    loss_streak_pause_minutes: int = 15
    loss_streak_threshold: int = 3
    limit_timeout_ms: int = 600
    requote_attempts: int = 3
    max_spread_bps: float = 8.0
    min_depth_usdt: float = 30000.0
    min_volume_24h_usdt: float = 5_000_000.0
    max_wick_ratio: float = 2.5
    max_positions_per_symbol: int = 1
    # Legacy sizing base. Not used when sizing is set to "max_exchange_qty".
    base_notional_usdt: float = 10000.0
    max_portfolio_heat: float = 0.35
    min_ev: float = 0.0  # TEST MODE: disabled filter

    # --- Production risk controls (exchange-first) ---
    # These are enforced in the bot loop; keep defaults permissive to avoid breaking existing flow.
    enable_risk_engine: bool = True
    max_exposure_per_symbol_usdt: float = 250000.0
    max_total_exposure_usdt: float = 1000000.0
    max_daily_drawdown_usdt: float = 0.0  # 0 disables
    max_consecutive_losses: int = 0  # 0 disables

    # Sizing mode: try to enter at the exchange max market qty.
    sizing_mode: str = "max_exchange_qty"  # "max_exchange_qty" | "notional_sizer"
    # Decision/execution optimization
    max_concurrency: int = 15
    market_cache_ttl_sec: int = 3
    deep_eval_top_n: int = 25
    ev_min_decision: float = 0.0  # TEST MODE: disabled filter
    conf_min_decision: float = 0.0  # TEST MODE: disabled filter
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
    tp3_r: float = 2.0
    emergency_close_on_mismatch: bool = True
    high_ev_override_ev: float = 0.0  # TEST MODE: disabled filter
    high_ev_override_conf: float = 0.55
    override_size_mult_min: float = 0.30
    override_size_mult_max: float = 0.60
    override_size_mult_default: float = 0.50
    regime_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.0,  # TEST MODE: disabled filter
            "breakout": 0.0,  # TEST MODE: disabled filter
            "chop": 999.0,  # DISABLED: chop regime rejected
            "panic": 0.0,  # TEST MODE: disabled filter
        }
    )
    # Adaptive per-regime quality gate (overrides min_trade_quality when present).
    regime_quality_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.0,  # TEST MODE: disabled filter
            "breakout": 0.0,  # TEST MODE: disabled filter
            "chop": 0.0,  # TEST MODE: disabled filter
            "panic": 0.0,  # TEST MODE: disabled filter
        }
    )
    # Execution rate limits.
    max_new_positions_per_cycle: int = 1
    min_minutes_between_entries_global: int = 3
    # Signal stickiness: require N consecutive cycles with allow=True before entry.
    stickiness_required_cycles: int = 1  # TEST MODE: disabled stickiness
    stickiness_conf_drop_threshold: float = 0.15
    # Hard cap for position notional (applies even in max_exchange_qty mode).
    max_position_notional_usdt: float = 25000.0

