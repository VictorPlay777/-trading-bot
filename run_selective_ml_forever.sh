#!/usr/bin/env bash
set -euo pipefail

# Auto-restart wrapper for selective_ml_bot.py (server-side).
# Usage on server:
#   chmod +x run_selective_ml_forever.sh
#   nohup ./run_selective_ml_forever.sh >> selective_ml_supervisor.log 2>&1 &

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

# Lockfile to prevent multiple supervisor instances
LOCKFILE="selective_ml_supervisor.lock"
if [[ -f "$LOCKFILE" ]]; then
  PID=$(cat "$LOCKFILE")
  if ps -p "$PID" > /dev/null 2>&1; then
    echo "[supervisor] Already running (PID $PID). Exit." >&2
    exit 1
  else
    echo "[supervisor] Removing stale lockfile (PID $PID not running)." >&2
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

CFG="${SELECTIVE_CFG:-config.yaml}"
SLEEP_SEC="${SELECTIVE_RESTART_SEC:-5}"

echo "[supervisor] cwd=$BOT_DIR cfg=$CFG restart_sleep=${SLEEP_SEC}s"

while true; do
  echo "[supervisor] starting selective_ml_bot.py at $(date -Is)"
  set +e
  python3 selective_ml_bot.py --config "$CFG"
  code=$?
  set -e
  echo "[supervisor] selective_ml_bot.py exited code=$code at $(date -Is); sleeping ${SLEEP_SEC}s"
  sleep "$SLEEP_SEC"
done
