import asyncio
import sys
from app.core.database import engine

async def check_db():
    print("Checking database connectivity...", flush=True)
    for attempt in range(1, 31):
        try:
            async with engine.connect() as conn:
                print(f"Database connection successful on attempt {attempt}.", flush=True)
                return True
        except Exception as e:
            print(f"Waiting for database (attempt {attempt}/30): {e}", flush=True)
            await asyncio.sleep(2)
    return False

if __name__ == "__main__":
    if not asyncio.run(check_db()):
        print("Database connection timed out after 30 attempts.", flush=True)
        sys.exit(1)
