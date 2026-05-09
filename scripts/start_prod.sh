#!/usr/bin/env bash
# Start oh-my-delivery backend in production mode.
#
# - Runs alembic upgrade head first so the schema is current.
# - Launches uvicorn with multiple worker processes and no auto-reload.
# - Binds 0.0.0.0 so it's reachable from outside the host (override with HOST).
#
# Tunables (env or args):
#   HOST=0.0.0.0
#   PORT=25001
#   WORKERS=4         # roughly 2*CPU+1 is a common starting point
#   LOG_LEVEL=info
#   SKIP_MIGRATE=0    # set to 1 to skip alembic upgrade head
#
# Usage:
#   ./scripts/start_prod.sh
#   PORT=80 WORKERS=8 ./scripts/start_prod.sh

set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-25001}"
WORKERS="${WORKERS:-4}"
LOG_LEVEL="${LOG_LEVEL:-info}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"

# Default to production env if not set; respect what's already in .env / shell.
# Settings.env literal accepts 'dev' | 'test' | 'prod'.
export ENV="${ENV:-prod}"
export PYTHONUNBUFFERED=1

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed. Install it first: https://docs.astral.sh/uv/" >&2
    exit 1
fi

if [ "$SKIP_MIGRATE" != "1" ]; then
    echo ">>> alembic upgrade head"
    uv run alembic upgrade head
fi

echo ">>> uvicorn app.main:app --host $HOST --port $PORT --workers $WORKERS"
exec uv run uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --no-access-log
