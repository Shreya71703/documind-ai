from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserResponse, Token
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(
    request: Request,
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Register a new user account (rate-limited)."""
    email_normalized = user_in.email.strip().lower()
    
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == email_normalized))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    # Create new user
    hashed_pw = hash_password(user_in.password)
    new_user = User(
        email=email_normalized,
        hashed_password=hashed_pw,
        full_name=user_in.full_name,
        is_active=True,
        is_admin=False
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login_json(
    request: Request,
    login_in: UserLogin,
    db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate user credentials via JSON request payload (rate-limited)."""
    email_normalized = login_in.email.strip().lower()
    
    # Find user
    result = await db.execute(select(User).where(User.email == email_normalized))
    user = result.scalars().first()
    
    # Verify user credentials
    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")

@router.post("/login-oauth2", response_model=Token)
@limiter.limit("10/minute")
async def login_oauth2(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Token:
    """OAuth2 compatible form login (rate-limited, specifically for OpenAPI interactive docs)."""
    email_normalized = form_data.username.strip().lower()
    
    # Find user
    result = await db.execute(select(User).where(User.email == email_normalized))
    user = result.scalars().first()
    
    # Verify user credentials
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_user)
) -> UserResponse:
    """Retrieve details of the currently authenticated user session."""
    return current_user
