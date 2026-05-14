import json, csv, re
from datetime import datetime, timezone
from collections import defaultdict

# 1. Полный PnL из trades.jsonl
trades = [json.loads(l) for l in open("ml_bot/logs/trades.jsonl") if l.strip()]
total_pnl_trades = sum(t.get("realized_pnl_net", 0) for t in trades)
print(f"1. Суммарный realized PnL из trades.jsonl: ${total_pnl_trades:.2f}")

# 2. Стратегии с PnL
by_strat = defaultdict(float)
for t in trades:
    s = t.get("strategy_id", "?")
    by_strat[s] += t.get("realized_pnl_net", 0)
print("\n2. PnL по стратегиям:")
for s, pnl in sorted(by_strat.items(), key=lambda x: -x[1]):
    print(f"   {s}: ${pnl:.2f}")

# 3. Сделки, где realized_pnl_net может быть неполный — проверка по cumRealised
print("\n3. Поиск сделок с cumRealised:")
for t in trades[:5]:
    if "cum_realised_pnl" in t or "cumRealised" in str(t):
        print(f"   {t.get(trade_id,?)[:30]}: {t}")

# 4. PnL по дням (все сделки)
by_day = defaultdict(float)
for t in trades:
    dt = datetime.fromtimestamp(t.get("opened_ts", t.get("ts", 0)), tz=timezone.utc)
    day_key = dt.strftime("%Y-%m-%d")
    by_day[day_key] += t.get("realized_pnl_net", 0)
print("\n4. PnL по дням:")
for day in sorted(by_day.keys()):
    print(f"   {day}: ${by_day[day]:.2f}")

# 5. Поиск в supervisor логе — записи торговых результатов
print("\n5. Supervisor log: первые 20 строк с PnL или payout или realized:")
with open("selective_ml_supervisor.log") as f:
    for i, line in enumerate(f):
        if any(w in line.lower() for w in ["pnl", "payout", "realized", "trade_result", "closed"]):
            print(f"   {line.rstrip()[:250]}")
            if i > 30: break

# 6. Поиск строк с walletBalance или equity (snapshot баланса)
print("\n6. Supervisor log: балансовые снапшоты:")
with open("selective_ml_supervisor.log") as f:
    for i, line in enumerate(f):
        if "equity" in line.lower() or "wallet" in line.lower() or "balance" in line.lower():
            if any(x in line for x in ["total", "Info", "snapshot"]):
                print(f"   {line.rstrip()[:300]}")
                if i > 20: break

# 7. Сравнение cumRealised из API vs PnL из trades
print("\n7. CumRealised USDT из API (check_balance.py): -14577.83")
print(f"   Разница от PnL trades.jsonl: {total_pnl_trades + 14577.83:.2f}")
EOF
python3 find_profit.py
