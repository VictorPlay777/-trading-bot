import json

from dashboard.bot_bridge import trade_row_from_record
from dashboard.store import Store


SAMPLE = json.loads(
    r'''{"schema": "selective_trade_v1", "strategy_id": "v7_stats_collection_buckets_2026-05-05", "trade_id": "TIAUSDT_1788793674", "symbol": "TIAUSDT", "direction": "short", "opened_ts": 1788793674.1, "closed_ts": 1788793772.9, "duration_sec": 98.8, "entry_price": 0.2178, "qty_total": "45902.1", "qty_closed": "45902.1", "leverage": 1, "stop_loss_price": 0.2190, "take_profit_levels": {"tp1": 0.2166, "tp2": 0.2166, "tp3": 0.2142}, "signal": {"confidence": 0.77, "score": 0.635, "ev": -0.0015, "regime": "chop", "agreement": 3, "uncertainty": 0.0, "spread_bps": 1.2, "depth_usdt": 20000.0, "atr": 0.0024, "adx": 0.0, "funding_rate": 0.0001, "size_mult": 1.0}, "exit_reasons": [{"reason": "tp1_full", "qty": "45902.1", "ts": 1788793772.5}], "exit_reason_qty_sum": {"tp1_full": 45902.1}, "cum_realised_pnl_entry": -100.0, "cum_realised_pnl_close": 38.49, "realized_pnl_net": 138.49, "pnl_source": "bybit_closed_pnl", "entry_fees_est": 6.0, "exit_fees_est": 6.0, "funding_estimate": 0.0, "notional_entry": 9997.48, "exit_price": 0.2165}'''
)


def test_trade_upsert_filters_pagination_and_r_multiple(tmp_path):
    store = Store(str(tmp_path / "dashboard.db"))
    row = trade_row_from_record(SAMPLE)
    assert row["side"] == "short"
    assert row["exit_reason"] == "tp1_full"
    assert row["r_multiple"] > 2.5
    store.upsert_trade(row)
    row["trade_id"] = "ETHUSDT_2"
    row["symbol"] = "ETHUSDT"
    row["pnl"] = -1.0
    row["side"] = "long"
    store.upsert_trade(row)

    wins, total = store.list_trades({"result": "win", "symbol": "TIAUSDT"}, limit=10, offset=0)
    assert total == 1
    assert wins[0]["trade_id"] == "TIAUSDT_1788793674"
    page, total = store.list_trades({}, limit=1, offset=1)
    assert total == 2
    assert len(page) == 1

    store.update_trade_pnl("ETHUSDT_2", 5.0, 2000.0, "patch")
    assert store.get_trade("ETHUSDT_2")["pnl_source"] == "patch"
