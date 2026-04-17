#!/usr/bin/env python3
"""
Анализатор торговли - парсит логи и выдает сводку
"""
import re
from collections import defaultdict
from datetime import datetime

def analyze_trades(log_file):
    """Анализирует все сделки из лог файла"""
    
    # Структура для хранения статистики по монетам
    symbol_stats = defaultdict(lambda: {
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'total_pnl': 0.0,
        'pnl_list': [],
        'first_trade': None,
        'last_trade': None
    })
    
    # Регулярные выражения для парсинга
    trade_pattern = r'Recorded trade: (\w+) (\w+) (\w+), PnL: ([\d.-]+)%'
    pnl_pattern = r'Closed \w+: (\w+), PnL: \$([\d.-]+)'
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    total_pnl = 0.0
    total_trades = 0
    winning_trades = 0
    losing_trades = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Ищем строку с Recorded trade
        match = re.search(trade_pattern, line)
        if match:
            trade_type = match.group(1)
            direction = match.group(2)
            symbol = match.group(3)
            pnl_pct = float(match.group(4))
            
            # Ищем следующую строку с PnL в USD
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                pnl_match = re.search(r'PnL: \$([\d.-]+)', next_line)
                if pnl_match:
                    pnl_usd = float(pnl_match.group(1))
                    
                    # Обновляем статистику
                    stats = symbol_stats[symbol]
                    stats['total_trades'] += 1
                    stats['total_pnl'] += pnl_usd
                    stats['pnl_list'].append(pnl_usd)
                    
                    if pnl_usd > 0:
                        stats['winning_trades'] += 1
                        winning_trades += 1
                    else:
                        stats['losing_trades'] += 1
                        losing_trades += 1
                    
                    total_pnl += pnl_usd
                    total_trades += 1
                    
                    # Время первой и последней сделки
                    time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if time_match:
                        trade_time = time_match.group(1)
                        if stats['first_trade'] is None:
                            stats['first_trade'] = trade_time
                        stats['last_trade'] = trade_time
        
        i += 1
    
    # Выводим результаты
    print("=" * 80)
    print("📊 ОБЩАЯ СТАТИСТИКА ТОРГОВЛИ")
    print("=" * 80)
    print(f"Всего сделок: {total_trades}")
    print(f"Прибыльных: {winning_trades}")
    print(f"Убыточных: {losing_trades}")
    print(f"Win Rate: {winning_trades/total_trades*100:.1f}%" if total_trades > 0 else "N/A")
    print(f"Общий PnL: ${total_pnl:.2f}")
    print(f"Средний PnL на сделку: ${total_pnl/total_trades:.2f}" if total_trades > 0 else "N/A")
    print()
    
    # Сортируем монеты по PnL
    sorted_symbols = sorted(symbol_stats.items(), key=lambda x: x[1]['total_pnl'], reverse=True)
    
    print("=" * 80)
    print("🏆 ТОП-20 ЛУЧШИХ МОНЕТ (по общему PnL)")
    print("=" * 80)
    print(f"{'Монета':<20} {'Сделок':>8} {'Win%':>8} {'Общий PnL':>12} {'Средний':>10}")
    print("-" * 80)
    
    for symbol, stats in sorted_symbols[:20]:
        win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
        avg_pnl = stats['total_pnl']/stats['total_trades'] if stats['total_trades'] > 0 else 0
        print(f"{symbol:<20} {stats['total_trades']:>8} {win_rate:>7.1f}% {stats['total_pnl']:>11.2f}$ {avg_pnl:>9.2f}$")
    
    print()
    print("=" * 80)
    print("💀 ТОП-20 ХУДШИХ МОНЕТ (по общему PnL)")
    print("=" * 80)
    print(f"{'Монета':<20} {'Сделок':>8} {'Win%':>8} {'Общий PnL':>12} {'Средний':>10}")
    print("-" * 80)
    
    for symbol, stats in sorted_symbols[-20:]:
        win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
        avg_pnl = stats['total_pnl']/stats['total_trades'] if stats['total_trades'] > 0 else 0
        print(f"{symbol:<20} {stats['total_trades']:>8} {win_rate:>7.1f}% {stats['total_pnl']:>11.2f}$ {avg_pnl:>9.2f}$")
    
    print()
    print("=" * 80)
    print("📈 МОНЕТЫ С 100% WIN RATE (минимум 3 сделки)")
    print("=" * 80)
    
    perfect_symbols = [(s, st) for s, st in symbol_stats.items() 
                       if st['total_trades'] >= 3 and st['winning_trades'] == st['total_trades']]
    perfect_symbols.sort(key=lambda x: x[1]['total_pnl'], reverse=True)
    
    for symbol, stats in perfect_symbols[:15]:
        print(f"{symbol:<20} {stats['total_trades']:>3} сделок, PnL: ${stats['total_pnl']:>8.2f}")
    
    if not perfect_symbols:
        print("Нет монет с 100% win rate и минимум 3 сделками")
    
    print()
    print("=" * 80)
    print("📉 МОНЕТЫ С 0% WIN RATE (минимум 3 сделки)")
    print("=" * 80)
    
    bad_symbols = [(s, st) for s, st in symbol_stats.items() 
                   if st['total_trades'] >= 3 and st['losing_trades'] == st['total_trades']]
    bad_symbols.sort(key=lambda x: x[1]['total_pnl'])
    
    for symbol, stats in bad_symbols[:15]:
        print(f"{symbol:<20} {stats['total_trades']:>3} сделок, PnL: ${stats['total_pnl']:>8.2f}")
    
    if not bad_symbols:
        print("Нет монет с 0% win rate и минимум 3 сделками")
    
    # Сохраняем результаты в файл
    with open('trading_summary.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("📊 ОБЩАЯ СТАТИСТИКА ТОРГОВЛИ\n")
        f.write("=" * 80 + "\n")
        f.write(f"Всего сделок: {total_trades}\n")
        f.write(f"Прибыльных: {winning_trades}\n")
        f.write(f"Убыточных: {losing_trades}\n")
        f.write(f"Win Rate: {winning_trades/total_trades*100:.1f}%\n" if total_trades > 0 else "Win Rate: N/A\n")
        f.write(f"Общий PnL: ${total_pnl:.2f}\n")
        f.write(f"Средний PnL на сделку: ${total_pnl/total_trades:.2f}\n" if total_trades > 0 else "Средний PnL: N/A\n")
        f.write("\n")
        
        f.write("🏆 ТОП-20 ЛУЧШИХ МОНЕТ:\n")
        for symbol, stats in sorted_symbols[:20]:
            win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
            f.write(f"{symbol}: {stats['total_trades']} сделок, {win_rate:.1f}% win, ${stats['total_pnl']:.2f} total\n")
        
        f.write("\n💀 ТОП-20 ХУДШИХ МОНЕТ:\n")
        for symbol, stats in sorted_symbols[-20:]:
            win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
            f.write(f"{symbol}: {stats['total_trades']} сделок, {win_rate:.1f}% win, ${stats['total_pnl']:.2f} total\n")
    
    print()
    print("✅ Результаты сохранены в trading_summary.txt")

if __name__ == "__main__":
    analyze_trades('full_bot.log')
