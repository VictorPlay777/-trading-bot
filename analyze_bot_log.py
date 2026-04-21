#!/usr/bin/env python3
"""
Bot Log Analyzer - Extracts trading statistics from logs
"""
import re
import sys
from datetime import datetime
from collections import defaultdict

def analyze_log(log_file):
    """Analyze bot log file and extract statistics"""
    
    stats = {
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'total_pnl': 0.0,
        'symbols': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'wins': 0, 'losses': 0}),
        'start_time': None,
        'end_time': None,
        'errors': 0
    }
    
    # Patterns to match
    patterns = {
        'trade_profit': re.compile(r'(profit|PROFIT).*(\d+\.?\d*).*USDT'),
        'trade_loss': re.compile(r'(loss|LOSS|Stop loss).*(\d+\.?\d*).*USDT'),
        'pnl_line': re.compile(r'PnL[\s:]+([+-]?\d+\.?\d*)'),
        'symbol_trade': re.compile(r'(\w+USDT).*(?:profit|loss|closed)'),
        'timestamp': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'),
        'error': re.compile(r'(ERROR|Error|error)')
    }
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ File not found: {log_file}")
        return None
    
    print(f"📊 Analyzing {len(lines)} lines from {log_file}...")
    
    for line in lines:
        # Extract timestamp
        ts_match = patterns['timestamp'].search(line)
        if ts_match:
            try:
                ts = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S')
                if not stats['start_time']:
                    stats['start_time'] = ts
                stats['end_time'] = ts
            except:
                pass
        
        # Count errors
        if patterns['error'].search(line):
            stats['errors'] += 1
            continue
        
        # Look for profit/loss
        symbol = None
        sym_match = patterns['symbol_trade'].search(line)
        if sym_match:
            symbol = sym_match.group(1)
        
        # Profit
        profit_match = patterns['trade_profit'].search(line)
        if profit_match:
            stats['total_trades'] += 1
            stats['winning_trades'] += 1
            try:
                pnl = float(profit_match.group(2))
                stats['total_pnl'] += pnl
                if symbol:
                    stats['symbols'][symbol]['trades'] += 1
                    stats['symbols'][symbol]['pnl'] += pnl
                    stats['symbols'][symbol]['wins'] += 1
            except:
                pass
            continue
        
        # Loss
        loss_match = patterns['trade_loss'].search(line)
        if loss_match:
            stats['total_trades'] += 1
            stats['losing_trades'] += 1
            try:
                pnl = -float(loss_match.group(2))
                stats['total_pnl'] += pnl
                if symbol:
                    stats['symbols'][symbol]['trades'] += 1
                    stats['symbols'][symbol]['pnl'] += pnl
                    stats['symbols'][symbol]['losses'] += 1
            except:
                pass
            continue
        
        # Direct PnL mention
        pnl_match = patterns['pnl_line'].search(line)
        if pnl_match:
            try:
                pnl = float(pnl_match.group(1))
                # Don't double count
            except:
                pass
    
    return stats

def print_report(stats):
    """Print formatted report"""
    if not stats:
        return
    
    print("\n" + "="*60)
    print("📈 BOT TRADING STATISTICS REPORT")
    print("="*60)
    
    # Time range
    if stats['start_time'] and stats['end_time']:
        duration = stats['end_time'] - stats['start_time']
        days = duration.total_seconds() / 86400
        print(f"\n⏱️  Period: {stats['start_time']} to {stats['end_time']}")
        print(f"   Duration: {days:.1f} days ({duration.total_seconds()/3600:.1f} hours)")
    
    # Overall stats
    print(f"\n💰 FINANCIAL SUMMARY:")
    print(f"   Total Trades: {stats['total_trades']}")
    print(f"   Winning: {stats['winning_trades']}")
    print(f"   Losing: {stats['losing_trades']}")
    
    if stats['total_trades'] > 0:
        win_rate = (stats['winning_trades'] / stats['total_trades']) * 100
        print(f"   Win Rate: {win_rate:.2f}%")
    
    pnl_color = "🟢" if stats['total_pnl'] >= 0 else "🔴"
    print(f"   {pnl_color} Total PnL: {stats['total_pnl']:+.2f} USDT")
    
    print(f"\n⚠️  Errors encountered: {stats['errors']}")
    
    # Top symbols
    if stats['symbols']:
        print(f"\n📊 TOP 10 SYMBOLS BY TRADE COUNT:")
        sorted_symbols = sorted(stats['symbols'].items(), 
                               key=lambda x: x[1]['trades'], 
                               reverse=True)[:10]
        
        for i, (symbol, data) in enumerate(sorted_symbols, 1):
            win_rate_sym = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
            pnl_sym = "🟢" if data['pnl'] >= 0 else "🔴"
            print(f"   {i}. {symbol}: {data['trades']} trades, "
                  f"Win Rate {win_rate_sym:.1f}%, "
                  f"{pnl_sym} {data['pnl']:+.2f} USDT")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Default log files to check
        log_files = [
            'bot_logs/bot_3_alts_only.log',
            'multi_bot.log',
            'logs/trading.log'
        ]
        
        for log_file in log_files:
            print(f"\n🔍 Trying {log_file}...")
            stats = analyze_log(log_file)
            if stats and stats['total_trades'] > 0:
                print_report(stats)
                break
        else:
            print("❌ No log files found with trade data")
            print(f"Usage: python {sys.argv[0]} <log_file>")
    else:
        stats = analyze_log(sys.argv[1])
        if stats:
            print_report(stats)
