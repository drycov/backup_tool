#!/bin/sh
set -e

OX_REPO="${OXIDIZED_GIT_REPO:-/var/lib/oxidized}"
mkdir -p "$OX_REPO"

# Shared volume may be owned by oxidized (UID 30000) when external profile ran first.
chmod -R a+rwx "$OX_REPO" 2>/dev/null || true

git config --global --add safe.directory "$OX_REPO" 2>/dev/null || true

mkdir -p "$OX_REPO/bin" "$OX_REPO/rsc"
chmod -R a+rwx "$OX_REPO/bin" "$OX_REPO/rsc" 2>/dev/null || true

python scripts/wait_for_db.py

WORKERS="${GUNICORN_WORKERS:-2}"
if [ "${OXIDIZED_ENGINE:-python}" = "python" ]; then
  WORKERS=1
  PYTHON_LOG="${OXIDIZED_PYTHON_LOG_PATH:-/var/lib/oxidized/oxidized-python.log}"
  if [ -d "$PYTHON_LOG" ]; then
    rm -rf "$PYTHON_LOG"
  fi
  touch "$PYTHON_LOG" 2>/dev/null || true
  chmod a+rw "$PYTHON_LOG" 2>/dev/null || true
else
  RUBY_LOG="${OXIDIZED_LOG_PATH:-/var/lib/oxidized/oxidized.log}"
  if [ -d "$RUBY_LOG" ]; then
    rm -rf "$RUBY_LOG"
  fi
  touch "$RUBY_LOG" 2>/dev/null || true
  chmod a+rw "$RUBY_LOG" 2>/dev/null || true
fi

exec gunicorn backup_tools.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$WORKERS" \
  --timeout 120
