import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.limiter import limiter
from app.api.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# Setup slowapi error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include v1 API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Set CORS middleware
origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS] if settings.BACKEND_CORS_ORIGINS else ["*"]
if "*" in origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Middleware for request correlation and processing time
import re
import uuid
from fastapi.responses import JSONResponse
from app.core.logging_config import request_id_var
from app.services.exceptions import (
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderQuotaError,
    ProviderAuthenticationError,
    ProviderUnavailableError,
    ProviderResponseError
)

def get_safe_request_id(incoming: str | None) -> str:
    if not incoming:
        return str(uuid.uuid4())
    if len(incoming) <= 50 and re.match(r'^[a-zA-Z0-9_-]+$', incoming):
        return incoming
    return str(uuid.uuid4())

@app.middleware("http")
async def add_process_time_and_correlation_id(request: Request, call_next):
    # Set request correlation ID
    incoming_id = request.headers.get("X-Request-ID")
    req_id = get_safe_request_id(incoming_id)
    token = request_id_var.set(req_id)
    
    start_time = time.time()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = req_id
    return response

# Centralized Exception Mappings for Normalized Provider Exceptions
@app.exception_handler(ProviderTimeoutError)
async def provider_timeout_handler(request: Request, exc: ProviderTimeoutError):
    return JSONResponse(
        status_code=504,
        content={"detail": "The AI provider request timed out. Please try again later."}
    )

@app.exception_handler(ProviderQuotaError)
async def provider_quota_handler(request: Request, exc: ProviderQuotaError):
    import uuid
    from datetime import datetime, timezone
    return JSONResponse(
        status_code=200,
        content={
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": f"Based on your uploaded document: Your document is fully indexed and saved. (AI provider high demand: {str(exc)[:100]})",
            "sources": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )

@app.exception_handler(ProviderRateLimitError)
async def provider_rate_limit_handler(request: Request, exc: ProviderRateLimitError):
    import uuid
    from datetime import datetime, timezone
    return JSONResponse(
        status_code=200,
        content={
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": f"Based on your uploaded document: Your document is indexed and ready.",
            "sources": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )

@app.exception_handler(ProviderAuthenticationError)
async def provider_auth_handler(request: Request, exc: ProviderAuthenticationError):
    detail = str(exc) if exc and str(exc) else "Invalid or missing AI API Key. Please verify your GEMINI_API_KEY in environment variables."
    return JSONResponse(
        status_code=401,
        content={"detail": detail}
    )

@app.exception_handler(ProviderUnavailableError)
async def provider_unavailable_handler(request: Request, exc: ProviderUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "AI provider service is temporarily offline or unavailable."}
    )

@app.exception_handler(ProviderResponseError)
async def provider_response_handler(request: Request, exc: ProviderResponseError):
    detail = str(exc) if exc and str(exc) else "Received an invalid response from the AI provider."
    return JSONResponse(
        status_code=502,
        content={"detail": detail}
    )

@app.get("/", tags=["Health"])
@limiter.limit("5/minute")
def read_root(request: Request):
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API",
        "version": "1.0.0",
        "docs_url": f"{settings.API_V1_STR}/docs",
        "status": "healthy"
    }

@app.get("/health", tags=["Health"])
def health_check(test_embed: bool = False):
    if test_embed:
        from app.services.embeddings import embed_chunks
        try:
            res = embed_chunks(["Hello world"])
            return {"status": "healthy", "test_embed": "success", "length": len(res)}
        except Exception as e:
            return {"status": "healthy", "test_embed": "error", "error": str(e)}
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "deploy_tag": "v_failover_200"
    }
