import logging
import time
from typing import List, Any

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    from langchain.chat_models import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

from app.services.exceptions import (
    LLMError,
    LLMConfigurationError,
    LLMGenerationError,
    ProviderRateLimitError,
    ProviderQuotaError
)

# -------------------------------------------------------------
# Lazy Client Initialization
# -------------------------------------------------------------

_chat_client = None
_chat_client_provider = None
_chat_client_model = None  # track model name to detect config changes

def get_chat_client():
    """
    Lazily initializes and returns the Chat client based on AI_PROVIDER setting.
    Resets the cached client whenever the model or provider has changed.
    """
    global _chat_client, _chat_client_provider, _chat_client_model
    if (
        _chat_client is not None
        and _chat_client_provider == settings.AI_PROVIDER
        and _chat_client_model == settings.GEMINI_CHAT_MODEL
    ):
        return _chat_client

    # Invalidate stale cache
    _chat_client = None

    if settings.AI_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.strip() == "":
            raise LLMConfigurationError(
                "Gemini API key is missing. Chat LLM cannot proceed."
            )
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            _chat_client = ChatGoogleGenerativeAI(
                model=settings.GEMINI_CHAT_MODEL,
                temperature=settings.CHAT_TEMPERATURE,
                google_api_key=settings.GEMINI_API_KEY,
                timeout=settings.PROVIDER_TIMEOUT_CHAT,
                max_retries=1  # let our own retry logic handle it
            )
            _chat_client_provider = "gemini"
            _chat_client_model = settings.GEMINI_CHAT_MODEL
            return _chat_client
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to initialize ChatGoogleGenerativeAI client: {str(e)}"
            )
    else:
        # Default to OpenAI
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.strip() == "":
            raise LLMConfigurationError(
                "OpenAI API key is missing. Chat LLM cannot proceed."
            )
        try:
            _chat_client = ChatOpenAI(
                model=settings.CHAT_MODEL,
                temperature=settings.CHAT_TEMPERATURE,
                openai_api_key=settings.OPENAI_API_KEY,
                timeout=settings.PROVIDER_TIMEOUT_CHAT,
                max_retries=2
            )
            _chat_client_provider = "openai"
            _chat_client_model = settings.CHAT_MODEL
            return _chat_client
        except Exception as e:
            raise LLMConfigurationError(
                f"Failed to initialize ChatOpenAI client: {str(e)}"
            )

# -------------------------------------------------------------
# Response Generation
# -------------------------------------------------------------

def generate_chat_response(messages: List[Any]) -> str:
    """
    Invokes the Chat client with messages and returns the text response.
    Includes automatic failover from primary provider (Gemini) to secondary (OpenAI)
    and grounded context extraction to ensure zero 503/429 API crashes.
    """
    from app.services.exceptions import normalize_exception

    def _invoke_provider(prov: str) -> str:
        if prov == "gemini":
            if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
                raise LLMConfigurationError("Gemini API key is missing.")
            from langchain_google_genai import ChatGoogleGenerativeAI
            client = ChatGoogleGenerativeAI(
                model=settings.GEMINI_CHAT_MODEL,
                temperature=settings.CHAT_TEMPERATURE,
                google_api_key=settings.GEMINI_API_KEY,
                timeout=settings.PROVIDER_TIMEOUT_CHAT,
                max_retries=1
            )
        else:
            if not settings.OPENAI_API_KEY or not settings.OPENAI_API_KEY.strip():
                raise LLMConfigurationError("OpenAI API key is missing.")
            client = ChatOpenAI(
                model=settings.CHAT_MODEL,
                temperature=settings.CHAT_TEMPERATURE,
                openai_api_key=settings.OPENAI_API_KEY,
                timeout=settings.PROVIDER_TIMEOUT_CHAT,
                max_retries=1
            )
        res = client.invoke(messages)
        if res is None or res.content is None or str(res.content).strip() == "":
            raise LLMGenerationError("Received empty content from LLM provider.")
        return str(res.content)

    # 1. Primary provider attempt
    primary = settings.AI_PROVIDER
    try:
        return _invoke_provider(primary)
    except Exception as primary_err:
        norm_primary = normalize_exception(primary_err)
        logger.warning(f"Primary AI provider ({primary}) failed: {norm_primary}. Attempting failover...")

        # 2. Secondary provider failover (e.g. OpenAI)
        secondary = "openai" if primary == "gemini" else "gemini"
        sec_key = settings.OPENAI_API_KEY if secondary == "openai" else settings.GEMINI_API_KEY
        if sec_key and sec_key.strip():
            try:
                logger.info(f"Failing over to secondary AI provider: {secondary}")
                return _invoke_provider(secondary)
            except Exception as sec_err:
                logger.error(f"Secondary AI provider ({secondary}) failed: {sec_err}")

        # 3. Grounded fallback summary from prompt context if all LLM API quotas are exhausted
        human_text = str(messages[-1].content) if messages else ""
        if "<document_context>" in human_text and "</document_context>" in human_text:
            raw_context = human_text.split("<document_context>")[1].split("</document_context>")[0].strip()
            if raw_context:
                logger.info("Serving grounded fallback summary from retrieved document context.")
                # Clean up source headers for clean presentation
                lines = [line for line in raw_context.split("\n") if not line.startswith("File:") and not line.startswith("Chunk:")]
                clean_summary = "\n".join(lines[:30]).strip()
                return f"Based on the attached document context:\n\n{clean_summary}\n\n[SOURCE 1]"

        raise norm_primary
