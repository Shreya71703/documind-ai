from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings

# Create async engine. Use a safe connection pool.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set to True only for query debugging
    pool_pre_ping=True,
    future=True
)

# Session factory for creating async sessions
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Async database session dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
