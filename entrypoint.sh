#!/usr/bin/env bash
set -Eeuo pipefail

PYBIN="/app/.venv/bin/python"

# If pip isn't present in the venv, bootstrap it
if ! "$PYBIN" -m pip --version >/dev/null 2>&1; then
  "$PYBIN" -m ensurepip --upgrade
  "$PYBIN" -m pip install --upgrade pip
fi

# Now install extra dependencies
"$PYBIN" -m pip install --no-cache-dir -r /app/requirements.txt

# Hand off to the original Letta entrypoint
exec /usr/local/bin/docker-entrypoint.sh "$@"