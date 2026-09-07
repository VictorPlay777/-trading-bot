#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../dashboard/frontend"

if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build the frontend" >&2
    exit 1
fi

cd "$FRONTEND_DIR"
npm ci
npm run build
