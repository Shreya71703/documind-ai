#!/bin/sh

echo "Waiting for database connection..."
python -c "
import asyncio, time
from app.core.config import settings
from app.core.database import engine

async def check_db():
    for attempt in range(1, 31):
        try:
            async with engine.connect() as conn:
                print(f'Database connection established on attempt {attempt}.')
                return True
        except Exception as e:
            print(f'Waiting for database (attempt {attempt}/30): {e}')
            await asyncio.sleep(2)
    return False

if not asyncio.run(check_db()):
    print('Failed to connect to database after 30 attempts.')
    exit(1)
"

echo "Running Alembic database migrations..."
alembic upgrade head

echo "Starting Uvicorn server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
