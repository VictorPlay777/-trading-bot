#!/usr/bin/env python3
"""Анализ точности предсказаний за текущую сессию бота"""
import re
import sys
from collections import defaultdict
from datetime import datetime

def analyze_session_accuracy(log_file):
    """Анализирует точность предсказаний по логам"""
    
    # Находим время начала сессии
    session_start = None
    predictions = {}
    positions = {}
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Ищем начало сессии
    for line in lines:
        if 'Scanner started:' in line:
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                session_start = timestamp_match.group(1)
                break
    
    print(f"📊 Анализ сессии с {session_start}")
    print("=" * 60)
    
    # Собираем предсказания и открытия
    for line in lines:
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if not timestamp_match:
            continue
            
        timestamp = timestamp_match.group(1)
        
        # Предсказания
        if 'p_up=' in line and 'p_dn=' in line and 'signal=' in line:
            symbol_match = re.search(r'(\w+USDT):', line)
            if symbol_match:
                symbol = symbol_match.group(1)
                p_up_match = re.search(r'p_up=([\d.]+)', line)
                p_dn_match = re.search(r'p_dn=([\d.]+)', line)
                signal_match = re.search(r'signal=(\w+)', line)
                
                if all([p_up_match, p_dn_match, signal_match]):
                    p_up = float(p_up_match.group(1))
                    p_dn = float(p_dn_match.group(1))
                    signal = signal_match.group(1)
                    
                    predictions[symbol] = {
                        'timestamp': timestamp,
                        'p_up': p_up,
                        'p_dn': p_dn,
                        'signal': signal,
                        'opened': False,
                        'closed': False,
                        'result': None
                    }
        
        # Открытия позиций
        if '>> OPENED' in line:
            symbol_match = re.search(r'(\w+USDT)', line)
            if symbol_match:
                symbol = symbol_match.group(1)
                if symbol in predictions:
                    predictions[symbol]['opened'] = True
                    predictions[symbol]['open_time'] = timestamp
                    
                    # Извлекаем сторону и размер
                    if 'long' in line:
                        predictions[symbol]['side'] = 'long'
                    elif 'short' in line:
                        predictions[symbol]['side'] = 'short'
        
        # Закрытия позиций (TP)
        if 'TP triggered:' in line or 'Closed TP:' in line:
            symbol_match = re.search(r'(\w+USDT)', line)
            if symbol_match:
                symbol = symbol_match.group(1)
                if symbol in predictions:
                    predictions[symbol]['closed'] = True
                    predictions[symbol]['close_time'] = timestamp
                    predictions[symbol]['result'] = 'TP'
        
        # Закрытия (Early Exit)
        if 'EARLY EXIT:' in line:
            symbol_match = re.search(r'(\w+USDT)', line)
            if symbol_match:
                symbol = symbol_match.group(1)
                if symbol in predictions:
                    predictions[symbol]['closed'] = True
                    predictions[symbol]['close_time'] = timestamp
                    predictions[symbol]['result'] = 'EARLY_EXIT'
    
    # Анализируем результаты
    total_predictions = len(predictions)
    opened_positions = sum(1 for p in predictions.values() if p['opened'])
    closed_positions = sum(1 for p in predictions.values() if p['closed'])
    
    # Считаем точность по закрытым позициям
    tp_count = sum(1 for p in predictions.values() if p['result'] == 'TP')
    early_exit_count = sum(1 for p in predictions.values() if p['result'] == 'EARLY_EXIT')
    
    print(f"📈 Статистика предсказаний:")
    print(f"  Всего предсказаний: {total_predictions}")
    print(f"  Открыто позиций: {opened_positions}")
    print(f"  Закрыто позиций: {closed_positions}")
    print(f"  TP закрытий: {tp_count}")
    print(f"  Early Exit: {early_exit_count}")
    
    if closed_positions > 0:
        tp_rate = (tp_count / closed_positions) * 100
        print(f"  🎯 Win Rate (TP): {tp_rate:.1f}%")
    
    print(f"\n📊 Детализация по сигналам:")
    
    # Группируем по сигналам
    signal_stats = defaultdict(lambda: {'total': 0, 'opened': 0, 'closed': 0, 'tp': 0})
    
    for symbol, pred in predictions.items():
        signal_type = pred['signal']
        signal_stats[signal_type]['total'] += 1
        if pred['opened']:
            signal_stats[signal_type]['opened'] += 1
        if pred['closed']:
            signal_stats[signal_type]['closed'] += 1
        if pred['result'] == 'TP':
            signal_stats[signal_type]['tp'] += 1
    
    for signal_type, stats in signal_stats.items():
        if signal_type != 'None':
            print(f"  {signal_type}:")
            print(f"    Предсказаний: {stats['total']}")
            print(f"    Открыто: {stats['opened']}")
            print(f"    Закрыто: {stats['closed']}")
            if stats['closed'] > 0:
                win_rate = (stats['tp'] / stats['closed']) * 100
                print(f"    Win Rate: {win_rate:.1f}%")
    
    print(f"\n🔍 Последние открытые позиции:")
    for symbol, pred in sorted(predictions.items(), key=lambda x: x[1].get('timestamp', ''), reverse=True)[:10]:
        if pred['opened'] and not pred['closed']:
            print(f"  {symbol}: {pred['signal']} (p_up={pred['p_up']:.3f}, p_dn={pred['p_dn']:.3f})")
    
    print(f"\n📋 Последние закрытия:")
    for symbol, pred in sorted(predictions.items(), key=lambda x: x[1].get('close_time', ''), reverse=True)[:10]:
        if pred['closed']:
            print(f"  {symbol}: {pred['signal']} → {pred['result']}")

if __name__ == "__main__":
    log_file = "ml_live_scanner.log"
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    
    analyze_session_accuracy(log_file)
