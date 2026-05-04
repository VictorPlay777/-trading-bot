def expectancy(trades):
    if not trades:
        return 0.0
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    p_win = len(wins) / len(trades)
    avg_win = sum(t["pnl"] for t in wins) / max(1, len(wins))
    avg_loss = abs(sum(t["pnl"] for t in losses) / max(1, len(losses)))
    return p_win * avg_win - (1 - p_win) * avg_loss

