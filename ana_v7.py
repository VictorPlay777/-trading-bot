import json, csv, os
from collections import defaultdict, Counter

os.chdir('c:\\trading-bot')

total = 0
allowed = []
with open('ml_bot/logs/signal_log.csv') as f:
    for row in csv.DictReader(f):
        total += 1
        if row['allow_entry'] == 'True':
            allowed.append(row)

print(f'Total signals: {total}')
print(f'Allowed signals: {len(allowed)}')

by_sym = defaultdict(list)
for s in allowed:
    by_sym[s['symbol']].append(s)
print(f'Unique symbols: {len(by_sym)}')

trades = []
with open('ml_bot/logs/trades.jsonl') as f:
    for line in f:
        try:
            trades.append(json.loads(line.strip()))
        except: pass

print(f'\nTotal trades: {len(trades)}')
wins = sum(1 for t in trades if t.get('realized_pnl_net',0)>0)
losses = sum(1 for t in trades if t.get('realized_pnl_net',0)<0)
tp = sum(t.get('realized_pnl_net',0) for t in trades)
print(f'Wins: {wins} ({wins/len(trades)*100:.1f}%)')
print(f'Losses: {losses} ({losses/len(trades)*100:.1f}%)')
print(f'Total PnL: {tp:.2f} USDT')
print(f'Avg PnL: {tp/len(trades):.2f} USDT')

by_st = defaultdict(list)
for t in trades:
    by_st[t.get('symbol','?')].append(t)

print('\nWin Rate by Symbol:')
for sym in sorted(by_st):
    st = by_st[sym]
    w = sum(1 for t in st if t.get('realized_pnl_net',0)>0)
    l = sum(1 for t in st if t.get('realized_pnl_net',0)<0)
    wr = w/len(st)*100
    pt = sum(t.get('realized_pnl_net',0) for t in st)
    print(f'{sym:20s} {len(st):3d}t {w:3d}W {l:3d}L {wr:5.1f}% PnL:{pt:8.2f}')

exits = [len(t.get('exit_reasons',[])) for t in trades]
sl = sum(1 for t in trades if any(r['reason']=='stop_loss' for r in t.get('exit_reasons',[])))
ptp = sum(1 for e in exits if e>2)
print(f'\nStop-loss: {sl} ({sl/len(trades)*100:.1f}%)')
print(f'Partial TP: {ptp} ({ptp/len(trades)*100:.1f}%)')
print(f'Avg exits: {sum(exits)/len(exits):.1f}, Max exits: {max(exits)}')
