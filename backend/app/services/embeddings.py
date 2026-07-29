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
    """Thin wrapper around GoogleGenerativeAIEmbeddings & google.genai with deterministic fallback."""

    def __init__(self, model: str, api_key: str):
        self._api_key = api_key
        self._model = model

    def _generate_fallback_vector(self, text: str, dim: int = 768) -> List[float]:
        import hashlib
        import math
        words = text.lower().split()
        if not words:
            return [1.0 / math.sqrt(dim)] * dim
        
        vec = [0.0] * dim
        for word in words:
            h_val = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
            idx = h_val % dim
            val = ((h_val >> 8) % 1000) / 500.0 - 1.0
            vec[idx] += val

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            return [x / norm for x in vec]
        return [1.0 / math.sqrt(dim)] * dim

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._api_key and self._api_key.strip():
            # 1. Try langchain_google_genai with candidate models
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            for m in ["models/embedding-001", "models/text-embedding-004", "text-embedding-004", "embedding-001"]:
                try:
                    lc_client = GoogleGenerativeAIEmbeddings(model=m, google_api_key=self._api_key)
                    res = lc_client.embed_documents(texts)
                    if res and len(res) == len(texts):
                        return res
                except Exception as e:
                    logger.warning(f"LangChain Gemini embedding with model '{m}' failed: {e}")

            # 2. Try google.genai client
            try:
                from google import genai
                client = genai.Client(api_key=self._api_key)
                for m in ["text-embedding-004", "embedding-001"]:
                    try:
                        results = []
                        for t in texts:
                            resp = client.models.embed_content(model=m, contents=t)
                            results.append(resp.embeddings[0].values)
                        if len(results) == len(texts):
                            return results
                    except Exception as e:
                        logger.warning(f"google.genai embedding with model '{m}' failed: {e}")
            except Exception:
                pass

        logger.warning("External AI embedding provider failed or unavailable. Utilizing deterministic fallback vector generator.")
        return [self._generate_fallback_vector(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        if self._api_key and self._api_key.strip():
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            for m in ["models/embedding-001", "models/text-embedding-004", "text-embedding-004", "embedding-001"]:
                try:
                    lc_client = GoogleGenerativeAIEmbeddings(model=m, google_api_key=self._api_key)
                    res = lc_client.embed_query(query)
                    if res and len(res) > 0:
                        return res
                except Exception as e:
                    logger.warning(f"LangChain Gemini query embedding with model '{m}' failed: {e}")

            try:
                from google import genai
                client = genai.Client(api_key=self._api_key)
                for m in ["text-embedding-004", "embedding-001"]:
                    try:
                        resp = client.models.embed_content(model=m, contents=query)
                        if resp and resp.embeddings:
                            return resp.embeddings[0].values
                    except Exception as e:
                        logger.warning(f"google.genai query embedding with model '{m}' failed: {e}")
            except Exception:
                pass

        logger.warning("External AI query embedding provider failed or unavailable. Utilizing deterministic fallback vector generator.")
        return self._generate_fallback_vector(query)







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
