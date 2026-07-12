import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.core.config import settings
from app.services.vector_store import (
    get_active_collection_name,
    get_collection,
    ingest_document_chunks,
    delete_document_vectors,
    count_document_vectors,
    get_chroma_client
)

class MockChunk:
    def __init__(self, content, metadata):
        self.content = content
        self.metadata = metadata

def test_collection_naming_isolation():
    """Verify Gemini and OpenAI resolve isolated collections."""
    # Reset cached collection name variable
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="openai", EMBEDDING_MODEL="text-embedding-3-small"):
            # Mock get_embeddings_client query to return 1536 dim list
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 1536
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                openai_name = get_active_collection_name()
                assert "openai" in openai_name
                assert "1536" in openai_name
                
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_EMBEDDING_MODEL="models/gemini-embedding-2"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 3072
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                gemini_name = get_active_collection_name()
                assert "gemini" in gemini_name
                assert "3072" in gemini_name

def test_provider_switching_does_not_delete():
    """Verify that switching providers isolates and does not delete another provider's collection."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunks = [MockChunk("test data", {"source_filename": "test.txt", "file_type": "txt"})]
    
    # 1. Ingest under OpenAI
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="openai", EMBEDDING_MODEL="text-embedding-3-small"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 1536
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                # Ingest 1536 dim vector
                ingest_document_chunks(user_id, doc_id, chunks, [[0.1] * 1536])
                # Verify indexed in OpenAI collection
                assert count_document_vectors(user_id, doc_id) == 1

    # 2. Switch to Gemini, OpenAI collection should be untouched
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_EMBEDDING_MODEL="models/gemini-embedding-2"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 3072
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                # Count under Gemini (should be 0 since it is a different collection name)
                assert count_document_vectors(user_id, doc_id) == 0
                
                # Ingest under Gemini
                ingest_document_chunks(user_id, doc_id, chunks, [[0.2] * 3072])
                assert count_document_vectors(user_id, doc_id) == 1

    # 3. Switch back to OpenAI and verify original vector remains intact (non-destructive)
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="openai", EMBEDDING_MODEL="text-embedding-3-small"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 1536
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                # Vector count is still 1 (not deleted)
                assert count_document_vectors(user_id, doc_id) == 1

def test_deletion_is_isolated():
    """Verify document vector deletion only affects active collection."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunks = [MockChunk("test data", {"source_filename": "test.txt", "file_type": "txt"})]
    
    # 1. Ingest under both
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="openai", EMBEDDING_MODEL="text-embedding-3-small"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 1536
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                ingest_document_chunks(user_id, doc_id, chunks, [[0.1] * 1536])
                
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_EMBEDDING_MODEL="models/gemini-embedding-2"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 3072
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                ingest_document_chunks(user_id, doc_id, chunks, [[0.2] * 3072])

    # 2. Delete under Gemini
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_EMBEDDING_MODEL="models/gemini-embedding-2"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 3072
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                delete_document_vectors(user_id, doc_id)
                assert count_document_vectors(user_id, doc_id) == 0

    # 3. Check OpenAI remains intact
    with patch("app.services.vector_store._active_collection_name", None):
        with patch.multiple(settings, AI_PROVIDER="openai", EMBEDDING_MODEL="text-embedding-3-small"):
            mock_emb = MagicMock()
            mock_emb.embed_query.return_value = [0.0] * 1536
            with patch("app.services.embeddings.get_embeddings_client", return_value=mock_emb):
                assert count_document_vectors(user_id, doc_id) == 1
                # Clean up OpenAI too
                delete_document_vectors(user_id, doc_id)
