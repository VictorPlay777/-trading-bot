#!/usr/bin/env python3
"""
Точка входа ML-бота: обёртка над temp_bot (scanner / run_live).
Зависимости: pip install -r temp_bot/requirements.txt

Примеры:
  python ml_bot.py scanner --config temp_bot/config_scanner.yaml
  python ml_bot.py scanner --config temp_bot/config_scanner.yaml --top 50 --size 10000
  python ml_bot.py live --config temp_bot/config.yaml
  python ml_bot.py live --config temp_bot/config_eth.yaml --resume
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMP_BOT = os.path.join(ROOT, "temp_bot")


def main() -> None:
    p = argparse.ArgumentParser(description="ML-бот (LogisticRegression + калибровка из temp_bot).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scanner", help="Мультивалютный сканер с дообучением моделей на топ-N парах.")
    ps.add_argument("--config", required=True, help="YAML, например temp_bot/config_scanner.yaml")
    ps.add_argument("--top", type=int, default=100, help="Сколько самых волатильных USDT perpetual брать")
    ps.add_argument("--size", type=float, default=50000.0, help="Размер позиции в USDT (как в scanner.py)")

    pl = sub.add_parser("live", help="Один символ, переобучение на новой свече, как run_live.py.")
    pl.add_argument("--config", required=True, help="YAML, например temp_bot/config.yaml")
    pl.add_argument("--resume", action="store_true", help="Передать флаг --resume в run_live.py")

    args = p.parse_args()
    if not os.path.isdir(TEMP_BOT):
        print(f"Не найден каталог temp_bot: {TEMP_BOT}", file=sys.stderr)
        sys.exit(1)

    exe = [sys.executable]
    if args.cmd == "scanner":
        cmd = exe + [
            "scanner.py",
            "--config",
            args.config,
            "--top",
            str(args.top),
            "--size",
            str(args.size),
        ]
    else:
        cmd = exe + ["run_live.py", "--config", args.config]
        if args.resume:
            cmd.append("--resume")

    rc = subprocess.call(cmd, cwd=TEMP_BOT)
    sys.exit(rc)


if __name__ == "__main__":
    main()
