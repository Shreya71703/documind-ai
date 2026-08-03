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
    Invokes the ChatOpenAI or ChatGoogleGenerativeAI model with messages and returns the text response.
    Converts provider exceptions into controlled normalized exceptions.
    Retries once after a short wait on rate-limit (429) errors.
    """
    from app.services.exceptions import normalize_exception

    def _invoke_once() -> str:
        client = get_chat_client()
        try:
            response = client.invoke(messages)
        except Exception as e:
            raise normalize_exception(e)

        if response is None or response.content is None or str(response.content).strip() == "":
            from app.services.exceptions import ProviderResponseError
            raise ProviderResponseError("Received empty or malformed content response from chat provider.")

        return str(response.content)

    try:
        return _invoke_once()
    except ProviderRateLimitError:
        # Wait 5 seconds and retry once on rate-limit
        logger.warning("Rate limit hit — retrying after 5 seconds")
        time.sleep(5)
        return _invoke_once()
    except ProviderQuotaError:
        # Quota is exhausted — no point retrying
        raise
    except Exception as e:
        logger.error("Failed to generate response from Chat LLM.")
        raise normalize_exception(e)
