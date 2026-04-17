#!/bin/bash
# Анализатор торговли для конкретного запуска бота

LOG_FILE="${1:-bot.log}"

echo "=========================================="
echo "📊 АНАЛИЗ ТОРГОВЛИ: $LOG_FILE"
echo "=========================================="
echo ""

# Общая статистика
echo "=== ОБЩАЯ СТАТИСТИКА ==="
TOTAL_TRADES=$(grep -c "Recorded trade:" "$LOG_FILE" 2>/dev/null || echo "0")
echo "Всего сделок: $TOTAL_TRADES"

# Считаем PnL всех закрытых позиций
echo ""
echo "=== РАСЧЕТ PnL ==="
grep "Closed.*PnL:" "$LOG_FILE" 2>/dev/null | tail -n 200 | while read line; do
    echo "$line" | grep -oP 'PnL: \$[\d.-]+' | sed 's/PnL: \$//'
done > /tmp/pnl_values.txt

TOTAL_PNL=$(awk '{sum+=$1} END {printf "%.2f", sum}' /tmp/pnl_values.txt 2>/dev/null || echo "0.00")
WINS=$(grep "Closed.*PnL:" "$LOG_FILE" 2>/dev/null | grep -c "PnL: \$[0-9]")
LOSSES=$(grep "Closed.*PnL:" "$LOG_FILE" 2>/dev/null | grep -c "PnL: \$-")

if [ "$TOTAL_TRADES" -gt 0 ]; then
    WIN_RATE=$(echo "scale=1; $WINS * 100 / $TOTAL_TRADES" | bc 2>/dev/null || echo "0")
    echo "Прибыльных: $WINS"
    echo "Убыточных: $LOSSES"
    echo "Win Rate: ${WIN_RATE}%"
fi
echo "Общий PnL (последние 200): $${TOTAL_PNL}"

# Топ-20 худших сделок
echo ""
echo "=== 💀 ТОП-20 ХУДШИХ СДЕЛОК ==="
grep "Closed.*PnL: \$-" "$LOG_FILE" 2>/dev/null | sort -t'$' -k2 -n | head -20 | while read line; do
    echo "$line" | grep -oP '\w+USDT.*PnL: \$[\d.-]+'
done

# Топ-20 лучших сделок  
echo ""
echo "=== ✅ ТОП-20 ЛУЧШИХ СДЕЛОК ==="
grep "Closed.*PnL: \$[0-9]" "$LOG_FILE" 2>/dev/null | sort -t'$' -k2 -n -r | head -20 | while read line; do
    echo "$line" | grep -oP '\w+USDT.*PnL: \$[\d.-]+'
done

# Последние 10 ошибок API
echo ""
echo "=== ⚠️ ПОСЛЕДНИЕ 10 ОШИБОК ==="
grep "ERROR" "$LOG_FILE" 2>/dev/null | tail -10

echo ""
echo "=========================================="
echo "✅ Анализ завершен"
echo "=========================================="
