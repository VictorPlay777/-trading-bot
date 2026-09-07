# Professional Statistics System v2

## Overview

This is a professional, reproducible statistics collection system for the ML trading bot. It tracks the complete lifecycle:

```
raw events → signals → trades → equity → automatically calculated metrics → reports
```

All raw data is stored in append-only JSONL files, allowing complete recalculation of any aggregated metrics at any time.

## Files

### New Statistics Modules (`stats/`)

- `system_id.py` - Unique ID generation for signals, trades, and equity snapshots
- `signal_logger.py` - Complete signal logging with full feature snapshots
- `trade_logger.py` - Complete trade logging with MAE/MFE and full PnL breakdown
- `equity_tracker.py` - Equity curve and portfolio state tracking
- `mae_mfe_tracker.py` - Maximum Adverse/Favorable Excursion tracking
- `data_quality.py` - Data validation and quality checks
- `advanced_metrics.py` - Derived metrics calculation (win rate, profit factor, Sharpe, etc.)

### Output Files

All files are written to `logs/`:

- `signals_v2.jsonl` - Every signal (accepted and rejected) with complete feature snapshot
- `trades_v2.jsonl` - Every completed trade with full metrics
- `equity_snapshots_v2.jsonl` - Portfolio state snapshots
- `signal_trade_links.jsonl` - Signal-to-trade linkage records
- `stats_by_symbol.json` (legacy) - Aggregated per-symbol statistics
- `stats_by_confidence.json` (legacy) - Aggregated per-confidence statistics

## Schema

### Signal Record

```json
{
  "signal_id": "unique id",
  "timestamp": 1788785301.0,
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "direction": "long",
  "signal_score": 0.75,
  "strategy_version": "v7_v2_professional_stats_2026-09-07",
  "model_version": "catboost_v1",
  "feature_version": "v2",
  "decision": "ACCEPTED",
  "decision_reason": "All filters passed",
  "decision_timestamp": 1788785301.0,
  "market_regime": "trend",
  "volatility_regime": "low",
  "trend_regime": "up",
  "price_at_signal": 50000.0,
  "full_features": { ... },
  "trade_id": null
}
```

### Trade Record

```json
{
  "trade_id": "unique id",
  "signal_id": "linked signal id",
  "strategy_version": "...",
  "model_version": "...",
  "feature_version": "...",
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "side": "long",
  "signal_timestamp": 1788785000.0,
  "entry_timestamp": 1788785001.0,
  "exit_timestamp": 1788785291.0,
  "entry_price": 50000.0,
  "exit_price": 50100.0,
  "quantity": 0.2,
  "stop_loss": 49800.0,
  "take_profit": 50200.0,
  "exit_reason": "tp1_full",
  "holding_time": 290.0,
  "gross_pnl": 20.0,
  "commission": 10.0,
  "funding": 1.0,
  "slippage": 0.0,
  "spread_cost": 0.0,
  "net_pnl": 8.0,
  "return_pct": 0.2,
  "risk_amount": 200.0,
  "r_multiple": 0.04,
  "mae": -50.0,
  "mae_pct": -0.1,
  "mae_r": -0.25,
  "mfe": 100.0,
  "mfe_pct": 0.2,
  "mfe_r": 0.4,
  "equity_at_entry": 100000.0,
  "equity_at_exit": 100008.0
}
```

### Equity Snapshot

```json
{
  "timestamp": 1788785301.0,
  "balance": 100000.0,
  "equity": 100000.0,
  "realized_pnl": 0.0,
  "unrealized_pnl": 0.0,
  "open_positions": 0,
  "gross_exposure": 0.0,
  "net_exposure": 0.0,
  "drawdown": 0.0,
  "drawdown_pct": 0.0,
  "peak_equity": 100000.0
}
```

## Usage

### Running Tests

```bash
python test_v2_stats.py
```

### Analyzing Results

```bash
python analyze_v2_stats.py
```

### Running the Bot

The bot now automatically logs to v2 files. No additional configuration needed.

```bash
python selective_ml_bot.py --config config_scanner.yaml
```

## Key Improvements

1. **Complete signal logging** - Every signal is logged, not just executed ones
2. **Full feature snapshots** - All model features at decision time are preserved
3. **Signal-to-trade linkage** - Each trade is linked to the originating signal
4. **MAE/MFE tracking** - Maximum adverse and favorable excursion metrics
5. **Equity curve** - Complete portfolio state snapshots
6. **Data quality** - Validation of all records
7. **Advanced metrics** - Comprehensive performance and risk metrics
8. **Version control** - All records include strategy, model, and feature versions
9. **Clean slate** - New files do not interfere with old data

## Backwards Compatibility

The new system writes to separate files (`*_v2.jsonl`) and does not modify or delete existing `trades.jsonl`, `signal_log.csv`, or other legacy files. Old data is preserved and can still be analyzed with old scripts.