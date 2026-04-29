#!/bin/bash
# Analyze YOLO trades using awk for speed

cd ~/-trading-bot
awk -F',' '
NR==1 {next}
{
    pnl = $NF  # Assuming pnl is the last column
    gsub(/"/, "", pnl)  # Remove quotes if present
    if (pnl != "") {
        total++
        total_pnl += pnl
        if (pnl > 0) {
            wins++
            win_pnl += pnl
        } else if (pnl < 0) {
            losses++
            loss_pnl += pnl
        }
    }
}
END {
    win_rate = (wins / total * 100) if total > 0 else 0
    avg_win = (win_pnl / wins) if wins > 0 else 0
    avg_loss = (loss_pnl / losses) if losses > 0 else 0
    profit_factor = (win_pnl / -loss_pnl) if loss_pnl != 0 else "N/A"
    
    print "=================================================="
    print "YOLO Bot Trade Analysis"
    print "=================================================="
    print "Total Trades: " total
    print "Wins: " wins
    print "Losses: " losses
    printf "Win Rate: %.2f%%\n", win_rate
    printf "Total PnL: $%.2f\n", total_pnl
    printf "Win PnL: $%.2f\n", win_pnl
    printf "Loss PnL: $%.2f\n", loss_pnl
    printf "Average Win: $%.2f\n", avg_win
    printf "Average Loss: $%.2f\n", avg_loss
    print "Profit Factor: " profit_factor
    print "=================================================="
}
' logs/trades.csv
