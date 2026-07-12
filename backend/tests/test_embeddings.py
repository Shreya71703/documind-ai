import pytest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.embeddings import (
    get_embeddings_client,
    embed_chunks,
    embed_query,
    EmbeddingConfigurationError,
    EmbeddingGenerationError
)

@pytest.fixture(autouse=True, scope="module")
def setup_openai_provider():
    old_provider = settings.AI_PROVIDER
    settings.AI_PROVIDER = "openai"
    yield
    settings.AI_PROVIDER = old_provider

# -------------------------------------------------------------
# Unit Tests for Embeddings Service
# -------------------------------------------------------------

def test_missing_api_key_raises_configuration_error():
    """Verify missing API key produces controlled configuration error."""
    # Temporarily remove API key and clear lazy client cache
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = ""
    
    # We clear the internal lazy client cache by patching the global variable
    with patch("app.services.embeddings._embeddings_client", None):
        with pytest.raises(EmbeddingConfigurationError) as exc:
            get_embeddings_client()
        assert "API key is missing" in str(exc.value)
        
    settings.OPENAI_API_KEY = old_key

def test_lazy_initialization():
    """Verify that get_embeddings_client caches the initialized client and is lazy."""
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "dummy-key-for-test"
    
    with patch("app.services.embeddings._embeddings_client", None) as mock_cache:
        # First call initializes the client
        client1 = get_embeddings_client()
        assert client1 is not None
        
        # Second call returns cached client
        client2 = get_embeddings_client()
        assert client1 is client2
        
    settings.OPENAI_API_KEY = old_key

def test_embed_chunks_rejects_empty_chunks():
    """Verify that passing empty/whitespace chunks is rejected before calling provider."""
    # Put a dummy key so configuration passes
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "dummy-key"
    
    with pytest.raises(EmbeddingGenerationError) as exc:
        embed_chunks(["Chunk 1", "", "Chunk 3"])
    assert "empty chunk detected" in str(exc.value).lower()
    
    settings.OPENAI_API_KEY = old_key

@patch("app.services.embeddings.get_embeddings_client")
def test_embed_chunks_count_mismatch_raises_error(mock_get_client):
    """Verify that if provider returns wrong number of embeddings, it raises error."""
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "dummy-key"
    
    # Mock client.embed_documents to return mismatched list length
    mock_client = MagicMock()
    mock_client.embed_documents.return_value = [[0.1, 0.2]] # Returns 1 embedding for 2 texts
    mock_get_client.return_value = mock_client
    
    with pytest.raises(EmbeddingGenerationError) as exc:
        embed_chunks(["Text 1", "Text 2"])
    assert "count mismatch" in str(exc.value).lower()
    
    settings.OPENAI_API_KEY = old_key

@patch("app.services.embeddings.get_embeddings_client")
def test_embed_chunks_success(mock_get_client):
    """Verify successful batch chunk embedding returns ordered embeddings."""
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "dummy-key"
    
    mock_client = MagicMock()
    mock_client.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
    mock_get_client.return_value = mock_client
    
    res = embed_chunks(["Chunk 1", "Chunk 2"])
    assert len(res) == 2
    assert res[0] == [0.1, 0.2]
    assert res[1] == [0.3, 0.4]
    mock_client.embed_documents.assert_called_once_with(["Chunk 1", "Chunk 2"])
    
    settings.OPENAI_API_KEY = old_key

@patch("app.services.embeddings.get_embeddings_client")
def test_embed_query_success(mock_get_client):
    """Verify successful single query embedding."""
    old_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "dummy-key"
    
    mock_client = MagicMock()
    mock_client.embed_query.return_value = [0.9, 0.8]
    mock_get_client.return_value = mock_client
    
    res = embed_query("hello world")
    assert res == [0.9, 0.8]
    mock_client.embed_query.assert_called_once_with("hello world")
    
    settings.OPENAI_API_KEY = old_key
