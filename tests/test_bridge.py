from dashboard.bot_bridge import BotBridge
from dashboard.store import Store


def bridge(tmp_path):
    return BotBridge(Store(str(tmp_path / "dashboard.db")), strategy_id="test-strategy")


def test_kill_switch_triggers_once_and_resets_on_utc_day(tmp_path):
    b = bridge(tmp_path)
    b.store.set_setting("risk", {"max_daily_loss_pct": 3.0})
    day_one = 1_800_000_000.0
    assert b.check_kill_switch(100_000, day_one) is False
    assert b.check_kill_switch(96_000, day_one + 60) is True
    events, total = b.store.list_events({"event_type": "RISK_LIMIT_REACHED"}, 10, 0)
    assert total == 1
    assert len(events) == 1
    next_day = day_one + 86_400
    assert b.check_kill_switch(96_000, next_day) is False
    assert b.control()["kill_switch_triggered"] is False


def test_risk_check_and_position_override(tmp_path):
    b = bridge(tmp_path)
    b.store.set_setting("risk", {"long_enabled": False, "allowed_symbols": ["BTCUSDT"], "max_open_positions": 1})
    sig = {"symbol": "BTCUSDT", "direction": "long"}
    assert b.risk_check(sig, [], 1000) == (False, "dashboard_long_disabled")
    b.store.set_setting("risk", {"allowed_symbols": ["BTCUSDT"], "max_open_positions": 1})
    b = BotBridge(b.store, strategy_id="test-strategy")
    assert b.risk_check(sig, [{"size": "1"}], 1000) == (False, "dashboard_max_positions")
    assert b.risk_check({"symbol": "ETHUSDT", "direction": "short"}, [], 1000) == (
        False,
        "dashboard_symbol_not_allowed",
    )

    b.store.set_setting("position_overrides", {"BTCUSDT": {"stop_loss": 99.0, "tp1": 101.0}})
    assert b.position_overrides("BTCUSDT")["stop_loss"] == 99.0
    assert b.position_overrides("BTCUSDT") is None


def test_log_sink_creates_expected_events(tmp_path):
    b = bridge(tmp_path)
    b._sink("[OPEN] TIAUSDT short qty=1 entry=1.0")
    b._sink("[EXIT] TIAUSDT reason=stop_loss qty=1 remaining=0")
    b._sink("[LOOP] get_positions failed: boom")
    events, _ = b.store.list_events({}, 20, 0)
    event_types = {event["event_type"] for event in events}
    assert {"POSITION_OPENED", "SL_HIT", "BYBIT_CONNECTION_ERROR"} <= event_types
    assert b._bybit_ok is False
