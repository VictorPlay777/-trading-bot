import json, csv, os
from collections import defaultdict, Counter

os.chdir('c:\\trading-bot')

print('=' * 100)
print('V7 COMPREHENSIVE ANALYSIS')
print('=' * 100)

# SIGNAL LOG ANALYSIS
total = 0
allowed = []
with open('ml_bot/logs/signal_log.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        if row['allow_entry'] == 'True':
            allowed.append(row)

print(f'\nTotal signals logged: {total}')
print(f'Allowed signals: {len(allowed)}')

by_symbol = defaultdict(list)
for s in allowed:
    by_symbol[s['symbol']].append(s)

print(f'\nUnique symbols with signals: {len(by_symbol)}')

print('\n' + '-' * 80)
print('SIGNALS BY SYMBOL')
print('-' * 80)
cols = f'{"Symbol":<20} {"Signals":<10} {"Long":<8} {"Short":<8} {"AvgConf":<10} {"AvgEV":<12} {"Regime":<15}'
print(cols)
print('-' * 80)

for sym in sorted(by_symbol.keys()):
    sigs = by_symbol[sym]
    long_c = sum(1 for s in sigs if s['direction'] == 'long')
    short_c = sum(1 for s in sigs if s['direction'] == 'short')
    avg_c = sum(float(s['confidence']) for s in sigs) / len(sigs)
    avg_e = sum(float(s['ev']) for s in sigs) / len(sigs)
    main_reg = Counter(s['regime'] for s in sigs).most_common(1)[0][0]
    print(f'{sym:<20} {len(sigs):<10} {long_c:<8} {short_c:<8} {avg_c:<10.3f} {avg_e:<12.6f} {main_reg:<15}')

# OVERALL STATS
print('\n' + '=' * 100)
print('OVERALL STATISTICS')
print('=' * 100)

all_confs = [float(s['confidence']) for s in allowed]
all_evs = [float(s['ev']) for s in allowed]

longs = sum(1 for s in allowed if s['direction'] == 'long')
shorts = sum(1 for s in allowed if s['direction'] == 'short')
print(f'\nLong signals: {longs} ({longs/len(allowed)*100:.1f}%)')
print(f'Short signals: {shorts} ({shorts/len(allowed)*100:.1f}%)')
print(f'Average confidence: {sum(all_confs)/len(all_confs):.3f}')
print(f'Average EV: {sum(all_evs)/len(all_evs):.6f}')

print('\nRegime distribution:')
for r, c in Counter(s['regime'] for s in allowed).most_common():
    print(f'  {r}: {c} ({c/len(allowed)*100:.1f}%)')

print('\nReason distribution:')
for r, c in Counter(s['reason'] for s in allowed).most_common():
    print(f'  {r}: {c} ({c/len(allowed)*100:.1f}%)')

# TRADE ANALYSIS
print('\n' + '=' * 100)
print('TRADE ANALYSIS FROM trades.jsonl')
print('=' * 100)

trades = []
with open('ml_bot/logs/trades.jsonl', 'r') as f:
    for line in f:
        try:
            trade = json.loads(line.strip())
            trades.append(trade)
        except:
            pass

print(f'\nTotal trades: {len(trades)}')

wins = [t for t in trades if t.get('realized_pnl_net', 0) > 0]
losses = [t for t in trades if t.get('realized_pnl_net', 0) < 0]
total_pnl = sum(t.get('realized_pnl_net', 0) for t in trades)

print(f'Winning trades: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)')
print(f'Losing trades: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)')
print(f'Total realized PnL: {total_pnl:.2f} USDT')
print(f'Average PnL per trade: {total_pnl/len(trades):.2f} USDT')

pnls = [t.get('realized_pnl_net', 0) for t in trades]
print(f'Best trade: {max(pnls):.2f} USDT')
print(f'Worst trade: {min(pnls):.2f} USDT')

print('\n' + '-' * 80)
print('WIN RATE BY SYMBOL')
print('-' * 80)
cols2 = f'{"Symbol":<20} {"Trades":<8} {"Wins":<6} {"Losses":<8} {"WR%":<8} {"TotalPnL":<12} {"AvgPnL":<10}'
print(cols2)
print('-' * 80)

by_sym_t = defaultdict(list)
for t in trades:
    by_sym_t[t.get('symbol', '?')].append(t)

symbol_stats = []
for sym in sorted(by_sym_t.keys()):
    st = by_sym_t[sym]
    w = sum(1 for t in st if t.get('realized_pnl_net', 0) > 0)
    l = sum(1 for t in st if t.get('realized_pnl_net', 0) < 0)
    wr = w / len(st) * 100
    tp = sum(t.get('realized_pnl_net', 0) for t in st)
    symbol_stats.append({'sym': sym, 'trades': len(st), 'wins': w, 'losses': l, 'wr': wr, 'pnl': tp})
    print(f'{sym:<20} {len(st):<8} {w:<6} {l:<8} {wr:<8.1f}% {tp:<12.2f} {tp/len(st):<10.2f}')

# TOP AND WORST
sorted_stats = sorted(symbol_stats, key=lambda x: x['wr'], reverse=True)
print('\n' + '=' * 100)
print('TOP 5 BEST SYMBOLS')
print('=' * 100)
for s in sorted_stats[:5]:
    print(f'  + {s["sym"]}: {s["wr"]:.1f}% WR, {s["pnl"]:.2f} USDT ({s["trades"]} trades)')

print('\n' + '=' * 100)
print('TOP 5 WORST SYMBOLS')
print('=' * 100)
for s in sorted_stats[-5:]:
    print(f'  - {s["sym"]}: {s["wr"]:.1f}% WR, {s["pnl"]:.2f} USDT ({s["trades"]} trades)')

# EXIT LOGIC ANALYSIS
print('\n' + '=' * 100)
print('EXIT LOGIC ANALYSIS (PARTIAL CLOSES)')
print('=' * 100)

exit_counts = [len(t.get('exit_reasons', [])) for t in trades]
sl_trades = sum(1 for t in trades if any(r['reason'] == 'stop_loss' for r in t.get('exit_reasons', [])))
partial_trades = sum(1 for e in exit_counts if e > 2)

print(f'\nTotal trades analyzed for exits: {len(trades)}')
print(f'Trades with stop-loss: {sl_trades} ({sl_trades/len(trades)*100:.1f}%)')
print(f'Trades with partial TP (>2 exits): {partial_trades} ({partial_trades/len(trades)*100:.1f}%)')
print(f'Average exit events per trade: {sum(exit_counts)/len(exit_counts):.1f}')
print(f'Median exit events: {sorted(exit_counts)[len(exit_counts)//2]}')
print(f'Maximum exit events in single trade: {max(exit_counts)}')

print('\nExit count distribution:')
cnt_dist = Counter(exit_counts)
for k in sorted(cnt_dist.keys()):
    print(f'  {k} exits: {cnt_dist[k]} trades ({cnt_dist[k]/len(trades)*100:.1f}%)')

print('\n' + '=' * 100)
print('DETAILED EXAMPLES - TRADES WITH MOST PARTIAL EXITS')
print('=' * 100)

sorted_by_exits = sorted(trades, key=lambda t: len(t.get('exit_reasons', [])), reverse=True)
for i, trade in enumerate(sorted_by_exits[:3]):
    print(f'\n{i+1}. {trade.get("trade_id", "?")}')
    print(f'   Symbol: {trade.get("symbol", "?")} | Direction: {trade.get("direction", "?")}')
    print(f'   Entry: {trade.get("entry_price", "?")} | Qty total: {trade.get("qty_total", "?")}')
    print(f'   Duration: {trade.get("duration_sec", 0):.0f}s ({trade.get("duration_sec", 0)/60:.1f} min)')
    print(f'   Net PnL: {trade.get("realized_pnl_net", 0):.2f} USDT')

    exit_summary = trade.get('exit_reason_qty_sum', {})
    total_qty = float(trade.get('qty_total', 0)) or 1
    print(f'   Exit breakdown:')
    for reason, qty in sorted(exit_summary.items()):
        print(f'     {reason}: {qty:.0f} units ({qty/total_qty*100:.1f}%)')

print('\n' + '=' * 100)
print('ANALYSIS COMPLETE')
print('=' * 100)
</｜｜DSML｜｜parameter>
<task_progress>
- [x] Изучить текущую структуру v7 и его логи
- [x] Создать скрипт для анализа всех данных
- [ ] Запустить анализ и получить статистику
- [ ] Проанализировать винрейт по каждой монете
- [ ] Определить прибыльные и убыточные сигналы
- [ ] Изучить логику закрытия позиций
- [ ] Выяснить причину частичного закрытия позиций
- [ ] Создать детальный отчет со статистикой
</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>