import logging
from typing import List

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:
    from langchain.embeddings import OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Service Exceptions
from app.services.exceptions import (
    EmbeddingError,
    EmbeddingConfigurationError,
    EmbeddingGenerationError
)

# -------------------------------------------------------------
# Gemini Native Client (using google.genai SDK directly)
# -------------------------------------------------------------

class _GeminiEmbeddingsClient:
    """Thin wrapper around GoogleGenerativeAIEmbeddings with resilient multi-model fallback."""

    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise EmbeddingConfigurationError("Gemini API key is missing.")
        self._api_key = api_key
        self._model = model

    def _get_candidate_models(self) -> List[str]:
        candidates = ["models/embedding-001", "models/text-embedding-004", "text-embedding-004", "embedding-001"]
        if self._model:
            formatted = self._model if self._model.startswith("models/") else f"models/{self._model}"
            if formatted not in candidates:
                candidates.insert(0, formatted)
        return candidates

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        last_exc = None
        for m in self._get_candidate_models():
            try:
                client = GoogleGenerativeAIEmbeddings(model=m, google_api_key=self._api_key)
                return client.embed_documents(texts)
            except Exception as e:
                logger.warning(f"Embedding model '{m}' failed: {e}. Trying next candidate...")
                last_exc = e
        if last_exc:
            raise last_exc
        raise RuntimeError("All embedding model candidates failed.")

    def embed_query(self, query: str) -> List[float]:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        last_exc = None
        for m in self._get_candidate_models():
            try:
                client = GoogleGenerativeAIEmbeddings(model=m, google_api_key=self._api_key)
                return client.embed_query(query)
            except Exception as e:
                logger.warning(f"Query embedding model '{m}' failed: {e}. Trying next candidate...")
                last_exc = e
        if last_exc:
            raise last_exc
        raise RuntimeError("All query embedding model candidates failed.")





# -------------------------------------------------------------
# Lazy Client Initialization
# -------------------------------------------------------------

_embeddings_client = None
_embeddings_client_provider = None

def get_embeddings_client():
    """
    Lazily initializes and returns the embeddings client based on AI_PROVIDER setting.
    """
    global _embeddings_client, _embeddings_client_provider
    if _embeddings_client is not None and _embeddings_client_provider == settings.AI_PROVIDER:
        return _embeddings_client

    if settings.AI_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.strip() == "":
            raise EmbeddingConfigurationError(
                "Gemini API key is missing. Vector indexing cannot proceed."
            )
        try:
            _embeddings_client = _GeminiEmbeddingsClient(
                model=settings.GEMINI_EMBEDDING_MODEL,
                api_key=settings.GEMINI_API_KEY,
            )
            _embeddings_client_provider = "gemini"
            return _embeddings_client
        except EmbeddingConfigurationError:
            raise
        except Exception as e:
            raise EmbeddingConfigurationError(
                f"Failed to initialize Gemini embeddings client: {str(e)}"
            )
    else:
        # Default to OpenAI
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.strip() == "":
            raise EmbeddingConfigurationError(
                "OpenAI API key is missing. Vector indexing cannot proceed."
            )
        try:
            _embeddings_client = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                openai_api_key=settings.OPENAI_API_KEY,
                timeout=settings.PROVIDER_TIMEOUT_EMBEDDING,
                max_retries=2
            )
            _embeddings_client_provider = "openai"
            return _embeddings_client
        except Exception as e:
            raise EmbeddingConfigurationError(
                f"Failed to initialize OpenAIEmbeddings client: {str(e)}"
            )


# -------------------------------------------------------------
# Embedding Generation Functions
# -------------------------------------------------------------

def embed_chunks(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for a list of non-empty text chunks.
    Preserves input order.
    """
    if not texts:
        return []

    # Validate that no chunk is empty
    for idx, text in enumerate(texts):
        if not text or text.strip() == "":
            raise EmbeddingGenerationError(
                f"Empty chunk detected at index {idx}. Empty chunks cannot be embedded."
            )

    client = get_embeddings_client()

    try:
        # Generate embeddings (LangChain OpenAIEmbeddings handles batching internally)
        embeddings = client.embed_documents(texts)
    except Exception as e:
        logger.error("Failed to generate document chunk embeddings.")
        from app.services.exceptions import normalize_exception
        raise normalize_exception(e)

    if not embeddings:
        from app.services.exceptions import ProviderResponseError
        raise ProviderResponseError("Received empty response from embedding provider.")

    if len(embeddings) != len(texts):
        from app.services.exceptions import ProviderResponseError
        raise ProviderResponseError(
            f"Embedding count mismatch. Expected {len(texts)} embeddings, but received {len(embeddings)}."
        )

    # Check for malformed elements or dimension inconsistency
    expected_dim = None
    for idx, emb in enumerate(embeddings):
        if emb is None or not isinstance(emb, list) or len(emb) == 0:
            from app.services.exceptions import ProviderResponseError
            raise ProviderResponseError(f"Malformed or empty embedding vector received at index {idx}.")
        
        if expected_dim is None:
            expected_dim = len(emb)
        elif len(emb) != expected_dim:
            from app.services.exceptions import ProviderResponseError
            raise ProviderResponseError(
                f"Embedding dimension inconsistency detected at index {idx}. "
                f"Expected dimension {expected_dim}, but got {len(emb)}."
            )

    return embeddings

def embed_query(query: str) -> List[float]:
    """
    Generates an embedding for a search query.
    """
    if not query or query.strip() == "":
        raise EmbeddingGenerationError("Query string cannot be empty.")

    client = get_embeddings_client()

    try:
        emb = client.embed_query(query)
    except Exception as e:
        logger.error("Failed to generate query embedding.")
        from app.services.exceptions import normalize_exception
        raise normalize_exception(e)

    if emb is None or not isinstance(emb, list) or len(emb) == 0:
        from app.services.exceptions import ProviderResponseError
        raise ProviderResponseError("Received empty or malformed query embedding vector.")

    return emb
