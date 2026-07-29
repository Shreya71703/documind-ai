import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.user import User

DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

async def get_current_user(
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Returns a default system user context so all endpoints remain 100% accessible
    without any authentication, headers, tokens, or credentials required.
    """
    result = await db.execute(select(User).where(User.id == DEFAULT_USER_ID))
    user = result.scalars().first()
    if not user:
        user = User(
            id=DEFAULT_USER_ID,
            email="default@documind.ai",
            hashed_password="no_password",
            full_name="Default User",
            is_active=True,
            is_admin=True
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception:
            await db.rollback()
            result = await db.execute(select(User).where(User.id == DEFAULT_USER_ID))
            user = result.scalars().first()
    return user
