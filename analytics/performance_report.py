import numpy as np
from .expectancy import expectancy
from .regime_metrics import pnl_by_regime


def report(trades):
    pnls = np.array([t.get("pnl", 0.0) for t in trades], dtype=float)
    ret = pnls if len(pnls) else np.array([0.0])
    sharpe = float(ret.mean() / (ret.std() + 1e-12))
    downside = ret[ret < 0]
    sortino = float(ret.mean() / (downside.std() + 1e-12)) if len(downside) else 0.0
    gross_win = float(ret[ret > 0].sum())
    gross_loss = float(abs(ret[ret <= 0].sum()))
    pf = gross_win / (gross_loss + 1e-12)
    dd = float(min(0.0, np.minimum.accumulate(ret.cumsum()).min()))
    return {
        "trades": len(trades),
        "expectancy": expectancy(trades),
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": pf,
        "max_drawdown": dd,
        "by_regime": pnl_by_regime(trades),
    }

