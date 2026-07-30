#!/bin/sh
set -e

echo "Running database readiness check..."
python -m app.wait_for_db

echo "Running Alembic database migrations..."
alembic upgrade head

echo "Starting Uvicorn server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --loop asyncio
