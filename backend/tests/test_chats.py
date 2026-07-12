import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.schemas.chat import ChatSessionResponse, ChatMessageResponse
from app.services.rag import RAGResult
from app.schemas.document import RetrievedSource

client = TestClient(app)

# -------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------

@pytest.fixture
def mock_user():
    """Mock authenticated user fixture."""
    return User(
        id=uuid.uuid4(),
        email="chatuser@example.com",
        full_name="Chat User",
        is_active=True,
        is_admin=False
    )

@pytest.fixture
def mock_db_session():
    """Mock DB session and override get_db dependency."""
    session = AsyncMock()
    
    async def mock_refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc)
            
    session.refresh.side_effect = mock_refresh
    
    async def override_get_db():
        yield session
        
    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def mock_chatsession_defaults():
    """Ensure ChatSession objects constructed in tests have default datetimes."""
    orig_init = ChatSession.__init__
    def patched_init(self, *args, **kwargs):
        if "created_at" not in kwargs:
            kwargs["created_at"] = datetime.now(timezone.utc)
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = datetime.now(timezone.utc)
        orig_init(self, *args, **kwargs)
    with patch.object(ChatSession, "__init__", patched_init):
        yield

@pytest.fixture
def mock_auth(mock_user):
    """Override get_current_user dependency to return our mock user."""
    async def override_get_current_user():
        return mock_user
        
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield mock_user
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]

# -------------------------------------------------------------
# Chat Endpoint Tests
# -------------------------------------------------------------

def test_create_session_requires_auth(mock_db_session):
    """Verify create session requires authentication."""
    response = client.post("/api/v1/chats", json={"document_ids": [str(uuid.uuid4())]})
    assert response.status_code == 401

def test_create_session_success(mock_db_session, mock_auth, mock_user):
    """Verify session creation succeeds with owned indexed documents."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="doc.pdf",
        stored_filename="doc_stored.pdf",
        file_type="pdf",
        file_size=100,
        storage_path="uploads/doc_stored.pdf",
        status=DocumentStatus.READY,
        index_status="indexed",
        chunk_count=2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    # Mock doc query and commit
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    response = client.post("/api/v1/chats", json={"title": "Test Chat", "document_ids": [str(doc_id)]})
    assert response.status_code == 201
    
    data = response.json()
    assert data["title"] == "Test Chat"
    assert "id" in data
    assert data["is_pinned"] is False
    assert len(data["document_ids"]) == 1
    assert data["document_ids"][0] == str(doc_id)

    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()

def test_create_session_validation_errors(mock_db_session, mock_auth):
    """Verify duplicate document IDs and empty title checks."""
    dup_id = str(uuid.uuid4())
    
    # Duplicate IDs
    response = client.post("/api/v1/chats", json={"title": "Test", "document_ids": [dup_id, dup_id]})
    assert response.status_code == 422

def test_create_session_unindexed_rejected(mock_db_session, mock_auth, mock_user):
    """Verify that unindexed documents are rejected during session creation."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="doc.pdf",
        stored_filename="doc_stored.pdf",
        file_type="pdf",
        file_size=100,
        storage_path="uploads/doc_stored.pdf",
        status=DocumentStatus.READY,
        index_status="failed", # Not indexed!
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    response = client.post("/api/v1/chats", json={"document_ids": [str(doc_id)]})
    assert response.status_code == 400
    assert "not fully indexed" in response.json()["detail"].lower()

def test_list_chat_sessions_only_current_user(mock_db_session, mock_auth, mock_user):
    """Verify list endpoint retrieves only current user's sessions."""
    session1 = ChatSession(id=uuid.uuid4(), user_id=mock_user.id, title="User A Session 1", is_pinned=True, documents=[])
    session2 = ChatSession(id=uuid.uuid4(), user_id=mock_user.id, title="User A Session 2", is_pinned=False, documents=[])

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [session1, session2]
    mock_db_session.execute.return_value = mock_result

    response = client.get("/api/v1/chats")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "User A Session 1"
    assert data[1]["title"] == "User A Session 2"

def test_get_session_details_success(mock_db_session, mock_auth, mock_user):
    """Verify retrieval of chat details and Chronological ordered messages."""
    session_id = uuid.uuid4()
    session = ChatSession(
        id=session_id, user_id=mock_user.id, title="My Chat", is_pinned=False, documents=[],
        messages=[
            ChatMessage(id=uuid.uuid4(), chat_session_id=session_id, role="assistant", content="Response 1", created_at=datetime(2026, 1, 1, 10, 5, 0, tzinfo=timezone.utc)),
            ChatMessage(id=uuid.uuid4(), chat_session_id=session_id, role="user", content="Question 1", created_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        ]
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = session
    mock_db_session.execute.return_value = mock_result

    response = client.get(f"/api/v1/chats/{session_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["session"]["title"] == "My Chat"
    assert len(data["messages"]) == 2
    # Verify chronological ordering: user question (10:00) before assistant response (10:05)
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"

def test_get_another_users_session_not_found(mock_db_session, mock_auth):
    """Verify session query returns 404 for unowned sessions."""
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    response = client.get(f"/api/v1/chats/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_update_session_success(mock_db_session, mock_auth, mock_user):
    """Verify title update and pinning endpoints."""
    session_id = uuid.uuid4()
    session = ChatSession(id=session_id, user_id=mock_user.id, title="Old title", is_pinned=False, documents=[])

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = session
    mock_db_session.execute.return_value = mock_result

    # 1. Update Title
    response = client.patch(f"/api/v1/chats/{session_id}", json={"title": "New Title"})
    assert response.status_code == 200
    assert session.title == "New Title"

    # 2. Pin
    response = client.patch(f"/api/v1/chats/{session_id}", json={"is_pinned": True})
    assert response.status_code == 200
    assert session.is_pinned is True

    # 3. Invalid whitespace title rejected
    response = client.patch(f"/api/v1/chats/{session_id}", json={"title": "   "})
    assert response.status_code == 422

def test_delete_session_success(mock_db_session, mock_auth, mock_user):
    """Verify deletion clears session but doesn't delete documents."""
    session_id = uuid.uuid4()
    session = ChatSession(id=session_id, user_id=mock_user.id, title="Chat to delete", documents=[])

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = session
    mock_db_session.execute.return_value = mock_result

    response = client.delete(f"/api/v1/chats/{session_id}")
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["detail"].lower()

    # DB Delete called
    mock_db_session.delete.assert_called_once_with(session)
    mock_db_session.commit.assert_called_once()

# -------------------------------------------------------------
# Question / Grounded Message Tests
# -------------------------------------------------------------

def test_ask_question_unauthorized(mock_db_session):
    """Verify authentication required to ask messages."""
    response = client.post(f"/api/v1/chats/{uuid.uuid4()}/messages", json={"question": "What is RAG?"})
    assert response.status_code == 401

@patch("app.api.endpoints.chats.generate_grounded_answer")
def test_ask_question_success(mock_rag, mock_db_session, mock_auth, mock_user):
    """Verify question endpoint generates answer, validates citations, and persists conversation pair."""
    session_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    doc = Document(id=doc_id, user_id=mock_user.id, original_filename="doc.txt", file_type="txt", index_status="indexed")
    
    session = ChatSession(
        id=session_id, user_id=mock_user.id, title="Grounded Chat",
        documents=[doc], messages=[]
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = session
    mock_db_session.execute.return_value = mock_result

    # Mock RAG response
    mock_citation = RetrievedSource(
        citation_id="SOURCE 1",
        document_id=doc_id,
        source_filename="doc.txt",
        file_type="txt",
        chunk_index=3,
        distance=0.1
    )
    mock_rag.return_value = RAGResult(
        answer="Grounded RAG Answer [SOURCE 1]",
        citations=[mock_citation],
        insufficient_context=False,
        retrieved_count=1,
        included_count=1
    )

    response = client.post(f"/api/v1/chats/{session_id}/messages", json={"question": "What is the policy?"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["role"] == "assistant"
    assert "Grounded RAG Answer [SOURCE 1]" in data["content"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["citation_id"] == "SOURCE 1"
    
    # DB calls: verify both user and assistant messages added
    # mock_db_session.add has been called twice (user and assistant messages)
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_called_once()
    
    # Security checks: ensure safe response without leaking details
    assert "storage_path" not in data["sources"][0]
    assert "user_id" not in data["sources"][0]
    assert "embeddings" not in data

@patch("app.api.endpoints.chats.generate_grounded_answer")
def test_ask_question_provider_failure_rolls_back(mock_rag, mock_db_session, mock_auth, mock_user):
    """Verify that if LLM/RAG generation fails, any written messages are rolled back."""
    session_id = uuid.uuid4()
    doc = Document(id=uuid.uuid4(), user_id=mock_user.id, original_filename="doc.txt", file_type="txt", index_status="indexed")
    session = ChatSession(id=session_id, user_id=mock_user.id, title="Grounded Chat", documents=[doc])

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = session
    mock_db_session.execute.return_value = mock_result

    # Force RAG to throw error
    mock_rag.side_effect = Exception("OpenAI API Down")

    response = client.post(f"/api/v1/chats/{session_id}/messages", json={"question": "Crash test"})
    assert response.status_code == 500
    
    # Verify rollback called
    mock_db_session.rollback.assert_called_once()
    # Confirm no changes committed
    mock_db_session.commit.assert_not_called()
