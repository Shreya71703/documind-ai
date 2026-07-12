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
from app.schemas.document import RetrievalResponse, RetrievalRequest, RetrievedSource
from app.services.retrieval import (
    retrieve_context,
    RetrievalError,
    DocumentNotIndexedError,
    InvalidRetrievalQueryError
)

client = TestClient(app)

# -------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------

@pytest.fixture
def mock_user():
    """Mock authenticated user fixture."""
    return User(
        id=uuid.uuid4(),
        email="retrievaluser@example.com",
        full_name="Retrieval User",
        is_active=True,
        is_admin=False
    )

@pytest.fixture
def mock_db_session():
    """Mock DB session and override get_db dependency."""
    session = AsyncMock()
    
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
# Service Unit Tests
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_or_whitespace_query_rejected():
    """Verify that empty or whitespace queries are rejected directly."""
    db = AsyncMock()
    user_id = uuid.uuid4()
    
    with pytest.raises(InvalidRetrievalQueryError):
        await retrieve_context(db, "", user_id)
        
    with pytest.raises(InvalidRetrievalQueryError):
        await retrieve_context(db, "   ", user_id)

@pytest.mark.asyncio
@patch("app.services.retrieval.embed_query")
@patch("app.services.retrieval.query_similarity")
async def test_no_retrieval_results_handled(mock_similarity, mock_embed, mock_db_session):
    """Verify empty retrieval result structure when ChromaDB returns no matches."""
    user_id = uuid.uuid4()
    mock_embed.return_value = [0.1, 0.2]
    mock_similarity.return_value = [] # No matches

    res = await retrieve_context(mock_db_session, "some query", user_id)
    assert isinstance(res, RetrievalResponse)
    assert res.query == "some query"
    assert res.retrieved_count == 0
    assert res.included_count == 0
    assert res.context == ""
    assert len(res.sources) == 0
    assert res.context_truncated is False

@pytest.mark.asyncio
@patch("app.services.retrieval.embed_query")
@patch("app.services.retrieval.query_similarity")
async def test_normalization_and_deduplication(mock_similarity, mock_embed, mock_db_session):
    """Verify normalization, user ID checks, and duplicate vector ID/content removal."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    mock_embed.return_value = [0.1]
    
    # 4 chunks returned by ChromaDB:
    # 1. Valid PDF chunk
    # 2. Duplicate content chunk (should be deduplicated)
    # 3. Security risk: mismatch user_id (should be excluded)
    # 4. Duplicate vector ID chunk (should be deduplicated)
    mock_similarity.return_value = [
        {
            "id": "vec1",
            "content": "Unique Content 1",
            "distance": 0.1,
            "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 0, "source_filename": "f.pdf", "file_type": "pdf", "page_number": 1}
        },
        {
            "id": "vec2",
            "content": "Unique Content 1", # Duplicate content
            "distance": 0.2,
            "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 1, "source_filename": "f.pdf", "file_type": "pdf", "page_number": 1}
        },
        {
            "id": "vec3",
            "content": "Unrelated User Content", # Ownership mismatch
            "distance": 0.3,
            "metadata": {"user_id": str(uuid.uuid4()), "document_id": str(doc_id), "chunk_index": 2, "source_filename": "f.pdf", "file_type": "pdf"}
        },
        {
            "id": "vec1", # Duplicate vector ID
            "content": "Different Text",
            "distance": 0.4,
            "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 0, "source_filename": "f.pdf", "file_type": "pdf", "page_number": 1}
        }
    ]

    res = await retrieve_context(mock_db_session, "query", user_id)
    # Only 1 unique chunk should survive
    assert res.retrieved_count == 1
    assert res.included_count == 1
    assert "Unique Content 1" in res.context
    assert res.sources[0].citation_id == "SOURCE 1"
    assert res.sources[0].page_number == 1
    assert res.sources[0].distance == 0.1

@pytest.mark.asyncio
@patch("app.services.retrieval.embed_query")
@patch("app.services.retrieval.query_similarity")
async def test_non_pdf_source_does_not_fabricate_page(mock_similarity, mock_embed, mock_db_session):
    """Verify non-PDF sources do not include page fields."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    mock_embed.return_value = [0.1]
    
    mock_similarity.return_value = [
        {
            "id": "vec1",
            "content": "TXT chunk content",
            "distance": 0.1,
            "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 0, "source_filename": "f.txt", "file_type": "txt"}
        }
    ]

    res = await retrieve_context(mock_db_session, "query", user_id)
    assert "Page:" not in res.context
    assert res.sources[0].page_number is None

@pytest.mark.asyncio
@patch("app.services.retrieval.embed_query")
@patch("app.services.retrieval.query_similarity")
async def test_context_respects_max_chars_limit(mock_similarity, mock_embed, mock_db_session):
    """Verify that chunks are included up to RAG_MAX_CONTEXT_CHARS and flag is set."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    mock_embed.return_value = [0.1]
    
    # Temporarily set max context chars to very low value
    old_max = settings.RAG_MAX_CONTEXT_CHARS
    settings.RAG_MAX_CONTEXT_CHARS = 100
    
    try:
        mock_similarity.return_value = [
            {
                "id": "vec1",
                "content": "Short first chunk", # Fits within 100 characters with header
                "distance": 0.1,
                "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 0, "source_filename": "f.txt", "file_type": "txt"}
            },
            {
                "id": "vec2",
                "content": "This second chunk will exceed the RAG_MAX_CONTEXT_CHARS limit",
                "distance": 0.15,
                "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 1, "source_filename": "f.txt", "file_type": "txt"}
            }
        ]

        res = await retrieve_context(mock_db_session, "query", user_id)
        assert res.included_count == 1
        assert "Short first chunk" in res.context
        assert "second chunk" not in res.context
        assert res.context_truncated is True
    finally:
        settings.RAG_MAX_CONTEXT_CHARS = old_max

@pytest.mark.asyncio
@patch("app.services.retrieval.embed_query")
@patch("app.services.retrieval.query_similarity")
async def test_chunk_aware_truncation_first_chunk(mock_similarity, mock_embed, mock_db_session):
    """Verify first chunk is safely truncated if it alone exceeds character budget."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    mock_embed.return_value = [0.1]
    
    old_max = settings.RAG_MAX_CONTEXT_CHARS
    settings.RAG_MAX_CONTEXT_CHARS = 50 # Tiny budget
    
    try:
        mock_similarity.return_value = [
            {
                "id": "vec1",
                "content": "This chunk is extremely long and will exceed the tiny limit by itself",
                "distance": 0.1,
                "metadata": {"user_id": str(user_id), "document_id": str(doc_id), "chunk_index": 0, "source_filename": "f.txt", "file_type": "txt"}
            }
        ]

        res = await retrieve_context(mock_db_session, "query", user_id)
        assert res.included_count == 1
        assert len(res.context) <= 50
        assert res.context_truncated is True
    finally:
        settings.RAG_MAX_CONTEXT_CHARS = old_max

@pytest.mark.asyncio
async def test_indexed_validation_for_selected_documents(mock_db_session):
    """Verify document validation rejects nonexistent or unindexed files."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    # 1. Nonexistent/other user's document
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db_session.execute.return_value = mock_result

    with pytest.raises(DocumentNotIndexedError) as exc:
        await retrieve_context(mock_db_session, "query", user_id, document_ids=[doc_id])
    assert exc.value.status_code == 404

    # 2. Owned but not indexed document (e.g. status is indexing/failed/not_indexed)
    doc = Document(
        id=doc_id,
        user_id=user_id,
        original_filename="sample.pdf",
        stored_filename="stored.pdf",
        file_type="pdf",
        file_size=10,
        storage_path="uploads/stored.pdf",
        status=DocumentStatus.UPLOADED,
        index_status="failed",
        chunk_count=0
    )
    mock_result.scalars().first.return_value = doc
    
    with pytest.raises(DocumentNotIndexedError) as exc:
        await retrieve_context(mock_db_session, "query", user_id, document_ids=[doc_id])
    assert exc.value.status_code == 400
    assert "not fully indexed" in str(exc.value)

# -------------------------------------------------------------
# Endpoint Integration Tests
# -------------------------------------------------------------

def test_search_unauthorized(mock_db_session):
    """Verify search endpoint requires authentication."""
    response = client.post("/api/v1/retrieval/search", json={"query": "hello"})
    assert response.status_code == 401

def test_search_validation_schema(mock_db_session, mock_auth):
    """Verify request schema validation rules (whitespace query, top_k limits)."""
    # 1. Whitespace query
    response = client.post("/api/v1/retrieval/search", json={"query": "   "})
    assert response.status_code == 422

    # 2. top_k below min
    response = client.post("/api/v1/retrieval/search", json={"query": "test", "top_k": 0})
    assert response.status_code == 422

    # 3. top_k above max
    response = client.post("/api/v1/retrieval/search", json={"query": "test", "top_k": settings.RAG_MAX_TOP_K + 1})
    assert response.status_code == 422

    # 4. Duplicate document IDs
    dup_id = str(uuid.uuid4())
    response = client.post("/api/v1/retrieval/search", json={"query": "test", "document_ids": [dup_id, dup_id]})
    assert response.status_code == 422

@patch("app.api.endpoints.retrieval.retrieve_context")
def test_search_endpoint_success(mock_retrieve, mock_db_session, mock_auth, mock_user):
    """Verify endpoint successfully returns structured RetrievalResponse without leaking sensitive fields."""
    doc_id = uuid.uuid4()
    mock_response = RetrievalResponse(
        query="search text",
        retrieved_count=1,
        included_count=1,
        context="[SOURCE 1]\nFile: f.txt\nChunk: 0\n\nsample content",
        sources=[
            RetrievedSource(
                citation_id="SOURCE 1",
                document_id=doc_id,
                source_filename="f.txt",
                file_type="txt",
                chunk_index=0,
                distance=0.123
            )
        ],
        context_truncated=False
    )
    mock_retrieve.return_value = mock_response

    response = client.post("/api/v1/retrieval/search", json={"query": "search text"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["query"] == "search text"
    assert data["retrieved_count"] == 1
    assert "sample content" in data["context"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["citation_id"] == "SOURCE 1"
    
    # Security checks: ensure sensitive info is not leaked in the JSON response
    assert "storage_path" not in data["sources"][0]
    assert "user_id" not in data["sources"][0]
    assert "embeddings" not in data
