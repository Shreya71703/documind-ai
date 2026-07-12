import uuid
from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# Configure OAuth2 scheme for bearer tokens
# Maps to the future form-login route for FastAPI interactive docs support
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login-oauth2",
    auto_error=True
)

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """FastAPI dependency to extract, decode, validate JWT and return the authenticated User ORM object."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode JWT payload
    payload = decode_access_token(token)
    token_sub: str = payload.get("sub")
    if not token_sub:
        raise credentials_exception
        
    try:
        user_uuid = uuid.UUID(token_sub)
    except ValueError:
        raise credentials_exception
        
    # Query database for user
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalars().first()
    
    if not user:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    return user

async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """FastAPI dependency that restricts route access to administrative users only."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privilege required"
        )
    return current_user
