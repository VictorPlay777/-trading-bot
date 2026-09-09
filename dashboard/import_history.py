from __future__ import annotations

import argparse
import json
from pathlib import Path

from dashboard.bot_bridge import trade_row_from_record
from dashboard.store import Store


def _records(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def import_history(logs_dir: str = "logs", db_path: str | None = None):
    logs = Path(logs_dir)
    store = Store(db_path)
    trade_rows = []
    trades_count = 0
    fills_count = 0
    for record in _records(logs / "trades.jsonl") or ():
        row = trade_row_from_record(record)
        store.upsert_trade(row)
        trade_rows.append(row)
        trades_count += 1

    for fill in _records(logs / "fills.jsonl") or ():
        fill = dict(fill)
        fill["raw_json"] = json.dumps(fill, ensure_ascii=False, default=str)
        store.upsert_fill(fill)
        fills_count += 1

    fees_updated = 0
    for row in trade_rows:
        opened_ms = int((float(row.get("opened_ts") or 0) - 60) * 1000)
        closed_ms = int((float(row.get("closed_ts") or row.get("opened_ts") or 0) + 60) * 1000)
        fees = store.sum_fees(row.get("symbol"), opened_ms, closed_ms)
        if fees > 0:
            current = store.get_trade(row["trade_id"])
            if current:
                current["fees_actual"] = fees
                store.upsert_trade(current)
                fees_updated += 1

    equity_note = ""
    if store.latest_equity() is None:
        equity_note = " No equity history imported: start equity is not available from trades."
    print(f"Imported {trades_count} trades, {fills_count} fills; updated actual fees for {fees_updated} trades.{equity_note}")
    return trades_count, fills_count, fees_updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    import_history(args.logs_dir, args.db)


if __name__ == "__main__":
    main()
