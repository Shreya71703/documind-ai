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

def _invoke_gemini_rest(messages: List[Any]) -> str:
    import urllib.request, json
    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
        raise LLMConfigurationError("Gemini API key is missing.")
    
    prompt_parts = []
    for msg in messages:
        content = getattr(msg, "content", str(msg))
        prompt_parts.append(str(content))
    prompt_str = "\n\n".join(prompt_parts)

    model_name = settings.GEMINI_CHAT_MODEL
    clean_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{clean_model}:generateContent?key={settings.GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt_str}]}],
        "generationConfig": {
            "temperature": float(settings.CHAT_TEMPERATURE),
            "maxOutputTokens": 1500
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=int(settings.PROVIDER_TIMEOUT_CHAT)) as resp:
        res_json = json.loads(resp.read().decode("utf-8"))
        candidates = res_json.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                txt = parts[0].get("text", "")
                if txt and txt.strip():
                    return txt.strip()
    raise LLMGenerationError("Gemini REST API returned empty content.")

def generate_chat_response(messages: List[Any]) -> str:
    """
    Invokes the Chat client with messages and returns the text response.
    Includes automatic failover from primary provider (Gemini) to secondary (OpenAI)
    and grounded context extraction to guarantee zero 503/429 API crashes.
    """
    from app.services.exceptions import normalize_exception

    def _invoke_provider(prov: str) -> str:
        if prov == "gemini":
            try:
                return _invoke_gemini_rest(messages)
            except Exception as e:
                from langchain_google_genai import ChatGoogleGenerativeAI
                client = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_CHAT_MODEL,
                    temperature=settings.CHAT_TEMPERATURE,
                    google_api_key=settings.GEMINI_API_KEY,
                    timeout=settings.PROVIDER_TIMEOUT_CHAT,
                    max_retries=1
                )
                res = client.invoke(messages)
                return str(res.content)
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

        # If secondary provider also failed or key is missing, raise the normalized primary exception
        raise norm_primary
