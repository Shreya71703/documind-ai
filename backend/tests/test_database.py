import pytest
from app.models.base import Base
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.models.chat import ChatSession, ChatMessage, MessageRole, chat_session_documents
from app.core.database import get_db

def test_models_registered():
    """Verify that all models are successfully imported and registered in the metadata."""
    registered_tables = Base.metadata.tables.keys()
    
    assert "users" in registered_tables
    assert "documents" in registered_tables
    assert "chat_sessions" in registered_tables
    assert "chat_messages" in registered_tables
    assert "chat_session_documents" in registered_tables

def test_user_model_structure():
    """Verify key structure of the User model."""
    assert hasattr(User, "id")
    assert hasattr(User, "email")
    assert hasattr(User, "hashed_password")
    assert hasattr(User, "full_name")
    assert hasattr(User, "is_active")
    assert hasattr(User, "is_admin")
    assert hasattr(User, "documents")
    assert hasattr(User, "chat_sessions")

def test_document_model_structure():
    """Verify key structure of the Document model."""
    assert hasattr(Document, "id")
    assert hasattr(Document, "user_id")
    assert hasattr(Document, "original_filename")
    assert hasattr(Document, "stored_filename")
    assert hasattr(Document, "file_type")
    assert hasattr(Document, "file_size")
    assert hasattr(Document, "storage_path")
    assert hasattr(Document, "status")
    assert hasattr(Document, "document_hash")
    assert hasattr(Document, "chunk_count")
    assert hasattr(Document, "user")
    assert hasattr(Document, "chat_sessions")

def test_chat_session_structure():
    """Verify key structure of the ChatSession model."""
    assert hasattr(ChatSession, "id")
    assert hasattr(ChatSession, "user_id")
    assert hasattr(ChatSession, "title")
    assert hasattr(ChatSession, "is_pinned")
    assert hasattr(ChatSession, "user")
    assert hasattr(ChatSession, "messages")
    assert hasattr(ChatSession, "documents")

def test_chat_message_structure():
    """Verify key structure of the ChatMessage model."""
    assert hasattr(ChatMessage, "id")
    assert hasattr(ChatMessage, "chat_session_id")
    assert hasattr(ChatMessage, "role")
    assert hasattr(ChatMessage, "content")
    assert hasattr(ChatMessage, "sources")
    assert hasattr(ChatMessage, "confidence_score")
    assert hasattr(ChatMessage, "chat_session")

def test_db_dependency_exists():
    """Verify database session generator dependency exists."""
    assert get_db is not None

def test_alembic_config():
    """Verify that Alembic configuration can be parsed and the version scripts are valid."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Get current revisions
    revisions = list(script.walk_revisions())
    assert len(revisions) > 0
    
    # Verify our initial migration is registered
    rev_ids = [rev.revision for rev in revisions]
    assert "f9d784a0d9b4" in rev_ids
