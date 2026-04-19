#!/usr/bin/env python3
"""
Analyze CURRENT SESSION only - Latest log file
"""
import re
import glob
import os
from collections import defaultdict
from datetime import datetime

def analyze_current_session():
    # Find latest log BY MODIFICATION TIME (not by name!)
    log_files = glob.glob("bot_*.log")
    if not log_files:
        print("No log files found!")
        return
    
    # Sort by modification time (most recent first)
    log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_log = log_files[0]
    
    print(f"📊 ANALYZING CURRENT SESSION")
    print(f"Log file: {latest_log}")
    print(f"{'='*70}\n")
    
    # Parse log
    with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()
    
    # Find last session start (START BOT or Starting trading engine)
    last_start_idx = 0
    for i, line in enumerate(all_lines):
        if "START BOT" in line or "Starting trading engine" in line:
            last_start_idx = i
    
    # Only analyze current session (after last start)
    lines = all_lines[last_start_idx:]
    print(f"📅 Session starts at line {last_start_idx + 1} ({lines[0][:19] if lines else 'N/A'})")
    print(f"   Analyzing {len(lines)} lines\n")
    
    # Data structures
    symbols = defaultdict(lambda: {
        'trades': 0, 'wins': 0, 'losses': 0,
        'total_pnl': 0.0, 'gross_pnl': 0.0,
        'win_amounts': [], 'loss_amounts': [],
        'signal_type': None
    })
    
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_net_pnl = 0.0
    signal_counts = defaultdict(int)
    
    # Parse each line
    for line in lines:
        # Recorded trade line - most detailed
        # Format: Recorded trade: momentum short BLESSUSDT, PnL: -1.26%
        match = re.search(r'Recorded trade:\s+(\w+)\s+(\w+)\s+(\w+)USDT.*?PnL:\s+([-\d.]+)%', line)
        if match:
            signal_type, direction, symbol_base, pnl_pct = match.groups()
            symbol = symbol_base + "USDT"
            pnl = float(pnl_pct)
            
            symbols[symbol]['trades'] += 1
            symbols[symbol]['signal_type'] = signal_type
            signal_counts[signal_type] += 1
            total_trades += 1
            
            if pnl > 0:
                symbols[symbol]['wins'] += 1
                symbols[symbol]['win_amounts'].append(pnl)
                total_wins += 1
            else:
                symbols[symbol]['losses'] += 1
                symbols[symbol]['loss_amounts'].append(pnl)
                total_losses += 1
            
            symbols[symbol]['gross_pnl'] += pnl
        
        # Net PnL from closed position
        # Format: Net PnL: $-164.32
        match = re.search(r'Closed \w+USDT.*?Net PnL:\s+\$?([-\d.]+)', line)
        if match:
            net_pnl = float(match.group(1))
            total_net_pnl += net_pnl
    
    # Calculate statistics
    results = []
    for symbol, data in symbols.items():
        if data['trades'] == 0:
            continue
        
        win_rate = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
        avg_win = sum(data['win_amounts']) / len(data['win_amounts']) if data['win_amounts'] else 0
        avg_loss = sum(data['loss_amounts']) / len(data['loss_amounts']) if data['loss_amounts'] else 0
        
        gross_profit = sum(data['win_amounts'])
        gross_loss = abs(sum(data['loss_amounts']))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        results.append({
            'symbol': symbol,
            'trades': data['trades'],
            'wins': data['wins'],
            'losses': data['losses'],
            'win_rate': win_rate,
            'total_pnl': data['gross_pnl'],
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'signal_type': data['signal_type'] or 'unknown'
        })
    
    # Sort by total PnL
    results.sort(key=lambda x: x['total_pnl'], reverse=True)
    
    # Print per-symbol table
    print(f"{'SYMBOL':<15} {'TRADES':>8} {'WINS':>6} {'LOSS':>6} {'WIN%':>8} {'TOTAL PnL%':>12} {'AVG WIN':>10} {'AVG LOSS':>10} {'P.F.':>6} {'TYPE':>10}")
    print(f"{'-'*15} {'-'*8} {'-'*6} {'-'*6} {'-'*8} {'-'*12} {'-'*10} {'-'*10} {'-'*6} {'-'*10}")
    
    for r in results:
        print(f"{r['symbol']:<15} {r['trades']:>8} {r['wins']:>6} {r['losses']:>6} {r['win_rate']:>7.1f}% {r['total_pnl']:>11.2f}% {r['avg_win']:>9.2f}% {r['avg_loss']:>9.2f}% {r['profit_factor']:>6.2f} {r['signal_type']:>10}")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"📈 OVERALL STATISTICS")
    print(f"{'='*70}")
    print(f"Total Trades:     {total_trades}")
    print(f"Wins:             {total_wins}")
    print(f"Losses:           {total_losses}")
    print(f"Win Rate:         {total_wins/total_trades*100:.2f}%" if total_trades > 0 else "N/A")
    print(f"Net PnL (from closes): ${total_net_pnl:.2f}")
    print(f"Gross PnL (from %):    {sum(r['total_pnl'] for r in results):.2f}%")
    
    # Best/Worst
    if results:
        best = results[0]
        worst = results[-1]
        print(f"\n🏆 BEST:  {best['symbol']} - Win Rate: {best['win_rate']:.1f}%, PnL: {best['total_pnl']:.2f}%")
        print(f"💀 WORST: {worst['symbol']} - Win Rate: {worst['win_rate']:.1f}%, PnL: {worst['total_pnl']:.2f}%")
    
    # Signal distribution
    print(f"\n📊 SIGNAL TYPE DISTRIBUTION:")
    for sig, count in sorted(signal_counts.items(), key=lambda x: x[1], reverse=True):
        pct = count / total_trades * 100 if total_trades > 0 else 0
        print(f"  {sig:>12}: {count:>4} trades ({pct:>5.1f}%)")
    
    print(f"\n{'='*70}")
    print(f"Session start: {lines[0][:19] if lines else 'N/A'}")
    print(f"Session end:   {lines[-1][:19] if lines else 'N/A'}")
    print(f"{'='*70}")

if __name__ == "__main__":
    analyze_current_session()
