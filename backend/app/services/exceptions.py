class EmbeddingError(Exception):
    """Base exception for embedding service."""
    pass

class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the embedding client is misconfigured (e.g. missing API key)."""
    pass

class EmbeddingGenerationError(EmbeddingError):
    """Raised when embedding generation fails."""
    pass

class LLMError(Exception):
    """Base exception for LLM service."""
    pass

class LLMConfigurationError(LLMError):
    """Raised when the LLM client is misconfigured (e.g. missing API key)."""
    pass

class LLMGenerationError(LLMError):
    """Raised when LLM response generation fails."""
    pass

class ProviderError(EmbeddingGenerationError, LLMGenerationError):
    """Base exception for all external AI provider errors."""
    def __init__(self, message: str, original_exception: Exception = None):
        # Initialize both parent exception classes
        super().__init__(message)
        self.original_exception = original_exception

class ProviderTimeoutError(ProviderError):
    """Raised when request to provider times out."""
    pass

class ProviderRateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""
    pass

class ProviderQuotaError(ProviderError):
    """Raised when provider quota/billing is exhausted."""
    pass

class ProviderAuthenticationError(ProviderError):
    """Raised when provider authentication fails (e.g. invalid API key)."""
    pass

class ProviderUnavailableError(ProviderError):
    """Raised when provider is temporarily offline or unavailable (e.g. HTTP 503)."""
    pass

class ProviderResponseError(ProviderError):
    """Raised when provider returns a malformed, empty, or unexpected response."""
    pass

def normalize_exception(e: Exception) -> Exception:
    import openai
    
    # 1. Check if it's an OpenAI error
    if isinstance(e, openai.OpenAIError):
        msg = str(e).lower()
        if isinstance(e, openai.APITimeoutError):
            return ProviderTimeoutError("Provider request timed out.", original_exception=e)
        if isinstance(e, openai.AuthenticationError):
            return ProviderAuthenticationError("Provider authentication failed.", original_exception=e)
        if isinstance(e, openai.RateLimitError):
            if "quota" in msg or "billing" in msg or "credit" in msg or "insufficient_quota" in msg:
                return ProviderQuotaError("Provider account quota/billing exhausted.", original_exception=e)
            return ProviderRateLimitError("Provider rate limit exceeded.", original_exception=e)
        if isinstance(e, (openai.InternalServerError, openai.APIConnectionError)):
            return ProviderUnavailableError("Provider is temporarily offline or unavailable.", original_exception=e)
        return ProviderResponseError(f"Unexpected provider response error: {str(e)}", original_exception=e)

    # 2. Check if it's a Google GenAI error
    try:
        from google.genai.errors import APIError
        if isinstance(e, APIError):
            msg = str(e).lower()
            code = getattr(e, "code", getattr(e, "status_code", None))
            if code is None:
                import re
                match = re.search(r'\b(401|403|429|503|504)\b', msg)
                if match:
                    code = int(match.group(1))
            
            if code in (401, 403) or "auth" in msg or "api key" in msg or "invalid" in msg:
                return ProviderAuthenticationError("Provider authentication failed.", original_exception=e)
            if code == 429 or "quota" in msg or "limit" in msg or "rate" in msg:
                if "quota" in msg or "exhausted" in msg or "insufficient" in msg:
                    return ProviderQuotaError("Provider account quota/billing exhausted.", original_exception=e)
                return ProviderRateLimitError("Provider rate limit exceeded.", original_exception=e)
            if code == 504 or "timeout" in msg or "deadline" in msg:
                return ProviderTimeoutError("Provider request timed out.", original_exception=e)
            if code in (500, 502, 503) or "unavailable" in msg or "server error" in msg:
                return ProviderUnavailableError("Provider is temporarily offline or unavailable.", original_exception=e)
            return ProviderResponseError(f"Unexpected provider response error: {str(e)}", original_exception=e)
    except ImportError:
        pass

    # 3. Check for general asyncio/httpx timeouts
    import asyncio
    import httpx
    if isinstance(e, (asyncio.TimeoutError, httpx.TimeoutException)):
        return ProviderTimeoutError("Provider request timed out.", original_exception=e)

    # Return as general response error
    return ProviderResponseError(f"Unexpected error: {str(e)}", original_exception=e)
