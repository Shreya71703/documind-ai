import logging
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
    LLMGenerationError
)

# -------------------------------------------------------------
# Lazy Client Initialization
# -------------------------------------------------------------

_chat_client = None
_chat_client_provider = None

def get_chat_client():
    """
    Lazily initializes and returns the Chat client based on AI_PROVIDER setting.
    """
    global _chat_client, _chat_client_provider
    if _chat_client is not None and _chat_client_provider == settings.AI_PROVIDER:
        return _chat_client

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
                max_retries=2
            )
            _chat_client_provider = "gemini"
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
    """
    client = get_chat_client()

    try:
        response = client.invoke(messages)
    except Exception as e:
        logger.error("Failed to generate response from Chat LLM.")
        from app.services.exceptions import normalize_exception
        raise normalize_exception(e)

    if response is None or response.content is None or str(response.content).strip() == "":
        from app.services.exceptions import ProviderResponseError
        raise ProviderResponseError("Received empty or malformed content response from chat provider.")

    return str(response.content)
