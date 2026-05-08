#!/usr/bin/env python3
"""
V7 Comprehensive Local Analysis - uses only local files
"""
import os
import json
import csv
import re
from datetime import datetime
from collections import defaultdict, Counter

SIGNAL_LOG = 'ml_bot/logs/signal_log.csv'
TRADES_LOG = 'ml_bot/logs/trades.jsonl'
SUPERVISOR_LOG = 'selective_ml_supervisor.log'

def analyze_signal_log():
    print("=" * 100)
    print("V7 COMPREHENSIVE ANALYSIS")
    print("=" * 100)

    if not os.path.exists(SIGNAL_LOG):
        print(f"Signal log not found: {SIGNAL_LOG}")
        return None

    total_signals = 0
    allowed_signals = []

    with open(SIGNAL_LOG, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_signals += 1
            if row['allow_entry'] == 'True':
                allowed_signals.append(row)

    print(f"\nTotal signals logged: {total_signals}")
    print(f"Allowed signals (trades): {len(allowed_signals)}")

    if not allowed_signals:
        print("No allowed signals found!")
        return None

    by_symbol = defaultdict(list)
    for sig in allowed_signals:
        by_symbol[sig['symbol']].append(sig)

    print("\n" + "=" * 100)
    print("SIGNAL STATISTICS BY SYMBOL")
    print("=" * 100)

    header = f"{'Symbol':<15} {'Signals':<8} {'Long':<6} {'Short':<6} {'AvgConf':<10} {'AvgEV':<14} {'AvgScore':<10} {'Regimes':<20}"
    print(f"\n{header}")
    print("-" * 100)

    for symbol in sorted(by_symbol.keys()):
        sigs = by_symbol[symbol]
        longs = sum(1 for s in sigs if s['direction'] == 'long')
        shorts = sum(1 for s in sigs if s['direction'] == 'short')
        avg_conf = sum(float(s['confidence']) for s in sigs) / len(sigs)
        avg_ev = sum(float(s['ev']) for s in sigs) / len(sigs)
        avg_score = sum(float(s['score']) for s in sigs) / len(sigs)
        r_count = Counter(s['regime'] for s in sigs)
        regimes = '+'.join([f"{k}({v})" for k, v in r_count.most_common(2)])

        print(f"{symbol:<15} {len(sigs):<8} {longs:<6} {shorts:<6} "
              f"{avg_conf:<10.3f} {avg_ev:<14.6f} {avg_score:<10.3f} {regimes:<20}")

    print("\n" + "=" * 100)
    print("OVERALL SIGNAL STATISTICS")
    print("=" * 100)

    all_confs = [float(s['confidence']) for s in allowed_signals]
    all_evs = [float(s['ev']) for s in allowed_signals]
    all_scores = [float(s['score']) for s in allowed_signals]

    print(f"Total unique symbols: {len(by_symbol)}")
    longs_all = sum(1 for s in allowed_signals if s['direction'] == 'long')
    shorts_all = sum(1 for s in allowed_signals if s['direction'] == 'short')
    print(f"Long signals: {longs_all} ({longs_all/len(allowed_signals)*100:.1f}%)")
    print(f"Short signals: {shorts_all} ({shorts_all/len(allowed_signals)*100:.1f}%)")

    print(f"\nAverage confidence: {sum(all_confs)/len(all_confs):.3f}")
    print(f"Average EV: {sum(all_evs)/len(all_evs):.6f}")
    print(f"Average score: {sum(all_scores)/len(all_scores):.3f}")

    regimes = Counter(s['regime'] for s in allowed_signals)
    print("\nRegime distribution:")
    for regime, count in regimes.most_common():
        print(f"  {regime}: {count} ({count/len(allowed_signals)*100:.1f}%)")

    buckets = Counter(s['bucket'] for s in allowed_signals)
    print("\nConfidence bucket distribution:")
    for bucket, count in buckets.most_common():
        print(f"  {bucket}: {count} ({count/len(allowed_signals)*100:.1f}%)")

    reasons = Counter(s['reason'] for s in allowed_signals)
    print("\nAllowed reason distribution:")
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count} ({count/len(allowed_signals)*100:.1f}%)")

    return allowed_signals, by_symbol


def analyze_trades():
    print("\n" + "=" * 100)
    print("TRADE ANALYSIS FROM trades.jsonl")
    print("=" * 100)

    if not os.path.exists(TRADES_LOG):
        print(f"Trades log not found: {TRADES_LOG}")
        return None

    v7_trades = []
    with open(TRADES_LOG, 'r') as f:
        for line in f:
            try:
                trade = json.loads(line.strip())
                sid = trade.get('strategy_id', '')
                if 'v7' in sid.lower() or 'selective_ml' in sid.lower():
                    v7_trades.append(trade)
            except:
                pass

    seen_ids = set()
    unique_trades = []
    for t in v7_trades:
        tid = t.get('trade_id', '')
        if tid not in seen_ids:
            seen_ids.add(tid)
            unique_trades.append(t)

    if not unique_trades:
        print("\nNo v7 trades found. Analyzing ALL trades instead...")
        with open(TRADES_LOG, 'r') as f:
            for line in f:
                try:
                    trade = json.loads(line.strip())
                    tid = trade.get('trade_id', '')
                    if tid not in seen_ids:
                        seen_ids.add(tid)
                        unique_trades.append(trade)
                except:
                    pass
        print(f"Found {len(unique_trades)} total trades")

    trades = unique_trades
    print(f"\nTotal trades analyzed: {len(trades)}")

    wins = [t for t in trades if t.get('realized_pnl_net', 0) > 0]
    losses = [t for t in trades if t.get('realized_pnl_net', 0) < 0]
    breakeven = [t for t in trades if t.get('realized_pnl_net', 0) == 0]

    total_pnl = sum(t.get('realized_pnl_net', 0) for t in trades)

    print(f"Winning trades: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"Losing trades: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    print(f"Breakeven trades: {len(breakeven)}")
    print(f"\nTotal PnL: {total_pnl:.2f} USDT")
    print(f"Average PnL per trade: {total_pnl/len(trades):.2f} USDT")

    pnls = [t.get('realized_pnl_net', 0) for t in trades]
    pnls_sorted = sorted(pnls)
    median_pnl = pnls_sorted[len(pnls_sorted)//2] if pnls_sorted else 0
    print(f"Median PnL: {median_pnl:.2f} USDT")
    print(f"Best trade: {max(pnls):.2f} USDT")
    print(f"Worst trade: {min(pnls):.2f} USDT")

    print("\n" + "=" * 100)
    print("WIN RATE BY SYMBOL")
    print("=" * 100)

    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t.get('symbol', '?')].append(t)

    print(f"\n{'Symbol':<15} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'WR%':<7} {'TotPnL':<12} {'AvgPnL':<12}")
    print("-" * 100)

    all_symbol_stats = []
    for symbol in sorted(by_symbol.keys()):
        st = by_symbol[symbol]
        w = sum(1 for t in st if t.get('realized_pnl_net', 0) > 0)
        l = sum(1 for t in st if t.get('realized_pnl_net', 0) < 0)
        wr = w / len(st) * 100 if len(st) > 0 else 0
        tp = sum(t.get('realized_pnl_net', 0) for t in st)
        ap = tp / len(st) if len(st) > 0 else 0

        all_symbol_stats.append({
            'symbol': symbol, 'trades': len(st), 'wins': w,
            'losses': l, 'wr': wr, 'total_pnl': tp, 'avg_pnl': ap
        })

        print(f"{symbol:<15} {len(st):<8} {w:<6} {l:<8} {wr:<7.1f}% {tp:<12.2f} {ap:<12.2f}")

    return trades, all_symbol_stats


def analyze_exit_logic():
    print("\n" + "=" * 100)
    print("EXIT LOGIC ANALYSIS (PARTIAL CLOSES)")
    print("=" * 100)

    if not os.path.exists(TRADES_LOG):
        return

    all_trades = []
    with open(TRADES_LOG, 'r') as f:
        for line in f:
            try:
                trade = json.loads(line.strip())
                all_trades.append(trade)
            except:
                pass

    print(f"\nAnalyzing {len(all_trades)} trades for exit logic")

    stop_loss_trades = 0
    partial_tp_trades = 0
    single_exit_trades = 0
    exit_counts_list = []

    for t in all_trades:
        exit_reasons = t.get('exit_reasons', [])
        reasons_used = set(r['reason'] for r in exit_reasons)
        exit_counts_list.append(len(exit_reasons))

        if 'stop_loss' in reasons_used:
            stop_loss_trades += 1
        if len(exit_reasons) > 2:
            partial_tp_trades += 1
        if len(exit_reasons) <= 2:
            single_exit_trades += 1

    avg_exits = sum(exit_counts_list) / len(exit_counts_list) if exit_counts_list else 0
    sorted_exits = sorted(exit_counts_list)
    median_exits = sorted_exits[len(sorted_exits)//2] if sorted_exits else 0
    max_exits = max(exit_counts_list) if exit_counts_list else 0

    print(f"\nExit types distribution:")
    print(f"  Trades with stop-loss: {stop_loss_trades} ({stop_loss_trades/len(all_trades)*100:.1f}%)")
    print(f"  Trades with partial TP: {partial_tp_trades} ({partial_tp_trades/len(all_trades)*100:.1f}%)")
    print(f"  Trades with 1-2 exits: {single_exit_trades} ({single_exit_trades/len(all_trades)*100:.1f}%)")

    print(f"\nAverage exit events per trade: {avg_exits:.1f}")
    print(f"Median exit events: {median_exits}")
    print(f"Max exit events: {max_exits}")

    print("\n" + "=" * 100)
    print("DETAILED EXAMPLES OF PARTIAL CLOSE TRADES")
    print("=" * 100)

    sorted_by_exits = sorted(all_trades, key=lambda t: len(t.get('exit_reasons', [])), reverse=True)

    for i, trade in enumerate(sorted_by_exits[:5]):
        print(f"\n{i+1}. Trade: {trade.get('trade_id', '?')}")
        print(f"   Symbol: {trade.get('symbol', '?')} Dir: {trade.get('direction', '?')}")
        print(f"   Entry: {trade.get('entry_price', '?')} Qty: {trade.get('qty_total', '?')}")
        dur = trade.get('duration_sec', 0)
        print(f"   Duration: {dur:.0f}s ({dur/60:.1f}min)")
        print(f"   Net PnL: {trade.get('realized_pnl_net', 0):.2f} USDT")

        exit_qty_sum = trade.get('exit_reason_qty_sum', {})
        total_qty = float(trade.get('qty_total', 0)) or 1

        print(f"   Exit breakdown:")
        for reason, qty in sorted(exit_qty_sum.items()):
            pct = qty / total_qty * 100
            print(f"     {reason}: qty={qty:.0f} ({pct:.1f}%)")

        print(f"   Exit events ({len(trade.get('exit_reasons', []))}):")
        for er in trade.get('exit_reasons', [])[:12]:
            ts_str = datetime.fromtimestamp(er['ts']).strftime('%H:%M:%S') if er.get('ts') else '?'
            print(f"     [{ts_str}] {er['reason']} qty={er['qty']:.0f}")
        if len(trade.get('exit_reasons', [])) > 12:
            print(f"     ... and {len(trade.get('exit_reasons', [])) - 12} more")


def main():
    signal_data = analyze_signal_log()
    trade_data = analyze_trades()
    analyze_exit_logic()

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    if signal_data:
        allowed, by_symbol = signal_data
        print(f"\nTotal allowed signals: {len(allowed)}")
        print(f"Unique symbols scanned: {len(by_symbol)}")

    if trade_data:
        trades, symbol_stats = trade_data
        wins = sum(1 for t in trades if t.get('realized_pnl_net', 0) > 0)
        total_pnl = sum(t.get('realized_pnl_net', 0) for t in trades)
        print(f"\nCompleted trades: {len(trades)}")
        print(f"Win rate: {wins/len(trades)*100:.1f}%")
        print(f"Total realized PnL: {total_pnl:.2f} USDT")

        if symbol_stats:
            sorted_by_wr = sorted(symbol_stats, key=lambda x: x['wr'], reverse=True)
            print("\nBest performing symbols:")
            for s in sorted_by_wr[:5]:
                print(f"  + {s['symbol']}: {s['wr']:.1f}% WR, {s['total_pnl']:.2f} USDT ({s['trades']} trades)")

            print("\nWorst performing symbols:")
            for s in sorted_by_wr[-5:]:
                print(f"  - {s['symbol']}: {s['wr']:.1f}% WR, {s['total_pnl']:.2f} USDT ({s['trades']} trades)")

    print("\n")


if __name__ == '__main__':
    main()
</｜｜DSML｜｜parameter>
<task_progress>
- [x] Изучить текущую структуру v7 и его логи
- [x] Создать скрипт для анализа всех данных
- [ ] Запустить анализ и получить статистику
- [ ] Проанализировать винрейт по каждой монете
- [ ] Определить прибыльные и убыточные сигналы
- [ ] Изучить логику закрытия позиций
- [ ] Выяснить причину частичного закрытия позиций
- [ ] Создать детальный отчет со статистикой
</｜｜DSML｜｜parameter>
</｜｜DSML｜｜tool_calls>