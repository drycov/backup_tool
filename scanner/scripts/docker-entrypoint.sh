#!/bin/sh
set -e

mkdir -p /var/lib/oxidized

WORKERS="${GUNICORN_WORKERS:-2}"
if [ "${OXIDIZED_ENGINE:-python}" = "python" ]; then
  WORKERS=1
  PYTHON_LOG="${OXIDIZED_PYTHON_LOG_PATH:-/var/lib/oxidized/oxidized-python.log}"
  touch "$PYTHON_LOG" 2>/dev/null || true
else
  RUBY_LOG="${OXIDIZED_LOG_PATH:-/var/lib/oxidized/oxidized.log}"
  touch "$RUBY_LOG" 2>/dev/null || true
fi

exec gunicorn backup_tools.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$WORKERS" \
  --timeout 120
