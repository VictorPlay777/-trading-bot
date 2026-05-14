#!/usr/bin/env python3
import re
from collections import defaultdict

# Парсим лог
positions = []

with open('ml_live_scanner.log', 'r') as f:
    for line in f:
        # Ищем сигналы с вероятностями
        match = re.search(r'(\w+USDT): p_up=([0-9.]+) p_dn=([0-9.]+) signal=(\w+)', line)
        if match and 'signal=None' not in line:
            symbol, p_up, p_dn, signal = match.groups()
            positions.append({
                'symbol': symbol,
                'p_up': float(p_up),
                'p_dn': float(p_dn),
                'signal': signal,
                'max_prob': max(float(p_up), float(p_dn))
            })

print(f"=== ВСЕ СИГНАЛЫ: {len(positions)} ===")

# Распределение по вероятностям
ranges = {
    '0.62-0.65': [],
    '0.65-0.68': [],
    '0.68-0.70': [],
    '0.70-0.75': [],
    '0.75+': []
}

for p in positions:
    prob = p['max_prob']
    if 0.62 <= prob < 0.65:
        ranges['0.62-0.65'].append(p)
    elif 0.65 <= prob < 0.68:
        ranges['0.65-0.68'].append(p)
    elif 0.68 <= prob < 0.70:
        ranges['0.68-0.70'].append(p)
    elif 0.70 <= prob < 0.75:
        ranges['0.70-0.75'].append(p)
    elif prob >= 0.75:
        ranges['0.75+'].append(p)

for r, items in ranges.items():
    longs = sum(1 for x in items if x['signal'] == 'long')
    shorts = sum(1 for x in items if x['signal'] == 'short')
    print(f"{r}: {len(items)} сигналов (long: {longs}, short: {shorts})")

print(f"\n=== САМЫЕ ВЫСОКИЕ ВЕРОЯТНОСТИ ===")
top = sorted(positions, key=lambda x: x['max_prob'], reverse=True)[:10]
for p in top:
    print(f"{p['symbol']}: {p['signal']} p_up={p['p_up']:.3f} p_dn={p['p_dn']:.3f} (max={p['max_prob']:.3f})")
