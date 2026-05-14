#!/usr/bin/env python3
import re
from collections import defaultdict

# Собираем данные
signals = {}  # symbol -> {prob, signal, result}

with open('ml_live_scanner.log', 'r') as f:
    for line in f:
        # Сигналы с вероятностями
        match = re.search(r'(\w+USDT): p_up=([0-9.]+) p_dn=([0-9.]+) signal=(\w+)', line)
        if match and 'signal=None' not in line:
            symbol, p_up, p_dn, signal = match.groups()
            max_prob = max(float(p_up), float(p_dn))
            signals[symbol] = {
                'prob': max_prob,
                'signal': signal,
                'p_up': float(p_up),
                'p_dn': float(p_dn)
            }
        
        # Закрытия по TP (прибыль)
        match = re.search(r'Closed (\w+USDT) on TP', line)
        if match:
            symbol = match.group(1)
            if symbol in signals:
                signals[symbol]['result'] = 'TP'
                signals[symbol]['pnl'] = 'profit'

# Считаем точность по диапазонам
ranges = {
    '0.62-0.65': {'total': 0, 'tp': 0},
    '0.65-0.70': {'total': 0, 'tp': 0},
    '0.70-0.80': {'total': 0, 'tp': 0},
    '0.80+': {'total': 0, 'tp': 0}
}

for sym, data in signals.items():
    if 'result' not in data:
        continue
    
    prob = data['prob']
    if 0.62 <= prob < 0.65:
        ranges['0.62-0.65']['total'] += 1
        if data['result'] == 'TP':
            ranges['0.62-0.65']['tp'] += 1
    elif 0.65 <= prob < 0.70:
        ranges['0.65-0.70']['total'] += 1
        if data['result'] == 'TP':
            ranges['0.65-0.70']['tp'] += 1
    elif 0.70 <= prob < 0.80:
        ranges['0.70-0.80']['total'] += 1
        if data['result'] == 'TP':
            ranges['0.70-0.80']['tp'] += 1
    elif prob >= 0.80:
        ranges['0.80+']['total'] += 1
        if data['result'] == 'TP':
            ranges['0.80+']['tp'] += 1

print("=== ТОЧНОСТЬ ПО ВЕРОЯТНОСТЯМ (закрытые позиции) ===")
for r, data in ranges.items():
    if data['total'] > 0:
        rate = data['tp'] / data['total'] * 100
        print(f"{r}: {data['tp']}/{data['total']} TP = {rate:.1f}%")

print(f"\n=== ВСЕГО ЗАКРЫТО ПО TP: {len([s for s in signals.values() if s.get('result')=='TP'])}/{len(signals)} ===")

# Покажем незакрытые позиции (в убытке)
print(f"\n=== ПОЗИЦИИ БЕЗ РЕЗУЛЬТАТА (возможно убыток) ===")
open_pos = [(sym, data) for sym, data in signals.items() if 'result' not in data]
print(f"Количество: {len(open_pos)}")
if open_pos:
    sorted_by_prob = sorted(open_pos, key=lambda x: x[1]['prob'], reverse=True)
    for sym, data in sorted_by_prob[:10]:
        print(f"{sym}: {data['signal']} prob={data['prob']:.3f} (up={data['p_up']:.3f}, dn={data['p_dn']:.3f})")
