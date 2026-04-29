#!/usr/bin/env python3
"""Analyze YOLO bot trades to calculate win rate."""

import csv
import sys

def analyze_trades(file_path):
    """Analyze trades.csv and calculate win rate."""
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            
            wins = 0
            losses = 0
            total = 0
            total_pnl = 0
            win_pnl = 0
            loss_pnl = 0
            
            for row in reader:
                total += 1
                pnl = float(row.get('pnl', 0))
                total_pnl += pnl
                
                if pnl > 0:
                    wins += 1
                    win_pnl += pnl
                elif pnl < 0:
                    losses += 1
                    loss_pnl += pnl
            
            win_rate = (wins / total * 100) if total > 0 else 0
            avg_win = (win_pnl / wins) if wins > 0 else 0
            avg_loss = (loss_pnl / losses) if losses > 0 else 0
            
            print("=" * 50)
            print("YOLO Bot Trade Analysis")
            print("=" * 50)
            print(f"Total Trades: {total}")
            print(f"Wins: {wins}")
            print(f"Losses: {losses}")
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Total PnL: ${total_pnl:.2f}")
            print(f"Win PnL: ${win_pnl:.2f}")
            print(f"Loss PnL: ${loss_pnl:.2f}")
            print(f"Average Win: ${avg_win:.2f}")
            print(f"Average Loss: ${avg_loss:.2f}")
            print(f"Profit Factor: {abs(win_pnl / loss_pnl) if loss_pnl != 0 else 'N/A'}")
            print("=" * 50)
            
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "logs/trades.csv"
    analyze_trades(file_path)
