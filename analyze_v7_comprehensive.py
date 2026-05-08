#!/usr/bin/env python3
"""
Comprehensive V7 Analysis Script
Analyzes all signals, trades, and positions for v7 strategy
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_bot.trader.exchange_demo import Exchange
import yaml

def analyze_signal_log():
    """Analyze signal_log.csv for all v7 signals"""
    print("=" * 100)
    print("V7 COMPREHENSIVE ANALYSIS")
    print("=" * 100)
    
    # Read signal log
    signal_log_path = 'ml_bot/logs/signal_log.csv'
    if not os.path.exists(signal_log_path):
        print(f"Signal log not found: {signal_log_path}")
        return
    
    df = pd.read_csv(signal_log_path)
    print(f"\nTotal signals logged: {len(df)}")
    
    # Filter allowed signals only
    allowed_df = df[df['allow_entry'] == True].copy()
    print(f"Allowed signals (trades): {len(allowed_df)}")
    
    if len(allowed_df) == 0:
        print("No allowed signals found!")
        return
    
    # Convert timestamp to datetime
    allowed_df['datetime'] = pd.to_datetime(allowed_df['timestamp'], unit='s')
    
    print("\n" + "=" * 100)
    print("SIGNAL STATISTICS BY SYMBOL")
    print("=" * 100)
    
    # Group by symbol
    symbol_stats = []
    for symbol in sorted(allowed_df['symbol'].unique()):
        symbol_df = allowed_df[allowed_df['symbol'] == symbol]
        
        stats = {
            'symbol': symbol,
            'total_signals': len(symbol_df),
            'long_signals': len(symbol_df[symbol_df['direction'] == 'long']),
            'short_signals': len(symbol_df[symbol_df['direction'] == 'short']),
            'avg_confidence': symbol_df['confidence'].mean(),
            'avg_ev': symbol_df['ev'].mean(),
            'avg_score': symbol_df['score'].mean(),
            'regimes': symbol_df['regime'].value_counts().to_dict(),
            'buckets': symbol_df['bucket'].value_counts().to_dict()
        }
        symbol_stats.append(stats)
    
    # Print symbol statistics
    print(f"\n{'Symbol':<15} {'Signals':<8} {'Long':<6} {'Short':<6} {'Avg Conf':<10} {'Avg EV':<12} {'Avg Score':<10}")
    print("-" * 100)
    for stat in symbol_stats:
        print(f"{stat['symbol']:<15} {stat['total_signals']:<8} {stat['long_signals']:<6} {stat['short_signals']:<6} "
              f"{stat['avg_confidence']:<10.3f} {stat['avg_ev']:<12.6f} {stat['avg_score']:<10.3f}")
    
    # Overall statistics
    print("\n" + "=" * 100)
    print("OVERALL SIGNAL STATISTICS")
    print("=" * 100)
    print(f"Total unique symbols: {len(allowed_df['symbol'].unique())}")
    print(f"Long signals: {len(allowed_df[allowed_df['direction'] == 'long'])} ({len(allowed_df[allowed_df['direction'] == 'long'])/len(allowed_df)*100:.1f}%)")
    print(f"Short signals: {len(allowed_df[allowed_df['direction'] == 'short'])} ({len(allowed_df[allowed_df['direction'] == 'short'])/len(allowed_df)*100:.1f}%)")
    print(f"\nAverage confidence: {allowed_df['confidence'].mean():.3f}")
    print(f"Average EV: {allowed_df['ev'].mean():.6f}")
    print(f"Average score: {allowed_df['score'].mean():.3f}")
    
    print("\nRegime distribution:")
    for regime, count in allowed_df['regime'].value_counts().items():
        print(f"  {regime}: {count} ({count/len(allowed_df)*100:.1f}%)")
    
    print("\nConfidence bucket distribution:")
    for bucket, count in allowed_df['bucket'].value_counts().items():
        print(f"  {bucket}: {count} ({count/len(allowed_df)*100:.1f}%)")
    
    print("\nReason distribution:")
    for reason, count in allowed_df['reason'].value_counts().head(10).items():
        print(f"  {reason}: {count} ({count/len(allowed_df)*100:.1f}%)")
    
    return allowed_df, symbol_stats


def analyze_trades_from_log():
    """Analyze actual trades from supervisor log"""
    print("\n" + "=" * 100)
    print("TRADE ANALYSIS FROM LOG")
    print("=" * 100)
    
    log_file = 'selective_ml_supervisor.log'
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return None
    
    trades = []
    positions = {}
    
    # Parse log file
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Look for position creation
            if '[STATE CREATE]' in line:
                match = re.search(r'\[STATE CREATE\] (\S+) side=(\S+) qty=(\S+) entry=(\S+)', line)
                if match:
                    symbol = match.group(1)
                    side = match.group(2)
                    qty = float(match.group(3))
                    entry = float(match.group(4))
                    
                    # Extract timestamp
                    ts_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    timestamp = ts_match.group(1) if ts_match else None
                    
                    positions[symbol] = {
                        'symbol': symbol,
                        'side': side,
                        'qty': qty,
                        'entry': entry,
                        'timestamp': timestamp,
                        'open': True
                    }
            
            # Look for trade recording (position close)
            if '[TRADE RECORDED]' in line:
                match = re.search(r'\[TRADE RECORDED\] (\S+) side=(\S+).*pnl=([\d\.\-]+)', line)
                if match:
                    symbol = match.group(1)
                    side = match.group(2)
                    pnl = float(match.group(3))
                    
                    # Extract timestamp
                    ts_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    timestamp = ts_match.group(1) if ts_match else None
                    
                    # Try to extract more details
                    entry_match = re.search(r'entry=([\d\.]+)', line)
                    exit_match = re.search(r'exit=([\d\.]+)', line)
                    qty_match = re.search(r'qty=([\d\.]+)', line)
                    
                    trade = {
                        'symbol': symbol,
                        'side': side,
                        'pnl': pnl,
                        'timestamp': timestamp,
                        'entry': float(entry_match.group(1)) if entry_match else None,
                        'exit': float(exit_match.group(1)) if exit_match else None,
                        'qty': float(qty_match.group(1)) if qty_match else None
                    }
                    trades.append(trade)
                    
                    # Mark position as closed
                    if symbol in positions:
                        positions[symbol]['open'] = False
    
    if not trades:
        print("No completed trades found in log")
        return None
    
    # Analyze trades
    trades_df = pd.DataFrame(trades)
    
    print(f"\nTotal completed trades: {len(trades_df)}")
    print(f"Winning trades: {len(trades_df[trades_df['pnl'] > 0])} ({len(trades_df[trades_df['pnl'] > 0])/len(trades_df)*100:.1f}%)")
    print(f"Losing trades: {len(trades_df[trades_df['pnl'] < 0])} ({len(trades_df[trades_df['pnl'] < 0])/len(trades_df)*100:.1f}%)")
    print(f"Breakeven trades: {len(trades_df[trades_df['pnl'] == 0])}")
    
    print(f"\nTotal PnL: {trades_df['pnl'].sum():.2f} USDT")
    print(f"Average PnL per trade: {trades_df['pnl'].mean():.2f} USDT")
    print(f"Median PnL: {trades_df['pnl'].median():.2f} USDT")
    print(f"Best trade: {trades_df['pnl'].max():.2f} USDT")
    print(f"Worst trade: {trades_df['pnl'].min():.2f} USDT")
    
    # Win rate by symbol
    print("\n" + "=" * 100)
    print("WIN RATE BY SYMBOL")
    print("=" * 100)
    print(f"\n{'Symbol':<15} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'Win Rate':<10} {'Total PnL':<12} {'Avg PnL':<10}")
    print("-" * 100)
    
    for symbol in sorted(trades_df['symbol'].unique()):
        symbol_trades = trades_df[trades_df['symbol'] == symbol]
        wins = len(symbol_trades[symbol_trades['pnl'] > 0])
        losses = len(symbol_trades[symbol_trades['pnl'] < 0])
        win_rate = wins / len(symbol_trades) * 100 if len(symbol_trades) > 0 else 0
        total_pnl = symbol_trades['pnl'].sum()
        avg_pnl = symbol_trades['pnl'].mean()
        
        print(f"{symbol:<15} {len(symbol_trades):<8} {wins:<6} {losses:<8} {win_rate:<10.1f}% {total_pnl:<12.2f} {avg_pnl:<10.2f}")
    
    return trades_df, positions


def analyze_current_positions():
    """Analyze current open positions"""
    print("\n" + "=" * 100)
    print("CURRENT OPEN POSITIONS ANALYSIS")
    print("=" * 100)
    
    try:
        cfg = yaml.safe_load(open('ml_bot/config.yaml'))
        ex = Exchange(cfg)
        
        pos_resp = ex.get_positions()
        positions = pos_resp.get('result', {}).get('list', [])
        
        open_positions = [p for p in positions if float(p.get('size', 0)) > 0]
        
        if not open_positions:
            print("\nNo open positions currently")
            return None
        
        print(f"\nTotal open positions: {len(open_positions)}")
        
        print(f"\n{'Symbol':<15} {'Side':<6} {'Size':<12} {'Entry':<10} {'Mark':<10} {'UnrPnL':<12} {'CumPnL':<12}")
        print("-" * 100)
        
        total_upl = 0
        total_cum = 0
        
        for p in open_positions:
            sym = p['symbol']
            side = p['side']
            size = float(p.get('size', 0))
            entry = float(p.get('avgPrice', 0))
            mark = float(p.get('markPrice', 0))
            upl = float(p.get('unrealisedPnl', 0))
            cum_pnl = float(p.get('cumRealisedPnl', 0))
            
            total_upl += upl
            total_cum += cum_pnl
            
            print(f"{sym:<15} {side:<6} {size:<12.4f} {entry:<10.4f} {mark:<10.4f} {upl:<12.2f} {cum_pnl:<12.2f}")
        
        print("-" * 100)
        print(f"{'TOTAL':<15} {'':<6} {'':<12} {'':<10} {'':<10} {total_upl:<12.2f} {total_cum:<12.2f}")
        
        # Analyze partial closes
        print("\n" + "=" * 100)
        print("PARTIAL CLOSE ANALYSIS")
        print("=" * 100)
        
        positions_with_cum = [p for p in open_positions if float(p.get('cumRealisedPnl', 0)) != 0]
        
        if positions_with_cum:
            print(f"\nPositions with partial closes: {len(positions_with_cum)}")
            print("\nThese positions have cumRealisedPnl != 0, indicating partial closes:")
            for p in positions_with_cum:
                sym = p['symbol']
                cum_pnl = float(p.get('cumRealisedPnl', 0))
                upl = float(p.get('unrealisedPnl', 0))
                print(f"  {sym}: CumRealisedPnL={cum_pnl:.2f}, UnrealisedPnL={upl:.2f}")
        else:
            print("\nNo positions with partial closes detected")
        
        return open_positions
        
    except Exception as e:
        print(f"Error getting positions: {e}")
        return None


def analyze_close_logic():
    """Analyze position closing logic from logs"""
    print("\n" + "=" * 100)
    print("POSITION CLOSE LOGIC ANALYSIS")
    print("=" * 100)
    
    log_file = 'selective_ml_supervisor.log'
    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return
    
    close_events = []
    partial_closes = []
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Look for close signals
            if 'CLOSE' in line or 'EXIT' in line or 'REDUCE' in line:
                # Extract timestamp
                ts_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = ts_match.group(1) if ts_match else None
                
                close_events.append({
                    'timestamp': timestamp,
                    'line': line.strip()
                })
            
            # Look for partial close indicators
            if 'partial' in line.lower() or 'reduce' in line.lower():
                ts_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = ts_match.group(1) if ts_match else None
                
                partial_closes.append({
                    'timestamp': timestamp,
                    'line': line.strip()
                })
    
    print(f"\nTotal close-related events: {len(close_events)}")
    print(f"Partial close events: {len(partial_closes)}")
    
    if close_events:
        print("\nRecent close events (last 20):")
        for event in close_events[-20:]:
            print(f"  [{event['timestamp']}] {event['line'][:150]}")
    
    if partial_closes:
        print("\nPartial close events (last 10):")
        for event in partial_closes[-10:]:
            print(f"  [{event['timestamp']}] {event['line'][:150]}")


def main():
    # Analyze signals
    signal_data = analyze_signal_log()
    
    # Analyze completed trades
    trade_data = analyze_trades_from_log()
    
    # Analyze current positions
    current_positions = analyze_current_positions()
    
    # Analyze close logic
    analyze_close_logic()
    
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    if signal_data:
        allowed_df, symbol_stats = signal_data
        print(f"\nTotal signals generated: {len(allowed_df)}")
        print(f"Unique symbols traded: {len(allowed_df['symbol'].unique())}")
    
    if trade_data is not None:
        trades_df, positions = trade_data
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df) * 100
        print(f"\nCompleted trades: {len(trades_df)}")
        print(f"Overall win rate: {win_rate:.1f}%")
        print(f"Total realized PnL: {trades_df['pnl'].sum():.2f} USDT")
    
    if current_positions:
        total_upl = sum(float(p.get('unrealisedPnl', 0)) for p in current_positions)
        print(f"\nOpen positions: {len(current_positions)}")
        print(f"Total unrealized PnL: {total_upl:.2f} USDT")
    
    print("\n" + "=" * 100)


if __name__ == '__main__':
    main()
