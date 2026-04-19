#!/bin/bash
# Analyze current session statistics

cd ~/-trading-bot

LATEST_LOG=$(ls -t bot_*.log 2>/dev/null | head -1)

echo "=========================================="
echo "   SESSION ANALYSIS"
echo "=========================================="
echo "Log file: $LATEST_LOG"
echo ""

# Check for session stats
SESSION_COUNT=$(grep -c "SESSION" "$LATEST_LOG" 2>/dev/null || echo "0")
if [ "$SESSION_COUNT" -gt 0 ]; then
    echo "📊 SESSION STATISTICS:"
    grep "SESSION" "$LATEST_LOG" | tail -5
    echo ""
else
    echo "⚠️  No session stats found - bot may be running old version"
    echo ""
fi

# Overall stats
echo "📈 OVERALL STATS:"
grep "Trade stats:" "$LATEST_LOG" | tail -3

echo ""
echo "🎯 TOP PERFORMING SYMBOLS:"
grep "Best performing symbols:" "$LATEST_LOG" | tail -1

echo ""
echo "❌ ERRORS ANALYSIS:"
echo "---"
echo "StopLoss/TP errors:"
grep -c "StopLoss.*should greater\|StopLoss.*should lower" "$LATEST_LOG" 2>/dev/null || echo "0"
echo ""
echo "Zero position errors:"
grep -c "zero position" "$LATEST_LOG" 2>/dev/null || echo "0"
echo ""
echo "API errors:"
grep "Bybit API Error" "$LATEST_LOG" 2>/dev/null | tail -5
echo ""
echo "Smart SL errors:"
grep "Error in smart stop" "$LATEST_LOG" 2>/dev/null | tail -5

echo ""
echo "💰 RECENT TRADES:"
grep "Recorded trade:" "$LATEST_LOG" 2>/dev/null | tail -10

echo ""
echo "🔥 HIGH SLIPPAGE (>2%):"
grep "High slippage" "$LATEST_LOG" 2>/dev/null | tail -10

echo ""
echo "=========================================="
echo "Analysis complete!"
