#!/usr/bin/env python3
"""Quick v7 stats - no external deps, no imports that can hang"""
import json, csv, os, sys
from collections import defaultdict

os.chdir('c:\\trading-bot')

print('='*90)
print('V7 TRADES ANALYSIS')
print('='*90)

# === 1. TRADES from trades.jsonl ===
trades = []
try:
    with open('ml_bot/logs/trades.jsonl') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except:
                    pass
except FileNotFoundError:
    print("ERROR: ml_bot/logs/trades.jsonl not found!")

if not trades:
    print('NO TRADES FOUND')
else:
    print(f'Total trades: {len(trades)}')

    wins = sum(1 for t in trades if float(t.get('realized_pnl_net',0)) > 0)
    losses = sum(1 for t in trades if float(t.get('realized_pnl_net',0)) < 0)
    flat = sum(1 for t in trades if float(t.get('realized_pnl_net',0)) == 0)
    total_pnl = sum(float(t.get('realized_pnl_net',0)) for t in trades)

    print(f'Wins: {wins} ({wins/len(trades)*100:.1f}%)')
    print(f'Losses: {losses} ({losses/len(trades)*100:.1f}%)')
    print(f'Flat: {flat}')
    print(f'Total PnL: {total_pnl:.2f} USDT')
    print(f'Avg PnL: {total_pnl/len(trades):.2f} USDT')

    # PnL source distribution
    pnl_sources = defaultdict(int)
    for t in trades:
        pnl_sources[t.get('pnl_source','?')] += 1
    print(f'\nPnL sources: {dict(pnl_sources)}')

    # Largest trades
    sorted_pnl = sorted(trades, key=lambda t: float(t.get('realized_pnl_net',0)), reverse=True)
    print(f'\nTop 5 winners:')
    for t in sorted_pnl[:5]:
        print(f'  {t.get("symbol","?")} {t.get("direction","?")} PnL={float(t.get("realized_pnl_net",0)):.2f} src={t.get("pnl_source","?")}')

    print(f'\nTop 5 losers:')
    for t in sorted_pnl[-5:]:
        print(f'  {t.get("symbol","?")} {t.get("direction","?")} PnL={float(t.get("realized_pnl_net",0)):.2f} src={t.get("pnl_source","?")}')

    # By symbol
    print('\n' + '='*90)
    print('PER-SYMBOL STATS')
    print('='*90)
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t.get('symbol','?')].append(t)

    print(f"{'Symbol':<15} {'Trades':<8} {'Wins':<6} {'Loss':<6} {'WR%':<8} {'PnL':<12} {'AvgPnL':<10}")
    print('-'*90)
    for sym in sorted(by_sym):
        st = by_sym[sym]
        w = sum(1 for t in st if float(t.get('realized_pnl_net',0)) > 0)
        l = sum(1 for t in st if float(t.get('realized_pnl_net',0)) < 0)
        wr = w/len(st)*100
        tp = sum(float(t.get('realized_pnl_net',0)) for t in st)
        ap = tp/len(st)
        print(f'{sym:<15} {len(st):<8} {w:<6} {l:<6} {wr:<8.1f} {tp:<12.2f} {ap:<10.2f}')

# === 2. SIGNALS from signal_log.csv ===
print('\n' + '='*90)
print('SIGNAL LOG ANALYSIS')
print('='*90)
total_sigs = 0
allowed_sigs = 0
try:
    with open('ml_bot/logs/signal_log.csv') as f:
        for row in csv.DictReader(f):
            total_sigs += 1
            if row.get('allow_entry','False') == 'True':
                allowed_sigs += 1
    print(f'Total signals: {total_sigs}')
    print(f'Allowed (trades taken): {allowed_sigs}')
    if total_sigs:
        print(f'Trade-to-signal ratio: {allowed_sigs/total_sigs*100:.1f}%')
except FileNotFoundError:
    print("ERROR: ml_bot/logs/signal_log.csv not found!")