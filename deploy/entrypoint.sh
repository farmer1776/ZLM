#!/bin/bash
set -euo pipefail

DB_HOST="${ZLM_DB_HOST:-db}"
DB_PORT="${ZLM_DB_PORT:-3306}"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Waiting for database at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 $MAX_RETRIES); do
    if python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${DB_HOST}', ${DB_PORT}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "Database is reachable."
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: Database not reachable after ${MAX_RETRIES} attempts." >&2
        exit 1
    fi
    echo "  Attempt $i/$MAX_RETRIES — retrying in ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

echo "Running database migrations..."
alembic upgrade head

echo "Starting gunicorn..."
exec gunicorn main:app -c /app/deploy/gunicorn.conf.py
