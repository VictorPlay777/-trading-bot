import re
from collections import defaultdict

stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0})

total_pnl = 0
total_trades = 0

print("Чтение файла...")
with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

print("Поиск сделок...")
# Находим все сделки
trades = re.findall(r'Recorded trade: (\w+) (\w+) (\w+), PnL: ([\d.-]+)%[\s\S]*?PnL: \$([\d.-]+)', content)

print(f"Найдено сделок: {len(trades)}")

for trade_type, direction, symbol, pnl_pct, pnl_usd in trades:
    pnl = float(pnl_usd)
    stats[symbol]['trades'] += 1
    stats[symbol]['pnl'] += pnl
    if pnl > 0:
        stats[symbol]['wins'] += 1
    total_pnl += pnl
    total_trades += 1

print(f"\n=== ОБЩАЯ СТАТИСТИКА ===")
print(f"Всего сделок: {total_trades}")
wins = sum(1 for s in stats.values() for p in [s['pnl']/s['trades'] if s['trades'] > 0 else 0] if s['pnl'] > 0)
print(f"Общий PnL: ${total_pnl:.2f}")

print(f"\n=== ТОП-20 ЛУЧШИХ ===")
sorted_stats = sorted(stats.items(), key=lambda x: x[1]['pnl'], reverse=True)
for i, (sym, s) in enumerate(sorted_stats[:20], 1):
    wr = s['wins']/s['trades']*100 if s['trades'] > 0 else 0
    print(f"{i:2}. {sym:20} {s['trades']:4} сделок  {wr:5.1f}%  ${s['pnl']:8.2f}")

print(f"\n=== ТОП-20 ХУДШИХ ===")
for i, (sym, s) in enumerate(sorted_stats[-20:], 1):
    wr = s['wins']/s['trades']*100 if s['trades'] > 0 else 0
    print(f"{i:2}. {sym:20} {s['trades']:4} сделок  {wr:5.1f}%  ${s['pnl']:8.2f}")

print("\n=== СОХРАНЕНО В quick_stats.txt ===")
with open('quick_stats.txt', 'w') as f:
    f.write(f"Total trades: {total_trades}\n")
    f.write(f"Total PnL: ${total_pnl:.2f}\n\n")
    f.write("=== TOP 50 BEST ===\n")
    for sym, s in sorted_stats[:50]:
        f.write(f"{sym}: {s['trades']} trades, ${s['pnl']:.2f}\n")
    f.write("\n=== TOP 50 WORST ===\n")
    for sym, s in sorted_stats[-50:]:
        f.write(f"{sym}: {s['trades']} trades, ${s['pnl']:.2f}\n")
