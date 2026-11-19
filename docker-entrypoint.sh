#!/bin/sh

set -eu

MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-10}"
WAIT_SECONDS="${DB_WAIT_INTERVAL_SECONDS:-2}"
attempt=1

echo "Waiting for database connection..."
until alembic current >/dev/null 2>&1; do
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
        echo "Database connection failed after $MAX_ATTEMPTS attempts. Check DATABASE_URL, network access, and credentials." >&2
        exit 1
    fi
    echo "Database not ready (attempt $attempt/$MAX_ATTEMPTS); retrying in ${WAIT_SECONDS}s..."
    attempt=$((attempt + 1))
    sleep "$WAIT_SECONDS"
done

echo "Database is reachable. Running migrations..."
alembic upgrade head

echo "Seeding tenant and sample users..."
python -m scripts.insert_user

echo "Starting FastAPI..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
