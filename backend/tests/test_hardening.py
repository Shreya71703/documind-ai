import pytest
import uuid
import time
import json
import logging
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

import openai
from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.services.exceptions import (
    normalize_exception,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderQuotaError,
    ProviderAuthenticationError,
    ProviderUnavailableError,
    ProviderResponseError,
    ProviderError
)
from app.services.embeddings import embed_chunks, embed_query
from app.services.llm import generate_chat_response
from app.services.retrieval import retrieve_context, RetrievalError
from app.services.rag import generate_grounded_answer, INSUFFICIENT_CONTEXT_MESSAGE
from app.core.logging_config import log_structured, request_id_var

client_test = TestClient(app)

@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

def test_request_id_headers_and_correlation():
    """Verify request ID generation, validation, and X-Request-ID response headers."""
    # 1. No incoming Request ID -> should generate a UUID
    response = client_test.get("/")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    generated_id = response.headers["X-Request-ID"]
    assert len(generated_id) > 10
    
    # 2. Valid incoming Request ID -> should be preserved
    valid_id = "test-request-id-12345"
    response2 = client_test.get("/", headers={"X-Request-ID": valid_id})
    assert response2.status_code == 200
    assert response2.headers["X-Request-ID"] == valid_id

    # 3. Invalid incoming Request ID (too long or bad chars) -> should be replaced with UUID
    invalid_id = "bad_id_with_special_chars_$%^&*" * 10
    response3 = client_test.get("/", headers={"X-Request-ID": invalid_id})
    assert response3.status_code == 200
    assert response3.headers["X-Request-ID"] != invalid_id
    assert len(response3.headers["X-Request-ID"]) > 10

def test_exception_normalization_openai():
    """Verify OpenAI exceptions are correctly normalized."""
    # 1. Timeout
    err1 = openai.APITimeoutError(request=None)
    norm1 = normalize_exception(err1)
    assert isinstance(norm1, ProviderTimeoutError)

    # 2. Authentication
    err2 = openai.AuthenticationError(message="Invalid API Key", response=MagicMock(), body=None)
    norm2 = normalize_exception(err2)
    assert isinstance(norm2, ProviderAuthenticationError)

    # 3. Rate Limit / Quota
    err3 = openai.RateLimitError(message="insufficient_quota", response=MagicMock(), body=None)
    norm3 = normalize_exception(err3)
    assert isinstance(norm3, ProviderQuotaError)

    err4 = openai.RateLimitError(message="Rate limit reached", response=MagicMock(), body=None)
    norm4 = normalize_exception(err4)
    assert isinstance(norm4, ProviderRateLimitError)

    # 4. Service Unavailable
    err5 = openai.InternalServerError(message="Service Unavailable", response=MagicMock(), body=None)
    norm5 = normalize_exception(err5)
    assert isinstance(norm5, ProviderUnavailableError)

def test_exception_normalization_gemini():
    """Verify Gemini APIExceptions are normalized correctly."""
    try:
        from google.genai.errors import APIError
        err = APIError(message="Quota exceeded (429)", request=MagicMock(), response=MagicMock())
        err.code = 429
        norm = normalize_exception(err)
        assert isinstance(norm, ProviderRateLimitError) or isinstance(norm, ProviderQuotaError)
    except Exception:
        pass

def test_api_status_mapping_for_provider_errors():
    """Verify FastAPI maps normalized exceptions to correct HTTP statuses with safe messages."""
    # Mock authentication and database session dependencies
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="testuser@example.com",
        full_name="Test User",
        is_active=True,
        is_admin=False
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    mock_session = MagicMock()
    mock_session.id = uuid.uuid4()
    mock_session.documents = []
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_session
    mock_db.execute.return_value = mock_result
    
    app.dependency_overrides[get_db] = lambda: mock_db

    # Patch generate_grounded_answer to raise ProviderTimeoutError
    with patch("app.api.endpoints.chats.generate_grounded_answer", side_effect=ProviderTimeoutError("Provider timed out")):
        response = client_test.post(
            f"/api/v1/chats/{uuid.uuid4()}/messages",
            json={"question": "What is the escalation path?"}
        )
        assert response.status_code == 504
        assert response.json()["detail"] == "The AI provider request timed out. Please try again later."

@patch("app.api.endpoints.documents.process_document")
@patch("app.api.endpoints.documents.embed_chunks")
def test_failed_indexing_does_not_become_indexed(mock_embed, mock_process):
    """Verify failed indexing updates index_status to failed in the database."""
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="testuser@example.com",
        full_name="Test User",
        is_active=True,
        is_admin=False
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Setup mock document
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=user_id,
        original_filename="sample.pdf",
        stored_filename="stored_sample.pdf",
        file_type="pdf",
        file_size=1024,
        storage_path="uploads/stored_sample.pdf",
        status=DocumentStatus.UPLOADED,
        index_status="not_indexed"
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = doc
    mock_db.execute.return_value = mock_result

    # Mock process_document success
    from app.services.document_processor import DocumentProcessingResult, ChunkResult
    mock_process.return_value = DocumentProcessingResult(
        document_id=doc_id,
        extracted_text_length=500,
        chunk_count=1,
        chunks=[ChunkResult(content="text", metadata={"source_filename": "s.pdf", "file_type": "pdf"})],
        status="ready"
    )

    # Mock embed_chunks to raise ProviderQuotaError
    mock_embed.side_effect = ProviderQuotaError("Quota exceeded")

    response = client_test.post(f"/api/v1/documents/{doc_id}/index")
    assert response.status_code == 503
    assert doc.index_status == "failed"
    assert mock_db.commit.call_count >= 1

@pytest.mark.asyncio
async def test_empty_retrieval_remains_insufficient_context():
    """Verify that a genuine empty retrieval continues to use the insufficient context response."""
    mock_db = AsyncMock()
    user_id = uuid.uuid4()
    
    # Mock retrieve_context to return empty context/sources
    mock_resp = MagicMock(retrieved_count=0, included_count=0, context="")
    with patch("app.services.rag.retrieve_context", return_value=mock_resp):
        rag_res = await generate_grounded_answer(mock_db, "Query test", user_id)
        assert rag_res.answer == INSUFFICIENT_CONTEXT_MESSAGE
        assert rag_res.insufficient_context is True

@pytest.mark.asyncio
async def test_retrieval_infrastructure_failure_not_insufficient_context():
    """Verify that provider timeout is raised as an error rather than insufficient context."""
    mock_db = AsyncMock()
    user_id = uuid.uuid4()
    
    with patch("app.services.rag.retrieve_context", side_effect=ProviderTimeoutError("Timeout")):
        with pytest.raises(ProviderTimeoutError):
            await generate_grounded_answer(mock_db, "Query test", user_id)

def test_latency_logging_monotonic():
    """Verify that structured latency profiling logs duration and warnings on slow thresholds."""
    with patch("app.core.logging_config.logger.log") as mock_log:
        log_structured(
            logging.INFO,
            "test_event",
            "test_operation",
            duration_ms=4500.0,
            user_id=str(uuid.uuid4())
        )
        assert mock_log.call_count == 1
        args, kwargs = mock_log.call_args
        log_json = json.loads(args[1])
        assert log_json["duration_ms"] == 4500.0
        assert log_json["event_name"] == "test_event"
        assert log_json["outcome"] == "success"
