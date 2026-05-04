#!/usr/bin/env python3
"""Анализ точности ML модели: предсказания vs реальные результаты"""
import re
import yaml
from trader.exchange_demo import Exchange
from collections import defaultdict

def analyze_model_accuracy():
    """Анализирует точность модели по предсказаниям и реальным PnL"""
    
    # Загружаем конфиг
    with open('config_scanner.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    ex = Exchange(cfg)
    
    # Получаем все открытые позиции
    pos_data = ex.get_positions()
    if pos_data.get('retCode') != 0:
        print(f"Error: {pos_data}")
        return
    
    positions = pos_data.get('result', {}).get('list', [])
    open_positions = {p.get('symbol'): {
        'side': p.get('side'),
        'pnl': float(p.get('unrealisedPnl', 0)),
        'entry': float(p.get('avgPrice', 0)),
        'size': float(p.get('size', 0))
    } for p in positions if float(p.get('size', 0)) > 0}
    
    print(f"📊 Анализ точности ML модели")
    print(f"Всего открытых позиций: {len(open_positions)}")
    print("=" * 70)
    
    # Читаем логи и собираем предсказания
    predictions = defaultdict(list)
    
    try:
        with open('ml_live_scanner.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except:
        print("Log file not found")
        return
    
    for line in lines:
        # Ищем предсказания
        match = re.search(r'(\w+USDT):\s+p_up=([\d.]+)\s+p_dn=([\d.]+)\s+signal=(\w+)', line)
        if match:
            symbol = match.group(1)
            p_up = float(match.group(2))
            p_dn = float(match.group(3))
            signal = match.group(4)
            
            if symbol in open_positions:
                pos = open_positions[symbol]
                predictions[symbol].append({
                    'p_up': p_up,
                    'p_dn': p_dn,
                    'signal': signal,
                    'actual_side': pos['side'],
                    'actual_pnl': pos['pnl'],
                    'entry': pos['entry']
                })
    
    # Анализируем точность
    correct_predictions = 0
    wrong_predictions = 0
    total_pnl = 0
    
    print(f"\n📈 Сопоставление предсказаний и результатов:")
    print(f"{'Symbol':<15} {'Signal':<8} {'p_up':<8} {'p_dn':<8} {'Actual':<8} {'PnL':>12} {'Result'}")
    print("-" * 70)
    
    for symbol, preds in predictions.items():
        if not preds:
            continue
        
        # Берём последнее предсказание
        pred = preds[-1]
        signal = pred['signal']
        actual_side = pred['actual_side']
        pnl = pred['actual_pnl']
        
        total_pnl += pnl
        
        # Проверяем соответствие
        if signal == 'None':
            result = 'SKIP'
        elif (signal == 'long' and actual_side == 'Buy') or (signal == 'short' and actual_side == 'Sell'):
            result = '✓ CORRECT'
            correct_predictions += 1
        else:
            result = '✗ WRONG'
            wrong_predictions += 1
        
        print(f"{symbol:<15} {signal:<8} {pred['p_up']:<8.3f} {pred['p_dn']:<8.3f} {actual_side:<8} {pnl:>+12.2f} {result}")
    
    print("=" * 70)
    print(f"\n📊 Статистика:")
    print(f"  Позиций с предсказаниями: {len(predictions)}")
    print(f"  Правильных направлений: {correct_predictions}")
    print(f"  Неправильных направлений: {wrong_predictions}")
    
    if correct_predictions + wrong_predictions > 0:
        accuracy = correct_predictions / (correct_predictions + wrong_predictions) * 100
        print(f"  🎯 Точность направления: {accuracy:.1f}%")
    
    print(f"\n💰 Финансовый результат:")
    print(f"  Общий PnL: {total_pnl:+.2f} USDT")
    print(f"  Средний PnL на позицию: {total_pnl/len(predictions):+.2f} USDT" if predictions else "  Нет данных")
    
    # Анализ по вероятностям
    print(f"\n📊 Анализ по уверенности модели:")
    
    high_conf = []  # p_up/p_dn > 0.8
    med_conf = []   # 0.68-0.8
    
    for symbol, preds in predictions.items():
        if not preds:
            continue
        pred = preds[-1]
        max_prob = max(pred['p_up'], pred['p_dn'])
        
        if max_prob >= 0.8:
            high_conf.append((symbol, max_prob, pred['actual_pnl']))
        elif max_prob >= 0.68:
            med_conf.append((symbol, max_prob, pred['actual_pnl']))
    
    if high_conf:
        avg_pnl_high = sum([x[2] for x in high_conf]) / len(high_conf)
        print(f"  Высокая уверенность (>0.8): {len(high_conf)} позиций, средний PnL: {avg_pnl_high:+.2f} USDT")
    
    if med_conf:
        avg_pnl_med = sum([x[2] for x in med_conf]) / len(med_conf)
        print(f"  Средняя уверенность (0.68-0.8): {len(med_conf)} позиций, средний PnL: {avg_pnl_med:+.2f} USDT")

if __name__ == "__main__":
    analyze_model_accuracy()
