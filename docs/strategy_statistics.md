# Strategy Statistics / Research System

Цель: накопление данных для ответа на вопрос — *какой тип сигнала в каком
рыночном режиме имеет положительный edge*. Система не меняет торговую логику.

## Уровни данных

### 1. Signal snapshots (`signal_snapshots` table, `data/dashboard.db`)

Записывается **каждый** оценённый сигнал — и открывший сделку, и отклонённый.
Также записываются tier1-отказы (до ML-оценки) с `allowed=0` и NULL в ML-полях.

| Группа | Поля |
|---|---|
| Идентификация | `signal_id`, `symbol`, `direction`, `timeframe`, `ts`, `strategy_id` |
| ML | `confidence`, `probability`, `agreement`, `h3_dir/h3_conf`, `h5_dir/h5_conf`, `h10_dir/h10_conf` |
| Режим | `regime` (`trend/breakout/chop/panic`), `regime_confidence`, `trend_score`, `breakout_score`, `chop_score`, `panic_score` — **NULL**: классификатор не выдаёт скоры |
| Волатильность | `atr`, `atr_pct` (ATR/price×100), `realized_volatility` (std доходностей за 20 баров = `vol_compression`) |
| Тренд | `adx` (ADX-14, считается на кэшированных свечах), `ema_distance` (close−EMA50)/close, `trend_strength` (ema_slope_50) |
| Объём | `volume`, `rel_volume` (volume/MA20) |
| Стакан | `spread_bps`, `spread_pct`, `bid_depth`, `ask_depth`, `total_depth`, `imbalance` |
| Деривативы | `funding_rate`, `open_interest`, `oi_change` (относительное изменение к прошлому циклу; NULL на первом), `basis` — **NULL: недоступен** |
| Price action | `pc_1m/5m/15m/1h`, `hl_range` (high−low последнего бара / close), `wick_ratio` (24h range/last из тикера) |
| Качество | `quality_score`, `uncertainty`, `ev`, `edge_score` (probability − 0.5) |
| Решение | `allowed`, `rejection_reason` (первый блокер — как в `allowed()`), `rejection_reasons_json` (**все** причины), `size_mult` |
| Бакеты | `confidence_bucket`, `adx_bucket`, `atr_bucket`, `volume_bucket`, `volatility_bucket`, `funding_bucket`, `oi_bucket`, `depth_bucket` |
| Время | `hour_utc`, `dow_utc` |
| Доп. | `extra_json` — сырые фичи FeatureStore |

### 2. Trades (`trades` table)

Дополнительно к существующим полям: `signal_snapshot_id` (FK к
signal_snapshots.id), `signal_id`, `mae`, `mfe`, `mae_r`, `mfe_r`,
`gross_pnl`, `result` (WIN/LOSS/BREAKEVEN по net PnL), `size_mult`.
`r_multiple` = PnL_R уже существовал.

## Бакеты

- **confidence**: `<0.50`, `0.50-0.55`, `0.55-0.60`, `0.60-0.65`, `0.65-0.70`, `0.70-0.75`, `0.75-0.80`, `0.80-0.85`, `0.85-0.90`, `0.90+`
- **ADX**: `<10`, `10-15`, `15-20`, `20-25`, `25-30`, `30-40`, `40+`
- **ATR%**: `low <0.15%`, `normal 0.15-0.4%`, `high 0.4-0.8%`, `extreme ≥0.8%`
- **Volume** (rel_volume): `low <0.7`, `normal 0.7-1.3`, `high 1.3-2.5`, `extreme ≥2.5`
- **Funding**: `strong_negative ≤-0.05%`, `negative <-0.01%`, `neutral ±0.01%`, `positive >0.01%`, `strong_positive ≥0.05%`
- **OI change**: `strong_falling <-2%`, `falling <-0.5%`, `neutral ±0.5%`, `rising >0.5%`, `strong_rising >2%`
- **Depth**: `<2k`, `2k-7k`, `7k-20k`, `20k-50k`, `50k+`
- **Regime**: `trend`, `breakout`, `chop`, `panic` (из RegimeClassifier)

## Метрики

- **Expectancy** = средний net PnL на сделку (USDT); **Expectancy R** = средний `r_multiple` = PnL / риск-до-SL.
- **Profit factor** = сумма выигрышей / |сумма проигрышей|; NULL если нет проигрышей.
- **WIN** = net_pnl > 0, **LOSS** < 0, **BREAKEVEN** = 0.
- **MAE/MFE** — максимум adverse/favorable excursion от entry (mark price каждый цикл ~2с); `MAE_R = MAE / risk_amount`, `risk_amount = |entry − SL| × qty`.
- **Sharpe/Sortino** считаются на распределении per-trade PnL (не аннуализированы) — только при n≥2; интерпретировать осторожно.
- **Max drawdown** — по кумулятивному PnL закрытых сделок.

## Sample size

| n | Метка |
|---|---|
| <30 | INSUFFICIENT SAMPLE — выводы делать нельзя |
| 30–100 | LOW CONFIDENCE |
| 100–300 | MODERATE |
| 300+ | STRONGER SAMPLE |

Это визуальный индикатор надёжности, не статистический критерий.

## Look-ahead

Все поля снапшота вычисляются только из данных на момент сигнала
(OHLCV до текущего бара, текущий стакан, текущий funding/OI). `oi_change`
использует значение OI предыдущего цикла — прошлое, не будущее.
Модель переобучается на строках `[60, len−h−1]` — без заглядывания вперёд
по таргету.

## Signal → trade linkage

`signal_snapshot_id` (autoincrement id строки `signal_snapshots`) сохраняется
в `sig._dash_signal_id` при записи сигнала, переносится в `signal_meta`
позиции и записывается в `trades.signal_snapshot_id` при закрытии.
Также `signal_id` (uuid из SignalLogger) дублирует связь для файловых логов.

## API

Все эндпоинты требуют авторизации, префикс `/api/research/`:

- `overview` — сводка (signals, trades, WR, PF, expectancy, drawdown, Sharpe/Sortino)
- `direction` — статистика long/short/all
- `confidence` — по бакетам confidence
- `regime` — по режимам
- `regime-direction` — матрица 4×2
- `confidence-regime` — пересечение
- `symbols` — по символам (+ long/short WR)
- `filters` — воронка фильтров: сколько сигналов блокирует каждый фильтр, сколько раз он был единственной причиной
- `buckets?field=atr_bucket|volume_bucket|funding_bucket|oi_bucket|depth_bucket|adx_bucket` — произвольные бакеты
- `time` — час/день недели × direction/regime
- `edge-matrix?min_trades=N` — комбинации regime×direction×conf×adx×atr, сортировка по expectancy R; статусы PROMISING/BAD/NEUTRAL/INSUFFICIENT
- `signals` — сырые снапшоты
- `equity-curve` — equity + кумулятивный PnL

UI: страница **Research** (`/research`) в дашборде, вкладки по разделам выше.

## Counterfactual outcomes (`signal_outcomes`)

Для **каждого** сигнала (включая отклонённые) через ~10 баров после сигнала
бот вычисляет гипотетический исход и пишет в `signal_outcomes`:

- `future_return_3/5/10` — знаковая доходность (long: close−entry, short: entry−close)
- `tp_hit`/`sl_hit`/`tp_first` — сработал бы гипотетический TP=SL=0.5×ATR, что первым
- `cf_mfe`/`cf_mae` — экскурсии за 10 баров
- `cf_r` — исход в R (+1 если TP первым, −1 если SL)

Resolver (`_resolve_signal_outcomes`) работает в конце цикла, читает только
исторические свечи после `ts` сигнала. Результаты **никогда** не попадают в
decision path — это чисто исследовательская таблица (look-ahead исключён).

Дополнительные поля снапшота: `entry_price`, `probability_long/short`,
`predicted_direction`, `di_plus`/`di_minus`, `ema_slope`, `ret_1/3/5/10`,
`momentum`, `distance_from_high/low` (vs 20-бар high/low), `volume_change`.

## Edge discovery (`/api/research/*`)

- `edge-discovery` — многоуровневый анализ по всем сигналам с исходом:
  level 1 (факторы), level 2 (пары), level 3 (комбинации), top/worst edges.
  Метрика — `expectancy_r` контрфакта. Стабильность: in-sample (первая половина
  по времени) vs out-of-sample (вторая), `symbol_breadth` = доля символов с
  положительным expectancy (символы с n≥3).
- `symbol-edge` — матрица символ × направление (контрфакт).
- `filter-value` — для каждого rejection reason: сколько заблокировано и
  контрфактический исход (would_win/lose, cf_expectancy_r, вердикт
  FILTER HELPS/HURTS).
- `trade-explain?trade_id=` — чеклист факторов сделки (conf, agreement,
  regime, ADX, rel volume, orderbook, funding, ATR, spread).
- `edge-report` — сводка по периодам 24h/7d/all + top/worst conditions.

## Evidence labels

`INSUFFICIENT DATA` (<30) · `WEAK EVIDENCE` · `POSSIBLE EDGE` ·
`OBSERVED EDGE` (n≥100 + OOS знак совпадает + breadth≥50%) · `NEGATIVE EDGE` ·
`NO EVIDENCE`. Метки не утверждают причинность — только наблюдаемую корреляцию.

## Что нельзя делать по этим данным

- Не делать выводов по выборкам <30 сделок.
- Не сравнивать expectancy отклонённых сигналов с исполненными — у отклонённых нет outcome (контрфактический анализ не реализован).
- Фильтр-отчёт показывает, **сколько** сигналов режет фильтр и был ли он единственной причиной; оценка «полезен ли фильтр» — по сравнению метрик сделок, прошедших/не прошедших условие фильтра, в разрезах (buckets, edge-matrix).
- Sharpe/Sortino per-trade — не годовые, не сопоставимы с классическими.
