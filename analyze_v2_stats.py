"""
Analyze v2 professional statistics data
"""
import json
import sys
from pathlib import Path
from collections import defaultdict
from stats.advanced_metrics import AdvancedMetricsCalculator


def load_jsonl(path):
    """Load records from jsonl file, skipping schema header"""
    records = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Skip schema headers
                    if data.get('schema') in ['signal_v2', 'trade_v2', 'equity_v2', 'v2']:
                        if len(data) <= 5:  # likely just header
                            continue
                    records.append(data)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print(f"File not found: {path}")
    return records


def analyze_signals(signals):
    """Analyze signal data"""
    print("\n" + "=" * 70)
    print("SIGNAL ANALYSIS")
    print("=" * 70)
    
    if not signals:
        print("No signals found.")
        return
    
    total = len(signals)
    accepted = [s for s in signals if s.get('decision') == 'ACCEPTED']
    rejected = [s for s in signals if s.get('decision') == 'REJECTED']
    
    print(f"Total signals: {total}")
    print(f"Accepted: {len(accepted)} ({len(accepted)/total*100:.1f}%)")
    print(f"Rejected: {len(rejected)} ({len(rejected)/total*100:.1f}%)")
    
    if accepted:
        confs = [s.get('signal_score', 0) for s in accepted]
        print(f"Accepted avg confidence: {sum(confs)/len(confs):.3f}")
    
    # By symbol
    by_symbol = defaultdict(int)
    for s in signals:
        by_symbol[s.get('symbol', 'unknown')] += 1
    
    print("\nTop 5 symbols:")
    for sym, count in sorted(by_symbol.items(), key=lambda x: -x[1])[:5]:
        print(f"  {sym}: {count} signals")
    
    # By regime
    by_regime = defaultdict(int)
    for s in signals:
        by_regime[s.get('market_regime', 'unknown')] += 1
    
    print("\nBy regime:")
    for regime, count in sorted(by_regime.items(), key=lambda x: -x[1]):
        print(f"  {regime}: {count} signals")


def analyze_trades(trades):
    """Analyze trade data"""
    print("\n" + "=" * 70)
    print("TRADE ANALYSIS")
    print("=" * 70)
    
    if not trades:
        print("No trades found.")
        return
    
    print(f"Total trades: {len(trades)}")
    
    # Calculate comprehensive statistics
    metrics = AdvancedMetricsCalculator()
    stats = metrics.calculate_trade_statistics(trades)
    
    print(f"Win rate: {stats['win_rate']:.1%}")
    print(f"Net profit: ${stats['net_profit']:.2f}")
    print(f"Gross profit: ${stats['gross_profit']:.2f}")
    print(f"Gross loss: ${stats['gross_loss']:.2f}")
    print(f"Profit factor: {stats['profit_factor']:.2f}")
    print(f"Expectancy: ${stats['expectancy']:.2f}")
    print(f"Average win: ${stats['average_win']:.2f}")
    print(f"Average loss: ${stats['average_loss']:.2f}")
    print(f"Max win: ${stats['max_win']:.2f}")
    print(f"Max loss: ${stats['max_loss']:.2f}")
    print(f"Average R: {stats['average_r']:.2f}")
    print(f"Max consecutive wins: {stats['max_consecutive_wins']}")
    print(f"Max consecutive losses: {stats['max_consecutive_losses']}")
    
    # By symbol
    by_symbol = metrics.calculate_categorized_statistics(trades, 'symbol')
    if by_symbol:
        print("\nBy symbol:")
        for sym, s in sorted(by_symbol.items(), key=lambda x: -x[1].get('net_profit', 0)):
            print(f"  {sym}: {s['total_trades']} trades, WR {s['win_rate']:.1%}, PnL ${s['net_profit']:.2f}")
    
    # By side
    by_side = metrics.calculate_categorized_statistics(trades, 'side')
    if by_side:
        print("\nBy side:")
        for side, s in by_side.items():
            print(f"  {side}: {s['total_trades']} trades, WR {s['win_rate']:.1%}, PnL ${s['net_profit']:.2f}")
    
    # By strategy version
    by_strategy = metrics.calculate_categorized_statistics(trades, 'strategy_version')
    if by_strategy:
        print("\nBy strategy version:")
        for version, s in by_strategy.items():
            print(f"  {version}: {s['total_trades']} trades, WR {s['win_rate']:.1%}, PnL ${s['net_profit']:.2f}")
    
    # MAE/MFE analysis
    if trades and 'mae_pct' in trades[0]:
        avg_mae = sum(t.get('mae_pct', 0) for t in trades) / len(trades)
        avg_mfe = sum(t.get('mfe_pct', 0) for t in trades) / len(trades)
        print(f"\nAverage MAE: {avg_mae:.2f}%")
        print(f"Average MFE: {avg_mfe:.2f}%")


def analyze_equity(equity_snapshots):
    """Analyze equity data"""
    print("\n" + "=" * 70)
    print("EQUITY ANALYSIS")
    print("=" * 70)
    
    if not equity_snapshots:
        print("No equity snapshots found.")
        return
    
    print(f"Total snapshots: {len(equity_snapshots)}")
    
    first = equity_snapshots[0]
    last = equity_snapshots[-1]
    
    print(f"Starting equity: ${first.get('equity', 0):.2f}")
    print(f"Ending equity: ${last.get('equity', 0):.2f}")
    print(f"Total return: ${last.get('equity', 0) - first.get('equity', 0):.2f}")
    
    # Get max drawdown from snapshots
    max_dd = max(s.get('drawdown_pct', 0) for s in equity_snapshots)
    print(f"Max drawdown: {max_dd:.2f}%")
    
    final_peak = max(s.get('peak_equity', 0) for s in equity_snapshots)
    print(f"Peak equity: ${final_peak:.2f}")


def main():
    logs_dir = Path("logs")
    
    signals = load_jsonl(logs_dir / "signals_v2.jsonl")
    trades = load_jsonl(logs_dir / "trades_v2.jsonl")
    equity = load_jsonl(logs_dir / "equity_snapshots_v2.jsonl")
    
    print("=" * 70)
    print("V2 PROFESSIONAL STATISTICS REPORT")
    print("=" * 70)
    
    analyze_signals(signals)
    analyze_trades(trades)
    analyze_equity(equity)
    
    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70)


if __name__ == "__main__":
    main()