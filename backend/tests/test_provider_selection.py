import pytest
from unittest.mock import patch, MagicMock
from app.core.config import settings
from app.services.embeddings import get_embeddings_client, EmbeddingConfigurationError
from app.services.llm import get_chat_client, LLMConfigurationError

def test_provider_selection_openai():
    """Verify that settings default/openai initializes OpenAI clients."""
    with patch.multiple(settings, AI_PROVIDER="openai", OPENAI_API_KEY="dummy-openai-key"):
        with patch("app.services.embeddings._embeddings_client", None), \
             patch("app.services.embeddings._embeddings_client_provider", None), \
             patch("app.services.llm._chat_client", None), \
             patch("app.services.llm._chat_client_provider", None):
            
            emb_client = get_embeddings_client()
            chat_client = get_chat_client()
            
            assert emb_client.__class__.__name__ == "OpenAIEmbeddings"
            assert chat_client.__class__.__name__ == "ChatOpenAI"

def test_provider_selection_gemini():
    """Verify that gemini setting initializes Gemini clients."""
    with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_API_KEY="dummy-gemini-key"):
        with patch("app.services.embeddings._embeddings_client", None), \
             patch("app.services.embeddings._embeddings_client_provider", None), \
             patch("app.services.llm._chat_client", None), \
             patch("app.services.llm._chat_client_provider", None):
            
            emb_client = get_embeddings_client()
            chat_client = get_chat_client()
            
            assert emb_client.__class__.__name__ == "GoogleGenerativeAIEmbeddings"
            assert chat_client.__class__.__name__ == "ChatGoogleGenerativeAI"

def test_gemini_missing_api_key_raises_error():
    """Verify that missing GEMINI_API_KEY raises configuration errors for Gemini provider."""
    with patch.multiple(settings, AI_PROVIDER="gemini", GEMINI_API_KEY=""):
        with patch("app.services.embeddings._embeddings_client", None), \
             patch("app.services.embeddings._embeddings_client_provider", None), \
             patch("app.services.llm._chat_client", None), \
             patch("app.services.llm._chat_client_provider", None):
            
            with pytest.raises(EmbeddingConfigurationError) as exc_emb:
                get_embeddings_client()
            assert "Gemini API key is missing" in str(exc_emb.value)
            
            with pytest.raises(LLMConfigurationError) as exc_llm:
                get_chat_client()
            assert "Gemini API key is missing" in str(exc_llm.value)
