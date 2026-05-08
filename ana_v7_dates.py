import json
from datetime import datetime

trades = []
with open('ml_bot/logs/trades.jsonl') as f:
    for line in f:
        try:
            trades.append(json.loads(line.strip()))
        except: pass

if not trades:
    print('No trades found')
else:
    # Get open and close timestamps
    first_open = min(t.get('opened_ts', 0) for t in trades)
    last_close = max(t.get('closed_ts', 0) for t in trades)
    first_close = min(t.get('closed_ts', 0) for t in trades if t.get('closed_ts', 0) > 0)
    last_open = max(t.get('opened_ts', 0) for t in trades)
    
    print(f'First trade opened:  {datetime.fromtimestamp(first_open).strftime( %Y-%m-%d %H:%M:%S)}')
    print(f'Last trade opened:   {datetime.fromtimestamp(last_open).strftime(%Y-%m-%d %H:%M:%S)}')
    print(f'First trade closed:  {datetime.fromtimestamp(first_close).strftime(%Y-%m-%d %H:%M:%S)}')
    print(f'Last trade closed:   {datetime.fromtimestamp(last_close).strftime(%Y-%m-%d %H:%M:%S)}')
    print(f'Total duration:       {(last_close - first_open)/86400:.1f} days')
    
    # Signal log dates
    with open('ml_bot/logs/signal_log.csv') as f:
        import csv
        reader = csv.DictReader(f)
        timestamps = []
        for row in reader:
            timestamps.append(float(row['timestamp']))
    
    if timestamps:
        print(f'\nSignal log first: {datetime.fromtimestamp(min(timestamps)).strftime(%Y-%m-%d %H:%M:%S)}')
        print(f'Signal log last:  {datetime.fromtimestamp(max(timestamps)).strftime(%Y-%m-%d %H:%M:%S)}')
    
    # Count trades by strategy
    from collections import Counter
    strategies = Counter(t.get('strategy_id', 'unknown') for t in trades)
    print(f'\nStrategies:')
    for s, c in strategies.most_common(10):
        print(f'  {s}: {c} trades')
