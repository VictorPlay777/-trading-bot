#!/usr/bin/env python3
"""Set TP orders for all open positions"""
import yaml
from trader.exchange_demo import Exchange
from scanner import TP_PERCENT

def main():
    # Load config
    with open('config_scanner.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    ex = Exchange(cfg)
    
    # Get all positions
    pos_data = ex.get_positions()
    if pos_data.get('retCode') != 0:
        print(f"Error getting positions: {pos_data}")
        return
    
    positions = pos_data.get('result', {}).get('list', [])
    print(f"Found {len(positions)} open positions\n")
    
    for pos in positions:
        symbol = pos.get('symbol', '')
        side = pos.get('side', '')  # 'Buy' or 'Sell'
        size = float(pos.get('size', 0))
        entry_price = float(pos.get('avgPrice', 0))
        
        if size <= 0 or entry_price <= 0:
            print(f"Skipping {symbol}: invalid size={size} or entry={entry_price}")
            continue
        
        # Calculate TP price
        if side == 'Buy':  # Long position
            tp_price = entry_price * (1 + TP_PERCENT)
        else:  # Short position
            tp_price = entry_price * (1 - TP_PERCENT)
        
        print(f"Setting TP for {symbol}:")
        print(f"  Side: {side}, Size: {size}, Entry: {entry_price:.4f}")
        print(f"  TP Price: {tp_price:.4f} ({TP_PERCENT*100:.1f}%)")
        
        try:
            result = ex.set_take_profit(symbol, side, size, tp_price)
            if result.get('retCode') == 0:
                print(f"  ✓ TP ORDER SET SUCCESSFULLY\n")
            else:
                print(f"  ✗ FAILED: {result.get('retMsg', 'Unknown error')}\n")
        except Exception as e:
            print(f"  ✗ ERROR: {e}\n")

if __name__ == '__main__':
    main()
