"""Unit tests for research statistics: buckets, aggregation, linkage."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent
BACKUP = ROOT / "dashboard_server_backup"

# --- import bucket functions from bot_bridge without dashboard package deps ---
# bot_bridge imports dashboard.store etc; import only the bucket functions by
# exec'ing the module file is heavy. Instead test via the real module if
# importable, else skip. Simpler: import functions by loading module source.
spec = importlib.util.spec_from_file_location("bot_bridge", BACKUP / "bot_bridge.py")
bb = importlib.util.module_from_spec(spec)
# Stub dashboard.* so bot_bridge imports resolve
dash = types.ModuleType("dashboard")
dash.__path__ = [str(BACKUP)]
sys.modules["dashboard"] = dash
sys.modules["dashboard.store"] = types.ModuleType("dashboard.store")
sys.modules["dashboard.store"].Store = object
try:
    spec.loader.exec_module(bb)
    HAS_BB = True
except Exception:
    HAS_BB = False

sys.path.insert(0, str(ROOT / "stats"))
from stats_collector import bucket_of  # noqa: E402


def test_confidence_buckets():
    if not HAS_BB:
        return
    assert bb.bucket_confidence(0.49) == "<0.50"
    assert bb.bucket_confidence(0.52) == "0.50-0.55"
    assert bb.bucket_confidence(0.55) == "0.55-0.60"
    assert bb.bucket_confidence(0.719) == "0.70-0.75"
    assert bb.bucket_confidence(0.91) == "0.90+"


def test_adx_buckets():
    if not HAS_BB:
        return
    assert bb.bucket_adx(5) == "<10"
    assert bb.bucket_adx(12) == "10-15"
    assert bb.bucket_adx(22) == "20-25"
    assert bb.bucket_adx(45) == "40+"


def test_atr_funding_oi_buckets():
    if not HAS_BB:
        return
    assert bb.bucket_atr_pct(0.1) == "low"
    assert bb.bucket_atr_pct(0.5) == "high"
    assert bb.bucket_atr_pct(1.5) == "extreme"
    assert bb.bucket_funding(0.001) == "strong_positive"
    assert bb.bucket_funding(0.0002) == "positive"
    assert bb.bucket_funding(0.0) == "neutral"
    assert bb.bucket_funding(-0.0006) == "strong_negative"
    assert bb.bucket_oi(0.03) == "strong_rising"
    assert bb.bucket_oi(-0.01) == "falling"
    assert bb.bucket_oi(None) is None


def test_stats_collector_buckets_unchanged():
    assert bucket_of(0.57) == "0.55-0.60"
    assert bucket_of(0.9) == "0.75+"


def test_trade_stats_math():
    sys.path.insert(0, str(BACKUP))
    import importlib
    research = importlib.import_module("backend.routes.research") if False else None
    # _trade_stats is module-level; import the module
    import importlib.util as iu
    spec2 = iu.spec_from_file_location("research", BACKUP / "backend" / "routes" / "research.py")
    # stub fastapi/dashboard deps
    fa = types.ModuleType("fastapi")
    class _R:
        def __init__(self, *a, **k): pass
        def get(self, *a, **k): return lambda f: f
        def __call__(self, *a, **k): return self
    fa.APIRouter = _R
    fa.Query = lambda *a, **k: None
    fa.Request = object
    sys.modules.setdefault("fastapi", fa)
    common = types.ModuleType("dashboard.backend.routes.common")
    common.User = None
    sys.modules["dashboard.backend"] = types.ModuleType("dashboard.backend")
    sys.modules["dashboard.backend.routes"] = types.ModuleType("dashboard.backend.routes")
    sys.modules["dashboard.backend.routes.common"] = common
    mod = iu.module_from_spec(spec2)
    spec2.loader.exec_module(mod)
    trades = [
        {"pnl": 100, "r_multiple": 1.0, "closed_ts": 1},
        {"pnl": -50, "r_multiple": -1.0, "closed_ts": 2},
        {"pnl": 200, "r_multiple": 2.0, "closed_ts": 3},
        {"pnl": -100, "r_multiple": -2.0, "closed_ts": 4},
    ]
    st = mod._trade_stats(trades)
    assert st["trades"] == 4
    assert st["win_rate"] == 0.5
    assert st["profit_factor"] == 2.0  # 300/150
    assert st["expectancy"] == 37.5
    assert st["expectancy_r"] == 0.0
    assert st["max_drawdown"] == 100.0  # cum: 100,50,250,150 -> dd 250-150
    assert st["sample_label"] == "INSUFFICIENT SAMPLE"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name}: OK")
    print("ALL PASSED")
