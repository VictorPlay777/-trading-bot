#!/usr/bin/env python3
"""Full analysis of v7_stats_collection_buckets strategy"""
import json, csv
from datetime import datetime, timezone
from collections import Counter, defaultdict

# Load trades
trades = [json.loads(l) for l in open('ml_bot/logs/trades.jsonl') if l.strip()]
print(f'Всего сделок: {len(trades)}')

# First trade ever
first = trades[0]
ts = first.get('opened_ts', first.get('ts', 0))
print(f'Первая сделка: {first.get("symbol","?")} {datetime.fromtimestamp(ts, tz=timezone.utc)} стратегия={first.get("strategy_id","?")}')

# By day
by_day = defaultdict(list)
for t in trades:
    dt = datetime.fromtimestamp(t.get('opened_ts', t.get('ts', 0)), tz=timezone.utc)
    by_day[dt.strftime('%Y-%m-%d')].append(t)

print('\n=== ПО ДНЯМ ===')
total_pnl_all = 0
for day in sorted(by_day.keys()):
    dtrades = by_day[day]
    pnls = [t.get('realized_pnl_net', 0) for t in dtrades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    total = sum(pnls)
    total_pnl_all += total
    wr = wins / max(len(dtrades), 1) * 100
    print(f'  {day}: {len(dtrades):3d} trades | W={wins:2d} L={losses:2d} WR={wr:5.1f}% | PnL=${total:9.2f}')
print(f'  {"ИТОГО":28s} PnL=${total_pnl_all:.2f}')

# Strategies
strategies = Counter(t.get('strategy_id', '?') for t in trades)
print('\n=== СТРАТЕГИИ ===')
for s, c in strategies.most_common():
    pnls = [t.get('realized_pnl_net', 0) for t in trades if t.get('strategy_id') == s]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    print(f'  {s}: {c} trades, WR={wins/max(c,1)*100:.1f}%, PnL=${total:.2f}')

# May 8-9 analysis
may8_9 = [t for t in trades if datetime.fromtimestamp(t.get('opened_ts',0), tz=timezone.utc).day >= 8]
print(f'\n=== МАЙ 8-9: {len(may8_9)} СДЕЛОК ===')

# By symbol
by_sym = defaultdict(list)
for t in may8_9:
    by_sym[t.get('symbol', '?')].append(t)

sym_stats = []
for sym, st in by_sym.items():
    pnls = [t.get('realized_pnl_net', 0) for t in st]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    total = sum(pnls)
    wr = wins / max(len(st), 1) * 100
    avg = total / max(len(st), 1)
    max_win = max(pnls) if pnls else 0
    max_loss = min(pnls) if pnls else 0
    sym_stats.append((total, sym, len(st), wr, avg, wins, losses, max_win, max_loss))

sym_stats.sort(reverse=True)

print(f'\n{"Symbol":15s} {"Cnt":4s} {"WR":6s} {"Wins":5s} {"Loss":5s} {"TotPnL":10s} {"Avg":9s} {"MaxWin":9s} {"MaxLoss":9s}')
print('-'*75)
grand_wins = grand_losses = cnt_all = 0
grand_pnl = 0.0
for total, sym, cnt, wr, avg, wins, losses, maxw, maxl in sym_stats:
    print(f'{sym:15s} {cnt:4d} {wr:5.1f}% {wins:5d} {losses:5d} ${total:8.2f} ${avg:7.2f} ${maxw:8.2f} ${maxl:8.2f}')
    grand_pnl += total
    grand_wins += wins
    grand_losses += losses
    cnt_all += cnt

print('-'*75)
print(f'{"TOTAL":15s} {cnt_all:4d} {grand_wins/max(cnt_all,1)*100:5.1f}% {grand_wins:5d} {grand_losses:5d} ${grand_pnl:8.2f}')

# By direction
dirs = defaultdict(lambda: {'cnt': 0, 'wins': 0, 'losses': 0, 'pnl': 0})
for t in may8_9:
    d = t.get('direction', '?')
    pnl = t.get('realized_pnl_net', 0)
    dirs[d]['cnt'] += 1
    dirs[d]['pnl'] += pnl
    if pnl > 0: dirs[d]['wins'] += 1
    elif pnl < 0: dirs[d]['losses'] += 1

print('\n=== ПО НАПРАВЛЕНИЯМ ===')
for d in sorted(dirs.keys()):
    st = dirs[d]
    wr = st['wins'] / max(st['cnt'], 1) * 100
    print(f'  {d:8s}: {st["cnt"]:3d} trades WR={wr:5.1f}% PnL=${st["pnl"]:9.2f}')

# Top 5 best and worst
pnl_list = [(t.get('symbol','?'), t.get('realized_pnl_net',0), t.get('direction','?'), datetime.fromtimestamp(t.get('opened_ts',0), tz=timezone.utc)) for t in may8_9]
pnl_list.sort(key=lambda x: x[1])
print('\n=== ТОП-5 ЛУЧШИХ СДЕЛОК ===')
for sym, pnl, dir, dt in pnl_list[-5:][::-1]:
    print(f'  +${pnl:9.2f} {sym:15s} {dir:5s} {dt}')
print('\n=== ТОП-5 ХУДШИХ СДЕЛОК ===')
for sym, pnl, dir, dt in pnl_list[:5]:
    print(f'  ${pnl:9.2f} {sym:15s} {dir:5s} {dt}')

# === ДОПОЛНИТЕЛЬНЫЙ АНАЛИЗ ===
print('\n' + '='*60)

# 1. Сигналы по confidence bands
print('\n=== СИГНАЛЫ ПО УРОВНЯМ CONFIDENCE ===')
sig_thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
sig_stats = {t: {'total':0, 'allowed':0} for t in sig_thresholds}
with open('ml_bot/logs/signal_log.csv') as f:
    for row in csv.DictReader(f):
        conf = float(row.get('confidence', 0))
        for t in sig_thresholds:
            if conf >= t:
                sig_stats[t]['total'] += 1
                if row.get('allow_entry', 'False') == 'True':
                    sig_stats[t]['allowed'] += 1

for t in sig_thresholds:
    st = sig_stats[t]
    pct = st['allowed']/max(st['total'],1)*100
    print(f'  conf>={t:.1f}: total={st["total"]:6d} allowed={st["allowed"]:5d} ({pct:.1f}%)')

# 2. Analyse allowed signals vs winrate
print('\n=== ALLOWED SIGNALS WINRATE (8-9 мая) ===')
allowed_ids = set()
with open('ml_bot/logs/signal_log.csv') as f:
    for row in csv.DictReader(f):
        ts = float(row.get('timestamp', 0))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if dt.day >= 8 and row.get('allow_entry', 'False') == 'True':
            allowed_ids.add(f'{row.get("symbol","?")}_{int(ts)}')

allowed_count = len(allowed_ids)
print(f'  Всего разрешённых сигналов: {allowed_count}')

# 3. V7 стратегия - только её
print('\n=== СТРАТЕГИЯ V7_STATS_COLLECTION - ДИНАМИКА ===')
v7_trades = [t for t in trades if 'v7_stats' in t.get('strategy_id','')]
by_day_v7 = defaultdict(list)
for t in v7_trades:
    dt = datetime.fromtimestamp(t.get('opened_ts', t.get('ts', 0)), tz=timezone.utc)
    by_day_v7[dt.strftime('%Y-%m-%d')].append(t)
v7_total_pnl = 0
for day in sorted(by_day_v7.keys()):
    dtrades = by_day_v7[day]
    pnls = [t.get('realized_pnl_net', 0) for t in dtrades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    total = sum(pnls)
    v7_total_pnl += total
    wr = wins / max(len(dtrades), 1) * 100
    print(f'  {day}: {len(dtrades):3d} trades WR={wr:5.1f}% PnL=${total:9.2f}')
print(f'  {"ВСЕГО":28s} PnL=${v7_total_pnl:.2f}')

# 4. PnL по символам с сортировкой по убыванию (топ-10 и худшие-10)
print('\n=== ТОП-10 МОНЕТ ПО PnL ===')
top10 = sym_stats[:10]
for total, sym, cnt, wr, avg, wins, losses, maxw, maxl in top10:
    print(f'  +{sym:15s} PnL=${total:9.2f} WR={wr:5.1f}% cnt={cnt}')
print('\n=== ХУДШИЕ-10 МОНЕТ ПО PnL ===')
bottom10 = sym_stats[-10:]
for total, sym, cnt, wr, avg, wins, losses, maxw, maxl in bottom10:
    print(f'  {sym:15s} PnL=${total:9.2f} WR={wr:5.1f}% cnt={cnt}')

# 5. Поиск баланса в логе супервизора
print('\n=== БАЛАНС ИЗ SUPERVISOR LOG (первое вхождение) ===')
with open('selective_ml_supervisor.log') as f:
    for i, line in enumerate(f):
        if 'totalEquity' in line or 'totalWalletBalance' in line:
            print(f'  {line[:300]}')
            if i > 3: break