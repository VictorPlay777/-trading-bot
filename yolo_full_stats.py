#!/usr/bin/env python3
"""Full YOLO session statistics - complete analysis per symbol and errors."""

import csv
from collections import defaultdict
import re
from datetime import datetime

def analyze_trades(file_path):
    """Analyze full trades.csv with per-symbol stats."""
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        
        symbol_stats = defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'win_pnl': 0.0,
            'loss_pnl': 0.0,
            'trades': []
        })
        
        overall = {
            'total': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'win_pnl': 0.0,
            'loss_pnl': 0.0
        }
        
        for row in reader:
            symbol = row['symbol']
            pnl = float(row.get('pnl_net', 0))
            direction = row['direction']
            entry_reason = row['entry_reason']
            exit_reason = row['exit_reason']
            timestamp = row['timestamp']
            
            # Overall stats
            overall['total'] += 1
            overall['total_pnl'] += pnl
            if pnl > 0:
                overall['wins'] += 1
                overall['win_pnl'] += pnl
            elif pnl < 0:
                overall['losses'] += 1
                overall['loss_pnl'] += pnl
            
            # Per-symbol stats
            symbol_stats[symbol]['total'] += 1
            symbol_stats[symbol]['total_pnl'] += pnl
            if pnl > 0:
                symbol_stats[symbol]['wins'] += 1
                symbol_stats[symbol]['win_pnl'] += pnl
            elif pnl < 0:
                symbol_stats[symbol]['losses'] += 1
                symbol_stats[symbol]['loss_pnl'] += pnl
            
            symbol_stats[symbol]['trades'].append({
                'timestamp': timestamp,
                'direction': direction,
                'pnl': pnl,
                'entry_reason': entry_reason,
                'exit_reason': exit_reason
            })
    
    return overall, symbol_stats

def analyze_errors(log_file):
    """Analyze log file for errors."""
    errors = []
    error_patterns = [
        r'ERROR',
        r'Exception',
        r'Failed',
        r'Timeout',
        r'Connection',
        r'API.*error',
        r'Invalid'
    ]
    
    try:
        with open(log_file, 'r') as f:
            for line in f:
                for pattern in error_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        errors.append(line.strip())
                        break
    except FileNotFoundError:
        print(f"Log file not found: {log_file}")
    
    return errors

def main():
    print("=" * 80)
    print("YOLO FULL SESSION STATISTICS")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Analyze trades
    print("TRADE ANALYSIS")
    print("-" * 80)
    overall, symbol_stats = analyze_trades('logs/trades.csv')
    
    # Overall stats
    print(f"\nOVERALL:")
    print(f"  Total Trades: {overall['total']}")
    print(f"  Wins: {overall['wins']}")
    print(f"  Losses: {overall['losses']}")
    win_rate = (overall['wins'] / overall['total'] * 100) if overall['total'] > 0 else 0
    print(f"  Win Rate: {win_rate:.2f}%")
    print(f"  Total PnL: ${overall['total_pnl']:,.2f}")
    print(f"  Win PnL: ${overall['win_pnl']:,.2f}")
    print(f"  Loss PnL: ${overall['loss_pnl']:,.2f}")
    avg_win = (overall['win_pnl'] / overall['wins']) if overall['wins'] > 0 else 0
    avg_loss = (overall['loss_pnl'] / overall['losses']) if overall['losses'] > 0 else 0
    print(f"  Avg Win: ${avg_win:,.2f}")
    print(f"  Avg Loss: ${avg_loss:,.2f}")
    profit_factor = abs(overall['win_pnl'] / overall['loss_pnl']) if overall['loss_pnl'] != 0 else 0
    print(f"  Profit Factor: {profit_factor:.2f}")
    
    # Per-symbol stats
    print(f"\nPER-SYMBOL STATISTICS ({len(symbol_stats)} symbols):")
    print("-" * 80)
    
    # Sort by total trades
    sorted_symbols = sorted(symbol_stats.items(), key=lambda x: x[1]['total'], reverse=True)
    
    for symbol, stats in sorted_symbols:
        symbol_win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        symbol_avg_win = (stats['win_pnl'] / stats['wins']) if stats['wins'] > 0 else 0
        symbol_avg_loss = (stats['loss_pnl'] / stats['losses']) if stats['losses'] > 0 else 0
        symbol_pf = abs(stats['win_pnl'] / stats['loss_pnl']) if stats['loss_pnl'] != 0 else 0
        
        print(f"\n  {symbol}:")
        print(f"    Trades: {stats['total']}")
        print(f"    Wins: {stats['wins']} | Losses: {stats['losses']}")
        print(f"    Win Rate: {symbol_win_rate:.2f}%")
        print(f"    Total PnL: ${stats['total_pnl']:,.2f}")
        print(f"    Avg Win: ${symbol_avg_win:,.2f}")
        print(f"    Avg Loss: ${symbol_avg_loss:,.2f}")
        print(f"    Profit Factor: {symbol_pf:.2f}")
    
    # Analyze errors
    print(f"\nERROR ANALYSIS")
    print("-" * 80)
    errors = analyze_errors('logs/bot.log')
    print(f"Total Errors: {len(errors)}")
    
    if errors:
        # Count unique error types
        error_counts = defaultdict(int)
        for error in errors:
            # Extract error type (first few words)
            error_type = ' '.join(error.split()[:5])
            error_counts[error_type] += 1
        
        print(f"\nTop Error Types:")
        for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {count}x: {error_type}")
        
        print(f"\nLast 20 Errors:")
        for error in errors[-20:]:
            print(f"  {error}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
