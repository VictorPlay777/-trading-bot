import re
from collections import defaultdict

stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0, 'max_p': 0.0, 'max_l': 0.0})
total_pnl = 0
total_trades = 0
winning = 0

print("Анализируем построчно...")
with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
    prev_line = ""
    count = 0
    for line in f:
        count += 1
        if count % 50000 == 0:
            print(f"Обработано {count} строк...")
        
        # Ищем Recorded trade
        match = re.search(r'Recorded trade: (\w+) (\w+) (\w+), PnL: ([\d.-]+)%', line)
        if match:
            trade_type, direction, symbol, pnl_pct = match.groups()
            pnl_pct = float(pnl_pct)
            
            # Читаем следующую строку для USD PnL
            try:
                next_line = next(f)
                pnl_match = re.search(r'PnL: \$([\d.-]+)', next_line)
                if pnl_match:
                    pnl_usd = float(pnl_match.group(1))
                    
                    stats[symbol]['trades'] += 1
                    stats[symbol]['pnl'] += pnl_usd
                    if pnl_usd > 0:
                        stats[symbol]['wins'] += 1
                        winning += 1
                        if pnl_usd > stats[symbol]['max_p']:
                            stats[symbol]['max_p'] = pnl_usd
                    else:
                        if pnl_usd < stats[symbol]['max_l']:
                            stats[symbol]['max_l'] = pnl_usd
                    
                    total_pnl += pnl_usd
                    total_trades += 1
            except:
                pass

print(f"\n=== РЕЗУЛЬТАТЫ ===")
print(f"Всего сделок: {total_trades}")
print(f"Winning: {winning}")
print(f"Losing: {total_trades - winning}")
print(f"Win Rate: {winning/total_trades*100:.1f}%")
print(f"Total PnL: ${total_pnl:.2f}")

print(f"\n=== ТОП-30 ЛУЧШИХ МОНЕТ ===")
sorted_stats = sorted(stats.items(), key=lambda x: x[1]['pnl'], reverse=True)
for i, (sym, s) in enumerate(sorted_stats[:30], 1):
    wr = s['wins']/s['trades']*100 if s['trades'] > 0 else 0
    print(f"{i:2}. {sym:20} {s['trades']:4} сделок  {wr:5.1f}%  ${s['pnl']:8.2f}  (max: ${s['max_p']:.2f}/{s['max_l']:.2f})")

print(f"\n=== ТОП-30 ХУДШИХ МОНЕТ ===")
for i, (sym, s) in enumerate(sorted_stats[-30:], 1):
    wr = s['wins']/s['trades']*100 if s['trades'] > 0 else 0
    print(f"{i:2}. {sym:20} {s['trades']:4} сделок  {wr:5.1f}%  ${s['pnl']:8.2f}  (max: ${s['max_p']:.2f}/{s['max_l']:.2f})")

print("\n=== СОХРАНЕНО В RESULTS.TXT ===")
with open('RESULTS.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total trades: {total_trades}\n")
    f.write(f"Win Rate: {winning/total_trades*100:.1f}%\n")
    f.write(f"Total PnL: ${total_pnl:.2f}\n\n")
    f.write("=== TOP 50 BEST ===\n")
    for sym, s in sorted_stats[:50]:
        f.write(f"{sym}: {s['trades']} trades, ${s['pnl']:.2f}\n")
    f.write("\n=== TOP 50 WORST ===\n")
    for sym, s in sorted_stats[-50:]:
        f.write(f"{sym}: {s['trades']} trades, ${s['pnl']:.2f}\n")
