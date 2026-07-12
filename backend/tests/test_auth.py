import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, status

from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserResponse
from app.api.dependencies import get_current_user, require_admin

# -------------------------------------------------------------
# Security & Hashing Tests (Tests 3, 4, 10, 11, 12, 13)
# -------------------------------------------------------------

def test_password_hashing():
    """Verify that password is stored hashed and verified correctly."""
    plain = "secure_password_123"
    hashed = hash_password(plain)
    
    assert hashed != plain
    assert len(hashed) > 20
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong_password", hashed) is False

def test_jwt_generation_and_decoding():
    """Verify standard JWT access token creation, claims, and validation."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    
    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert "exp" in claims
    assert "iat" in claims
    
    # Check invalid token returns empty claims
    assert decode_access_token("invalid.token.value") == {}

# -------------------------------------------------------------
# Auth Dependencies Tests (Tests 8, 14, 15)
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_user_valid():
    """Verify active user extraction from valid JWT token."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    
    # Mock user from database
    mock_user = User(
        id=user_id,
        email="test@user.com",
        is_active=True,
        is_admin=False
    )
    
    # Mock db session execute returning mock_user
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_user
    mock_db.execute.return_value = mock_result
    
    user = await get_current_user(db=mock_db, token=token)
    assert user.id == user_id
    assert user.email == "test@user.com"

@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    """Verify exception raised for invalid token."""
    mock_db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_user(db=mock_db, token="invalid_jwt_token")
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_get_current_user_inactive():
    """Verify exception raised for inactive user."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    
    mock_user = User(
        id=user_id,
        email="inactive@user.com",
        is_active=False
    )
    
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_user
    mock_db.execute.return_value = mock_result
    
    with pytest.raises(HTTPException) as exc:
        await get_current_user(db=mock_db, token=token)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Inactive user account" in exc.value.detail

@pytest.mark.asyncio
async def test_require_admin_valid():
    """Verify require_admin permits admin users."""
    admin_user = User(is_admin=True)
    res = await require_admin(current_user=admin_user)
    assert res == admin_user

@pytest.mark.asyncio
async def test_require_admin_forbidden():
    """Verify require_admin rejects standard users with 403."""
    normal_user = User(is_admin=False)
    with pytest.raises(HTTPException) as exc:
        await require_admin(current_user=normal_user)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

# -------------------------------------------------------------
# Endpoint Tests using FastAPI TestClient (Tests 1, 2, 5, 6, 7, 9)
# -------------------------------------------------------------

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db

client = TestClient(app)

@pytest.fixture
def mock_db():
    """Fixture to mock DB session and override get_db dependency."""
    session = AsyncMock()
    
    async def mock_refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()
        if hasattr(obj, "created_at") and obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)
            
    session.refresh.side_effect = mock_refresh
    
    async def override_get_db():
        yield session
        
    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()

def test_register_user_success(mock_db):
    """Test successful user registration endpoint."""
    user_data = {
        "email": "newuser@example.com",
        "password": "strongpassword123",
        "full_name": "New User"
    }
    
    # Mock email check: return None (no user exists)
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db.execute.return_value = mock_result
    
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201
    
    data = response.json()
    assert "id" in data
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "hashed_password" not in data  # Assert password hash is not exposed

def test_register_user_duplicate(mock_db):
    """Test register user with existing email is rejected."""
    user_data = {
        "email": "duplicate@example.com",
        "password": "strongpassword123"
    }
    
    # Mock existing user
    mock_user = User(id=uuid.uuid4(), email="duplicate@example.com")
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_user
    mock_db.execute.return_value = mock_result
    
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_login_success(mock_db):
    """Test login with correct credentials."""
    login_data = {
        "email": "login@example.com",
        "password": "password123"
    }
    
    # Mock stored user
    mock_user = User(
        id=uuid.uuid4(),
        email="login@example.com",
        hashed_password=hash_password("password123"),
        is_active=True
    )
    
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_user
    mock_db.execute.return_value = mock_result
    
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_incorrect_password(mock_db):
    """Test login fails with incorrect password."""
    login_data = {
        "email": "login@example.com",
        "password": "wrongpassword"
    }
    
    mock_user = User(
        id=uuid.uuid4(),
        email="login@example.com",
        hashed_password=hash_password("password123"),
        is_active=True
    )
    
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = mock_user
    mock_db.execute.return_value = mock_result
    
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 400
    assert "Incorrect email or password" in response.json()["detail"]

def test_login_unknown_email(mock_db):
    """Test login fails safely with unknown email."""
    login_data = {
        "email": "unknown@example.com",
        "password": "password123"
    }
    
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db.execute.return_value = mock_result
    
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 400
    assert "Incorrect email or password" in response.json()["detail"]

def test_auth_me_success():
    """Test /me endpoint returns current user response when authorized."""
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    
    # Mock user returning from dependency get_current_user
    mock_user = User(
        id=user_id,
        email="me@example.com",
        full_name="Me User",
        is_active=True,
        is_admin=False,
        created_at=datetime.now(timezone.utc)
    )
    
    from app.api.dependencies import get_current_user
    async def override_get_current_user():
        return mock_user
        
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    try:
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["full_name"] == "Me User"
        assert "hashed_password" not in data
    finally:
        app.dependency_overrides.clear()

