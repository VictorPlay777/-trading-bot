#!/usr/bin/env bash
set -euo pipefail

# Auto-restart wrapper for selective_ml_bot_v10.py (V10 research framework).
# Usage on server:
#   chmod +x run_v10_forever.sh
#   nohup ./run_v10_forever.sh >> v10_supervisor.log 2>&1 &

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

# Lockfile to prevent multiple supervisor instances
LOCKFILE="v10_supervisor.lock"
if [[ -f "$LOCKFILE" ]]; then
  PID=$(cat "$LOCKFILE")
  if ps -p "$PID" > /dev/null 2>&1; then
    echo "[v10-supervisor] Already running (PID $PID). Exit." >&2
    exit 1
  else
    echo "[v10-supervisor] Removing stale lockfile (PID $PID not running)." >&2
    rm -f "$LOCKFILE"
  fi
fi
echo $$ > "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT

if [[ ! -f "venv/bin/activate" ]]; then
  echo "venv not found at $BOT_DIR/venv/bin/activate" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "venv/bin/activate"

CFG="${V10_CFG:-ml_bot/config.yaml}"
SLEEP_SEC="${V10_RESTART_SEC:-5}"

echo "[v10-supervisor] cwd=$BOT_DIR cfg=$CFG restart_sleep=${SLEEP_SEC}s"

while true; do
  echo "[v10-supervisor] starting selective_ml_bot_v10.py at $(date -Is)"
  set +e
  python3 ml_bot/selective_ml_bot_v10.py --config "$CFG"
  code=$?
  set -e
  echo "[v10-supervisor] selective_ml_bot_v10.py exited code=$code at $(date -Is); sleeping ${SLEEP_SEC}s"
  sleep "$SLEEP_SEC"
done
