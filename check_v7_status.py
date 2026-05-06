#!/usr/bin/env python3
"""
Quick diagnostic script to check v7 bot status:
- Current balance and PnL
- Open positions
- Recent signals from log
"""
import sys
import os
import re
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_bot.trader.exchange_demo import Exchange
import yaml

def main():
    # Load config
    cfg = yaml.safe_load(open('ml_bot/config.yaml'))
    ex = Exchange(cfg)
    
    print("=" * 80)
    print("V7 BOT STATUS CHECK")
    print("=" * 80)
    
    # 1. Wallet balance
    print("\n[1] WALLET BALANCE")
    print("-" * 80)
    try:
        wb = ex.get_wallet_balance()
        result = wb.get('result', {})
        total = float(result.get('totalWalletBalance', 0))
        equity = float(result.get('totalEquity', 0))
        upl = float(result.get('totalPerpUPL', 0))
        
        print(f"Total Wallet Balance: {total:,.2f} USDT")
        print(f"Total Equity:         {equity:,.2f} USDT")
        print(f"Unrealized PnL:       {upl:+,.2f} USDT")
        print(f"Balance Change:       {equity - 1_000_000:+,.2f} USDT (from 1M start)")
    except Exception as e:
        print(f"ERROR getting balance: {e}")
    
    # 2. Open positions
    print("\n[2] OPEN POSITIONS")
    print("-" * 80)
    try:
        pos_resp = ex.get_positions()
        positions = pos_resp.get('result', {}).get('list', [])
        
        open_positions = [p for p in positions if float(p.get('size', 0)) > 0]
        
        if not open_positions:
            print("No open positions")
        else:
            print(f"Found {len(open_positions)} open positions:\n")
            total_upl = 0
            total_cum_realised = 0
            
            for p in open_positions:
                sym = p['symbol']
                side = p['side']
                size = float(p.get('size', 0))
                entry = float(p.get('avgPrice', 0))
                mark = float(p.get('markPrice', 0))
                upl = float(p.get('unrealisedPnl', 0))
                cum_pnl = float(p.get('cumRealisedPnl', 0))
                
                total_upl += upl
                total_cum_realised += cum_pnl
                
                print(f"  {sym:15s} {side:5s} size={size:12.4f} entry={entry:10.4f} mark={mark:10.4f}")
                print(f"                  unrealizedPnl={upl:+10.2f}  cumRealisedPnl={cum_pnl:+10.2f}")
            
            print(f"\n  TOTALS: Unrealized={total_upl:+,.2f}  CumRealised={total_cum_realised:+,.2f}")
    except Exception as e:
        print(f"ERROR getting positions: {e}")
    
    # 3. Check recent log activity
    print("\n[3] RECENT V7 ACTIVITY (last 50 lines)")
    print("-" * 80)
    try:
        log_file = 'selective_ml_supervisor.log'
        
        # Get last 50 lines with v7 or recent activity
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Find v7 boot line
        v7_boot = None
        for line in reversed(lines):
            if 'strategy_id=v7' in line and 'BOOT' in line:
                v7_boot = line.strip()
                break
        
        if v7_boot:
            print(f"Last v7 boot: {v7_boot[:120]}...")
        
        # Count signals and state changes since v7 boot
        v7_started = False
        signal_count = 0
        create_count = 0
        close_count = 0
        
        for line in lines:
            if 'strategy_id=v7' in line and 'BOOT' in line:
                v7_started = True
                continue
            
            if v7_started:
                if '[SIGNAL]' in line and 'allow=True' in line:
                    signal_count += 1
                if '[STATE CREATE]' in line:
                    create_count += 1
                if '[TRADE RECORDED]' in line:
                    close_count += 1
        
        print(f"\nSince v7 boot:")
        print(f"  Allowed signals:  {signal_count}")
        print(f"  Positions opened: {create_count}")
        print(f"  Trades closed:    {close_count}")
        
        # Show last 10 allowed signals
        print("\n  Last 10 allowed signals:")
        re_signal = re.compile(r'\[SIGNAL\] (\S+) dir=(\S+) conf=(\S+).*allow=True')
        allowed_signals = []
        
        for line in reversed(lines):
            m = re_signal.search(line)
            if m:
                allowed_signals.append((m.group(1), m.group(2), m.group(3)))
                if len(allowed_signals) >= 10:
                    break
        
        for sym, direction, conf in reversed(allowed_signals):
            print(f"    {sym:15s} {direction:5s} conf={conf}")
        
        # Show last 5 position creates
        print("\n  Last 5 positions opened:")
        re_create = re.compile(r'\[STATE CREATE\] (\S+) side=(\S+) qty=(\S+) entry=(\S+)')
        creates = []
        
        for line in reversed(lines):
            m = re_create.search(line)
            if m:
                creates.append((m.group(1), m.group(2), m.group(3), m.group(4)))
                if len(creates) >= 5:
                    break
        
        for sym, side, qty, entry in reversed(creates):
            print(f"    {sym:15s} {side:5s} qty={qty:12s} entry={entry}")
        
    except Exception as e:
        print(f"ERROR reading log: {e}")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
