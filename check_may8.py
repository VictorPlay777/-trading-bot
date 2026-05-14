#!/usr/bin/env python3
"""Check what data exists for May 8-9 2026"""
import json, csv, os
from collections import Counter, defaultdict
from datetime import datetime, timezone



print('=== trades.jsonl: May 8-9 ===')
trades = []
with open('ml_bot/logs/trades.jsonl') as f:
    for line in f:
        line = line.strip()
        if line:
            trades.append(json.loads(line))

may8_9_trades = [t for t in trades if datetime.fromtimestamp(t.get('opened_ts',0), tz=timezone.utc).day >= 8]
print(f'Trades on May 8-9: {len(may8_9_trades)}')
for t in may8_9_trades:
    dt = datetime.fromtimestamp(t.get('opened_ts',0), tz=timezone.utc)
    print(f'  {t.get("trade_id","?"):30s} opened={dt} strategy={t.get("strategy_id","?")} PnL={t.get("realized_pnl_net",0):.2f}')

print()
print('=== signal_log.csv: May 8-9 ===')
sig_count = 0
sig_allowed = 0
with open('ml_bot/logs/signal_log.csv') as f:
    for row in csv.DictReader(f):
        ts = float(row.get('timestamp', 0))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if dt.day >= 8:
            sig_count += 1
            if row.get('allow_entry','False') == 'True':
                sig_allowed += 1
            if sig_count <= 5:
                print(f'  {row["symbol"]:15s} {row["direction"]:5s} allow={row["allow_entry"]:5s} conf={row["confidence"]} ts={dt}')

print(f'Total signals on May 8-9: {sig_count}')
print(f'Allowed signals on May 8-9: {sig_allowed}')

print()
print('=== LastWriteTime of key files ===')
import os
for fname in ['ml_bot/logs/trades.jsonl', 'ml_bot/logs/signal_log.csv', 'logs/ml.log']:
    if os.path.exists(fname):
        mtime = datetime.fromtimestamp(os.path.getmtime(fname), tz=timezone.utc)
        print(f'  {fname}: last modified {mtime}')

print()
print('=== Check active processes for bot ===')
import psutil
import subprocess
try:
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/NH'], capture_output=True, text=True, timeout=5)
    print(result.stdout[:500])
except:
    print('Could not check processes')