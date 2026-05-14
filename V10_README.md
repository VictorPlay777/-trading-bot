# V10 Research Framework

**Goal: NOT max PnL. Goal: data, statistical significance, edge discovery.**

V10 is a research platform built on top of the V9.1 trading core. It logs every
signal (allowed and rejected), shadow-trades the rejects, tracks MFE/MAE in
R-units for every real position, and snapshots model features at entry.

---

## Architecture

```
selective_ml_bot_v10.py        # entrypoint (subclass of SelectiveMLBot)
selective_config_v10.py        # V10ProductionConfig
v10_research/                  # research helpers
  signal_logger.py             # all signals -> signals_all.jsonl
  shadow_tracker.py            # virtual trades for rejected signals
  mfe_mae_tracker.py           # MFE/MAE in R-units per real trade
  feature_snapshot.py          # features frozen on entry, content-hashed
  universe_filter.py           # TOP-40 by volume * volatility
v10_analytics.py               # post-hoc CLI analysis
run_v10_forever.sh             # supervisor wrapper
restart_v10.sh                 # restart helper
stop_v9_for_v10.sh             # safe stop of v9.1 before switching
```

V9.1 (`selective_ml_bot.py`) is **untouched** behaviourally; we only added 4
no-op hook methods and 1 config-driven log path. V9.1 still runs identically
when used directly.

---

## Configuration highlights (`V10ProductionConfig`)

| Setting | Value | Why |
|---|---|---|
| `strategy_id` | `v10_research_2026-05-12` | Isolation from v7-v9 stats |
| `base_notional_usdt` | 10000 | Same as v9 for direct comparability |
| `force_leverage_1x` | True | Pure direction edge, no leverage skew |
| `min_confidence_long/short` | 0.75 | Acted on threshold; everything logged |
| `tp1_r` / `sl_atr_mult` | 0.5 / 0.5 | R:R = 1:1 |
| `single_tp_full_close` | True | One signal -> one trade -> one outcome |
| `allow_dca` / `allow_pyramiding` | False | Independence assumption |
| `paper_trade_all_signals` | True | Counterfactual data for rejects |
| `shadow_max_hold_sec` | 86400 (24h) | Cap memory on stale shadows |
| `mfe_mae_tracking` | True | TP/SL calibration |
| `feature_snapshot_on_entry` | True | Reproducibility |

Universe = TOP-40 by `log10(turnover_24h+1) * sqrt(range_24h_pct)`, refreshed hourly.

---

## Output files (all under `logs/v10/`)

```
logs/v10/
  signals_all.jsonl            # one row per evaluated signal
  trades_v10.jsonl             # real trades + MFE/MAE/feature_hash/exit_r
  shadow_trades.jsonl          # virtual trades for rejected signals
  feature_snapshots/<hash>.json # frozen feature payloads
  last_state.json              # V10 persistent state (isolated)
  health.json                  # V10 heartbeat
  strategies/<strategy_id>.json # config snapshot
```

`signals_all.jsonl` schema:
```json
{
  "ts": 1778593068.83,
  "symbol": "SAGAUSDT",
  "side": "long",
  "confidence": 0.82,
  "score": 0.71,
  "ev": 0.012,
  "regime": "trend",
  "atr": 0.0012,
  "atr_pct": 0.018,
  "spread_bps": 3.2,
  "volume_24h": 28500000.0,
  "funding_rate": 0.0001,
  "btc_trend": "up",
  "allow": false,
  "reject_reason": "cooldown",
  "size_mult": 1.0
}
```

`trades_v10.jsonl` adds (vs v9 trades.jsonl):
```json
{
  "strategy_id": "v10_research_2026-05-12",
  "v10_trade_id": "ab12cd34...",
  "v10_feature_hash": "abc12345...",
  "mfe_r": 2.81,
  "mae_r": -0.72,
  "mfe_price": 0.03489,
  "mae_price": 0.03182,
  "exit_r": 1.00,
  "excursion_samples": 124
}
```

`shadow_trades.jsonl` schema:
```json
{
  "shadow_id": "f3a1...",
  "symbol": "BTCUSDT",
  "side": "short",
  "entry_price": 95234.0,
  "stop_loss_price": 95710.2,
  "take_profit_price": 94757.8,
  "confidence": 0.62,
  "regime": "chop",
  "reject_reason": "low_confidence",
  "outcome": "tp",
  "exit_r": 1.0,
  "mfe_r": 1.12,
  "mae_r": -0.58
}
```

---

## Switching from V9.1 to V10 (server-side)

**Important: V10 stats must be ISOLATED. Do not run V9 and V10 simultaneously.**

Server: `svy1990@111.88.150.44`

### Option A: One-shot deploy from Windows (recommended)

From `C:\trading-bot` in cmd / PowerShell:

```
deploy_v10.bat
```

This will SCP all v10 files, copy them into `ml_bot/`, chmod the shell scripts,
and run a syntax check on the server. After it finishes:

```bash
ssh svy1990@111.88.150.44
cd ~/-trading-bot

# 1. Stop V9.1 cleanly
bash stop_v9_for_v10.sh

# 2. ON BYBIT WEB UI: manually close ALL open positions and record balance.
#    Take a screenshot — that's the V10 baseline.

# 3. Start V10
bash restart_v10.sh

# 4. Verify
ps -ef | grep -E "v10|selective" | grep -v grep
sleep 30 && tail -20 logs/ml.log | grep V10
ls -la logs/v10/
wc -l logs/v10/signals_all.jsonl   # should grow quickly
```

### Option B: Manual SCP (one file at a time)

If `deploy_v10.bat` cannot be used:

```
scp selective_ml_bot.py            svy1990@111.88.150.44:~/-trading-bot/
scp selective_ml_bot_v10.py        svy1990@111.88.150.44:~/-trading-bot/
scp selective_config_v10.py        svy1990@111.88.150.44:~/-trading-bot/
scp run_v10_forever.sh             svy1990@111.88.150.44:~/-trading-bot/
scp restart_v10.sh                 svy1990@111.88.150.44:~/-trading-bot/
scp stop_v9_for_v10.sh             svy1990@111.88.150.44:~/-trading-bot/
scp v10_analytics.py               svy1990@111.88.150.44:~/-trading-bot/
scp V10_README.md                  svy1990@111.88.150.44:~/-trading-bot/
scp -r v10_research                svy1990@111.88.150.44:~/-trading-bot/
```

Then SSH in and finish setup:

```
ssh svy1990@111.88.150.44
cd ~/-trading-bot
cp selective_ml_bot.py selective_ml_bot_v10.py selective_config_v10.py ml_bot/
rm -rf ml_bot/v10_research && cp -r v10_research ml_bot/
chmod +x run_v10_forever.sh restart_v10.sh stop_v9_for_v10.sh
mkdir -p logs/v10 ml_bot/logs/v10
python3 -m py_compile ml_bot/selective_ml_bot_v10.py && echo OK
```

Then run `stop_v9_for_v10.sh` and `restart_v10.sh` as in Option A.

---

## Live monitoring

```bash
# Heartbeat
grep "[V10]" logs/ml.log | tail -10

# Signal flow (every evaluation)
tail -f logs/v10/signals_all.jsonl | head -30

# Real entries
grep "[V10 OPEN]" logs/ml.log

# Real closes (with MFE/MAE)
tail -1 logs/v10/trades_v10.jsonl | python3 -m json.tool

# Shadow trade activity
wc -l logs/v10/shadow_trades.jsonl
```

---

## Analytics

After at least 100-200 real trades have accumulated:

```bash
# Quick health check
python3 v10_analytics.py health

# Full report
python3 v10_analytics.py all

# Specific cuts
python3 v10_analytics.py summary
python3 v10_analytics.py by-confidence    # WR per conf bucket 0.50-0.55..0.95+
python3 v10_analytics.py by-symbol        # Worst symbols by total PnL
python3 v10_analytics.py by-regime        # Trend vs chop vs panic
python3 v10_analytics.py by-side          # Long vs short
python3 v10_analytics.py mfe-mae          # TP/SL calibration data
python3 v10_analytics.py shadow           # Rejected signal outcomes
python3 v10_analytics.py rejects          # What is filtering us most?
```

---

## Discipline rules

1. **Do not change config mid-run.** Bump `strategy_id` if you change anything.
   Statistical significance requires a stable parameter set across 300-500 trades.
2. **Never delete `trades_v10.jsonl` or `signals_all.jsonl`** without backup.
3. **Read `mfe-mae` weekly.** Avg MFE >> avg exit means TP too tight.
4. **Read `by-symbol` weekly.** Symbols with PF < 0.6 over n>=20 trades are
   candidates for blacklist (in V11).
5. **Read `shadow` weekly.** If a reject_reason has WR > 60% on 50+ shadows,
   reconsider that gate.
6. **Do not act on n < 30 trades.** Sample size theatre.

---

## What V10 should answer

Run for 2-4 weeks, then this CLI should produce evidence to answer:

| Question | Source |
|---|---|
| Which confidence buckets are profitable? | `by-confidence` |
| Which symbols are systematically losing? | `by-symbol` |
| Are shorts as profitable as longs? | `by-side` |
| Is TP=0.5 ATR too tight? | `mfe-mae` (avg MFE / TP ratio) |
| Is SL=0.5 ATR too tight? | `mfe-mae` (deep MAE %) |
| Which gates are removing profitable trades? | `shadow` |
| Which reject_reasons fire most? | `rejects` |
| Does regime matter? | `by-regime` |
