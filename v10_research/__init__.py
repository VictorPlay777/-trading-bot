"""
V10 Research Framework
======================
Quant research platform for systematic edge discovery.

Goal: NOT max PnL. Goal: data, statistical significance, and reproducibility.

Components:
- signal_logger:    log every signal (allowed + rejected) to signals_all.jsonl
- shadow_tracker:   virtual position tracking for rejected signals
- mfe_mae_tracker:  Maximum Favorable / Adverse Excursion (R-units) for every trade
- feature_snapshot: freeze model features at entry (hash + JSON file)
- universe_filter:  Volume * Volatility-based TOP-N symbol selection

Conventions:
- All files under logs/v10/ (isolated from v7-v9)
- All trades carry strategy_id="v10_research_<DATE>"
- One signal == one trade (no DCA, no pyramiding, no reversals)
"""
from .signal_logger import SignalLogger
from .shadow_tracker import ShadowTracker
from .mfe_mae_tracker import MFEMAETracker
from .feature_snapshot import FeatureSnapshot
from .universe_filter import UniverseFilter
from .symbol_bias_tracker import SymbolBiasTracker

__all__ = [
    "SignalLogger",
    "ShadowTracker",
    "MFEMAETracker",
    "FeatureSnapshot",
    "UniverseFilter",
    "SymbolBiasTracker",
]
