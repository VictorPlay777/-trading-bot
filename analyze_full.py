#!/usr/bin/env python3
"""
Анализатор торговли - парсит большие логи и выдает сводку
"""
import re
from collections import defaultdict
import sys

def analyze_trades(log_file):
    """Анализирует все сделки из лог файла"""
    
    # Структура для хранения статистики по монетам
    symbol_stats = defaultdict(lambda: {
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'total_pnl': 0.0,
        'total_pnl_pct': 0.0,
        'max_profit': 0.0,
        'max_loss': 0.0,
        'trade_types': defaultdict(int),
    })
    
    total_pnl = 0.0
    total_trades = 0
    winning_trades = 0
    losing_trades = 0
    
    # Регулярные выражения
    trade_pattern = r'Recorded trade: (\w+) (\w+) (\w+), PnL: ([\d.-]+)%'
    
    print("Читаем файл...")
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    print(f"Всего строк: {len(lines)}")
    print("Анализируем сделки...")
    
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
            pnl_usd = 0.0
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                pnl_match = re.search(r'PnL: \$([\d.-]+)', next_line)
                if pnl_match:
                    pnl_usd = float(pnl_match.group(1))
            
            # Обновляем статистику
            stats = symbol_stats[symbol]
            stats['total_trades'] += 1
            stats['total_pnl'] += pnl_usd
            stats['total_pnl_pct'] += pnl_pct
            stats['trade_types'][f"{trade_type} {direction}"] += 1
            
            if pnl_usd > 0:
                stats['winning_trades'] += 1
                winning_trades += 1
                if pnl_usd > stats['max_profit']:
                    stats['max_profit'] = pnl_usd
            else:
                stats['losing_trades'] += 1
                losing_trades += 1
                if pnl_usd < stats['max_loss']:
                    stats['max_loss'] = pnl_usd
            
            total_pnl += pnl_usd
            total_trades += 1
            
            if total_trades % 1000 == 0:
                print(f"Обработано: {total_trades} сделок...")
        
        i += 1
    
    # Выводим результаты
    print("\n" + "=" * 100)
    print("📊 ОБЩАЯ СТАТИСТИКА ТОРГОВЛИ")
    print("=" * 100)
    print(f"Всего сделок: {total_trades}")
    print(f"Прибыльных: {winning_trades}")
    print(f"Убыточных: {losing_trades}")
    print(f"Win Rate: {winning_trades/total_trades*100:.1f}%" if total_trades > 0 else "N/A")
    print(f"Общий PnL: ${total_pnl:.2f}")
    print(f"Средний PnL на сделку: ${total_pnl/total_trades:.2f}" if total_trades > 0 else "N/A")
    
    # Сортируем монеты по PnL
    sorted_symbols = sorted(symbol_stats.items(), key=lambda x: x[1]['total_pnl'], reverse=True)
    
    print("\n" + "=" * 100)
    print("🏆 ТОП-30 ЛУЧШИХ МОНЕТ (по общему PnL)")
    print("=" * 100)
    print(f"{'#':<3} {'Монета':<18} {'Сделок':>8} {'Win%':>8} {'Общий PnL':>12} {'Макс+':>10} {'Макс-':>10}")
    print("-" * 100)
    
    for idx, (symbol, stats) in enumerate(sorted_symbols[:30], 1):
        win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
        print(f"{idx:<3} {symbol:<18} {stats['total_trades']:>8} {win_rate:>7.1f}% {stats['total_pnl']:>11.2f}$ {stats['max_profit']:>9.2f}$ {stats['max_loss']:>9.2f}$")
    
    print("\n" + "=" * 100)
    print("💀 ТОП-30 ХУДШИХ МОНЕТ (по общему PnL)")
    print("=" * 100)
    print(f"{'#':<3} {'Монета':<18} {'Сделок':>8} {'Win%':>8} {'Общий PnL':>12} {'Макс+':>10} {'Макс-':>10}")
    print("-" * 100)
    
    for idx, (symbol, stats) in enumerate(sorted_symbols[-30:], 1):
        win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
        print(f"{idx:<3} {symbol:<18} {stats['total_trades']:>8} {win_rate:>7.1f}% {stats['total_pnl']:>11.2f}$ {stats['max_profit']:>9.2f}$ {stats['max_loss']:>9.2f}$")
    
    print("\n" + "=" * 100)
    print("📈 МОНЕТЫ С 100% WIN RATE (минимум 5 сделок)")
    print("=" * 100)
    
    perfect_symbols = [(s, st) for s, st in symbol_stats.items() 
                       if st['total_trades'] >= 5 and st['winning_trades'] == st['total_trades']]
    perfect_symbols.sort(key=lambda x: x[1]['total_pnl'], reverse=True)
    
    for idx, (symbol, stats) in enumerate(perfect_symbols[:20], 1):
        print(f"{idx:>2}. {symbol:<20} {stats['total_trades']:>3} сделок, PnL: ${stats['total_pnl']:>8.2f}")
    
    if not perfect_symbols:
        print("Нет монет с 100% win rate и минимум 5 сделками")
    
    print("\n" + "=" * 100)
    print("📉 МОНЕТЫ С 0% WIN RATE (минимум 5 сделок)")
    print("=" * 100)
    
    bad_symbols = [(s, st) for s, st in symbol_stats.items() 
                   if st['total_trades'] >= 5 and st['losing_trades'] == st['total_trades']]
    bad_symbols.sort(key=lambda x: x[1]['total_pnl'])
    
    for idx, (symbol, stats) in enumerate(bad_symbols[:20], 1):
        print(f"{idx:>2}. {symbol:<20} {stats['total_trades']:>3} сделок, PnL: ${stats['total_pnl']:>8.2f}")
    
    if not bad_symbols:
        print("Нет монет с 0% win rate и минимум 5 сделками")
    
    # Сохраняем полный отчет
    with open('FULL_ANALYSIS.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 100 + "\n")
        f.write("📊 ОБЩАЯ СТАТИСТИКА\n")
        f.write("=" * 100 + "\n")
        f.write(f"Всего сделок: {total_trades}\n")
        f.write(f"Прибыльных: {winning_trades}\n")
        f.write(f"Убыточных: {losing_trades}\n")
        f.write(f"Win Rate: {winning_trades/total_trades*100:.1f}%\n")
        f.write(f"Общий PnL: ${total_pnl:.2f}\n\n")
        
        f.write("🏆 ТОП-50 ЛУЧШИХ МОНЕТ:\n")
        for symbol, stats in sorted_symbols[:50]:
            win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
            f.write(f"{symbol}: {stats['total_trades']} сделок, {win_rate:.1f}% win, ${stats['total_pnl']:.2f} total\n")
        
        f.write("\n💀 ТОП-50 ХУДШИХ МОНЕТ:\n")
        for symbol, stats in sorted_symbols[-50:]:
            win_rate = stats['winning_trades']/stats['total_trades']*100 if stats['total_trades'] > 0 else 0
            f.write(f"{symbol}: {stats['total_trades']} сделок, {win_rate:.1f}% win, ${stats['total_pnl']:.2f} total\n")
    
    print("\n" + "=" * 100)
    print("✅ Полный отчет сохранен в FULL_ANALYSIS.txt")
    print("=" * 100)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_trades(sys.argv[1])
    else:
        analyze_trades('bot.log')
