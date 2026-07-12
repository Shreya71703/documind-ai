import os
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus

client = TestClient(app)

# -------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_upload_dir(tmp_path):
    """Dynamically set settings.UPLOAD_DIR to a temporary path for each test."""
    old_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield
    settings.UPLOAD_DIR = old_upload_dir

@pytest.fixture
def mock_user():
    """Mock authenticated user fixture."""
    return User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        full_name="Test User",
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
# Document API Tests
# -------------------------------------------------------------

def test_upload_document_success(mock_db_session, mock_auth):
    """Test that a valid file upload succeeds, returns DocumentResponse, and saves the file."""
    # Mock database check: no duplicate document hash exists
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    # Perform request
    file_content = b"This is a valid test PDF content."
    file_name = "test_document.pdf"
    
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (file_name, file_content, "application/pdf")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["original_filename"] == "test_document.pdf"
    assert data["file_type"] == "pdf"
    assert data["file_size"] == len(file_content)
    assert data["status"] == "uploaded"
    assert data["chunk_count"] == 0
    assert "created_at" in data
    assert "updated_at" in data
    
    # Ensure security constraint: internal storage_path must NOT be exposed
    assert "storage_path" not in data

    # Verify database calls
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

    # Verify physical file was written to disk
    added_doc = mock_db_session.add.call_args[0][0]
    assert isinstance(added_doc, Document)
    assert os.path.exists(added_doc.storage_path)
    with open(added_doc.storage_path, "rb") as f:
        assert f.read() == file_content

def test_upload_document_authentication_required(mock_db_session):
    """Test that file upload fails with 401 when user is not authenticated."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", b"content", "application/pdf")}
    )
    assert response.status_code == 401

def test_upload_document_invalid_extension(mock_db_session, mock_auth):
    """Test that unsupported file extensions are rejected with a 400 error."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("script.exe", b"malicious content", "application/octet-stream")}
    )
    assert response.status_code == 400
    assert "extension" in response.json()["detail"].lower()

def test_upload_document_oversized(mock_db_session, mock_auth):
    """Test that files exceeding the size limit are rejected."""
    # Temporarily set limit to 0 MB to reject all uploads
    old_limit = settings.MAX_FILE_SIZE_MB
    settings.MAX_FILE_SIZE_MB = 0
    try:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", b"some bytes", "application/pdf")}
        )
        assert response.status_code == 400
        assert "size" in response.json()["detail"].lower()
    finally:
        settings.MAX_FILE_SIZE_MB = old_limit

def test_upload_document_duplicate_hash_same_user(mock_db_session, mock_auth, mock_user):
    """Test that a duplicate upload for the same user is rejected."""
    # Mock existing document with same hash owned by current user
    existing_doc = Document(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        original_filename="existing.pdf",
        stored_filename="stored_existing.pdf",
        file_type="pdf",
        file_size=123,
        storage_path="uploads/stored_existing.pdf",
        status=DocumentStatus.READY,
        document_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", # SHA-256 for empty bytes
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = existing_doc
    mock_db_session.execute.return_value = mock_result

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("new.pdf", b"", "application/pdf")}  # Empty content produces empty hash
    )
    assert response.status_code == 400
    assert "duplicate" in response.json()["detail"].lower()

def test_upload_document_failed_db_persistence_cleanup(mock_db_session, mock_auth):
    """Test that the physical file is deleted if db commit fails during upload."""
    # Mock duplicate check to succeed (return None)
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    # Force database commit to fail
    mock_db_session.commit.side_effect = SQLAlchemyError("Database connection failed")

    # Spy on the service's delete_file function
    with patch("app.api.endpoints.documents.delete_file", wraps=os.remove) as mock_delete:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")}
        )
        assert response.status_code == 500
        assert "database" in response.json()["detail"].lower() or "persist" in response.json()["detail"].lower()
        
        # Verify delete_file was called to clean up the stored file
        mock_delete.assert_called_once()
        # Verify that no file remains in the temporary upload directory
        assert len(os.listdir(settings.UPLOAD_DIR)) == 0

def test_upload_document_path_traversal_sanitized(mock_db_session, mock_auth):
    """Test that unsafe filename path traversal is sanitized and saved correctly."""
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("../../unsafe_name.pdf", b"safe content", "application/pdf")}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "unsafe_name.pdf"

    added_doc = mock_db_session.add.call_args[0][0]
    # Verify path is within UPLOAD_DIR
    assert os.path.dirname(added_doc.storage_path) == settings.UPLOAD_DIR

def test_list_documents_only_current_user(mock_db_session, mock_auth, mock_user):
    """Test listing documents returns only those belonging to the authenticated user."""
    # Create list of mock documents
    doc1 = Document(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        original_filename="user_doc1.pdf",
        stored_filename="stored1.pdf",
        file_type="pdf",
        file_size=100,
        storage_path="uploads/stored1.pdf",
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    doc2 = Document(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        original_filename="user_doc2.pdf",
        stored_filename="stored2.pdf",
        file_type="pdf",
        file_size=200,
        storage_path="uploads/stored2.pdf",
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc1, doc2]
    mock_db_session.execute.return_value = mock_result

    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["original_filename"] == "user_doc1.pdf"
    assert data[1]["original_filename"] == "user_doc2.pdf"
    # Ensure storage path is hidden
    assert "storage_path" not in data[0]

def test_get_document_success(mock_db_session, mock_auth, mock_user):
    """Test retrieving a specific document owned by the user succeeds."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="user_doc.pdf",
        stored_filename="stored.pdf",
        file_type="pdf",
        file_size=100,
        storage_path="uploads/stored.pdf",
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    response = client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id)
    assert data["original_filename"] == "user_doc.pdf"
    assert "storage_path" not in data

def test_get_document_not_found_or_not_owned(mock_db_session, mock_auth):
    """Test retrieving a nonexistent or another user's document returns 404."""
    # Mock query returning None (user does not own the document or it doesn't exist)
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/documents/{random_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

@patch("app.api.endpoints.documents.delete_document_vectors")
def test_delete_document_success(mock_delete_vectors, mock_db_session, mock_auth, mock_user):
    """Test deleting owned document cleans database record, deletes physical file, and deletes vectors."""
    doc_id = uuid.uuid4()
    stored_name = "todelete.pdf"
    storage_path = os.path.join(settings.UPLOAD_DIR, stored_name)
    
    # Pre-write file so we can assert deletion
    with open(storage_path, "wb") as f:
        f.write(b"delete me")
        
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="original.pdf",
        stored_filename=stored_name,
        file_type="pdf",
        file_size=9,
        storage_path=storage_path,
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    response = client.delete(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["detail"].lower()

    # Verify db delete and commit
    mock_db_session.delete.assert_called_once_with(doc)
    mock_db_session.commit.assert_called_once()

    # Verify physical file deletion
    assert not os.path.exists(storage_path)

    # Verify vector deletion integration
    mock_delete_vectors.assert_called_once_with(user_id=mock_user.id, document_id=doc_id)


def test_delete_document_not_found_or_not_owned(mock_db_session, mock_auth):
    """Test that deleting another user's or nonexistent document returns 404."""
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    random_id = uuid.uuid4()
    response = client.delete(f"/api/v1/documents/{random_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    mock_db_session.delete.assert_not_called()

# -------------------------------------------------------------
# Document Processing Endpoint Tests
# -------------------------------------------------------------

@patch("app.api.endpoints.documents.process_document")
def test_process_document_success(mock_process, mock_db_session, mock_auth, mock_user):
    """Test successful document processing updates database and returns response."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="sample.txt",
        stored_filename="stored_sample.txt",
        file_type="txt",
        file_size=500,
        storage_path="uploads/stored_sample.txt",
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    # Mock DB query
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    # Mock processor service return value
    from app.services.document_processor import DocumentProcessingResult, ChunkResult
    mock_proc_res = DocumentProcessingResult(
        document_id=doc_id,
        extracted_text_length=1200,
        chunk_count=3,
        chunks=[ChunkResult(content="c", metadata={}) for _ in range(3)],
        status="ready"
    )
    mock_process.return_value = mock_proc_res

    response = client.post(f"/api/v1/documents/{doc_id}/process")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "ready"
    assert data["extracted_text_length"] == 1200
    assert data["chunk_count"] == 3

    # Verify that the DB fields are updated
    assert doc.status == DocumentStatus.READY
    assert doc.chunk_count == 3
    assert "extracted_text" not in data
    assert "storage_path" not in data

    # Verify db commits: once for status to PROCESSING, once for READY
    assert mock_db_session.commit.call_count == 2

@patch("app.api.endpoints.documents.process_document")
def test_process_document_failure_updates_status(mock_process, mock_db_session, mock_auth, mock_user):
    """Test that document processing failure updates DB status to FAILED and throws exception."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="sample.txt",
        stored_filename="stored_sample.txt",
        file_type="txt",
        file_size=500,
        storage_path="uploads/stored_sample.txt",
        status=DocumentStatus.UPLOADED,
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    # Mock processor to raise DocumentProcessingError
    from app.services.document_processor import EmptyExtractedContentError
    mock_process.side_effect = EmptyExtractedContentError("No extractable text found", status_code=400)

    response = client.post(f"/api/v1/documents/{doc_id}/process")
    assert response.status_code == 400
    assert "no extractable text" in response.json()["detail"].lower()
    
    # Assert DB status is FAILED
    assert doc.status == DocumentStatus.FAILED

def test_process_document_unauthorized(mock_db_session):
    """Test authentication required for processing document."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/process")
    assert response.status_code == 401

def test_process_document_nonexistent_returns_404(mock_db_session, mock_auth):
    """Test processing nonexistent document returns 404."""
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/process")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

# -------------------------------------------------------------
# Document Indexing Endpoint Tests
# -------------------------------------------------------------

@patch("app.api.endpoints.documents.process_document")
@patch("app.api.endpoints.documents.embed_chunks")
@patch("app.api.endpoints.documents.ingest_document_chunks")
def test_index_document_success(mock_ingest, mock_embed, mock_process, mock_db_session, mock_auth, mock_user):
    """Test successful document indexing transitions status and returns response."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="sample.pdf",
        stored_filename="stored_sample.pdf",
        file_type="pdf",
        file_size=1024,
        storage_path="uploads/stored_sample.pdf",
        status=DocumentStatus.UPLOADED,
        index_status="not_indexed",
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    # Mock document processing result
    from app.services.document_processor import DocumentProcessingResult, ChunkResult
    mock_proc_res = DocumentProcessingResult(
        document_id=doc_id,
        extracted_text_length=1500,
        chunk_count=2,
        chunks=[
            ChunkResult(content="Chunk 1", metadata={"source_filename": "sample.pdf", "file_type": "pdf"}),
            ChunkResult(content="Chunk 2", metadata={"source_filename": "sample.pdf", "file_type": "pdf"})
        ],
        status="ready"
    )
    mock_process.return_value = mock_proc_res

    # Mock embeddings return
    mock_embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

    response = client.post(f"/api/v1/documents/{doc_id}/index")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["index_status"] == "indexed"
    assert data["chunk_count"] == 2
    assert data["embedding_model"] == settings.EMBEDDING_MODEL

    # Verify that the DB fields are updated
    assert doc.index_status == "indexed"
    assert doc.chunk_count == 2
    assert "embeddings" not in data
    assert "chunks" not in data
    assert "storage_path" not in data

    # Verify integrations called
    mock_process.assert_called_once_with(
        document_id=doc_id,
        file_path="uploads/stored_sample.pdf",
        original_filename="sample.pdf"
    )
    mock_embed.assert_called_once_with(["Chunk 1", "Chunk 2"])
    mock_ingest.assert_called_once_with(
        user_id=mock_user.id,
        document_id=doc_id,
        chunks=mock_proc_res.chunks,
        embeddings=[[0.1, 0.2], [0.3, 0.4]]
    )

def test_index_document_unauthorized(mock_db_session):
    """Test authentication required for indexing."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/index")
    assert response.status_code == 401

def test_index_document_nonexistent_returns_404(mock_db_session, mock_auth):
    """Test indexing nonexistent document returns 404."""
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/index")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_index_document_indexing_state_rejected(mock_db_session, mock_auth, mock_user):
    """Test that indexing is rejected if document is currently indexing."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        original_filename="sample.pdf",
        stored_filename="stored_sample.pdf",
        file_type="pdf",
        file_size=1024,
        storage_path="uploads/stored_sample.pdf",
        status=DocumentStatus.UPLOADED,
        index_status="indexing",
        chunk_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db_session.execute.return_value = mock_result

    response = client.post(f"/api/v1/documents/{doc_id}/index")
    assert response.status_code == 400
    assert "currently being indexed" in response.json()["detail"].lower()


