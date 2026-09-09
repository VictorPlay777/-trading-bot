@"C:\Users\svy19\AppData\Local\Programs\Python\Python311\python.exe" -c "import json, csv, os
from collections import defaultdict, Counter
os.chdir('c:\\trading-bot')
total = 0
allowed = []
with open('ml_bot/logs/signal_log.csv') as f:
    for row in csv.DictReader(f):
        total += 1
        if row['allow_entry'] == 'True':
            allowed.append(row)
print('Total signals:', total)
print('Allowed signals:', len(allowed))
by_sym = defaultdict(list)
for s in allowed:
    by_sym[s['symbol']].append(s)
print('Unique symbols:', len(by_sym))
for sym in sorted(by_sym)[:10]:
    sigs = by_sym[sym]
    print(f'{sym}: {len(sigs)} signals')
trades = []
with open('ml_bot/logs/trades.jsonl') as f:
    for line in f:
        try:
            trades.append(json.loads(line.strip()))
        except:
            pass
print()
print('Total trades:', len(trades))
wins = sum(1 for t in trades if t.get('realized_pnl_net', 0) > 0)
losses = sum(1 for t in trades if t.get('realized_pnl_net', 0) < 0)
total_pnl = sum(t.get('realized_pnl_net', 0) for t in trades)
print(f'Wins: {wins} ({wins/len(trades)*100:.1f}%)')
print(f'Losses: {losses} ({losses/len(trades)*100:.1f}%)')
print(f'Total PnL: {total_pnl:.2f} USDT')
print(f'Avg PnL: {total_pnl/len(trades):.2f} USDT')
print()
by_st = defaultdict(list)
for t in trades:
    by_st[t.get('symbol', '?')].append(t)
print('Win Rate by Symbol:')
for sym in sorted(by_st):
    st = by_st[sym]
    w = sum(1 for t in st if t.get('realized_pnl_net', 0) > 0)
    l = sum(1 for t in st if t.get('realized_pnl_net', 0) < 0)
    wr = w/len(st)*100
    tp = sum(t.get('realized_pnl_net', 0) for t in st)
    print(f'{sym:20s} {len(st):4d} trades {w:3d}W {l:3d}L {wr:5.1f}% PnL:{tp:8.2f}')
exits = [len(t.get('exit_reasons',[])) for t in trades]
sl = sum(1 for t in trades if any(r['reason']=='stop_loss' for r in t.get('exit_reasons',[])))
pt = sum(1 for e in exits if e > 2)
print()
print(f'Stop-loss: {sl} ({sl/len(trades)*100:.1f}%)')
print(f'Partial TP: {pt} ({pt/len(trades)*100:.1f}%)')
print(f'Avg exits: {sum(exits)/len(exits):.1f}, Max: {max(exits)}')"</｜｜DSML｜｜parameter>
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