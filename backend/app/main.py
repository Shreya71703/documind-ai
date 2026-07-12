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
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
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

@app.exception_handler(ProviderRateLimitError)
async def provider_rate_limit_handler(request: Request, exc: ProviderRateLimitError):
    return JSONResponse(
        status_code=429,
        content={"detail": "AI provider rate limit exceeded. Please retry in a moment."}
    )

@app.exception_handler(ProviderQuotaError)
async def provider_quota_handler(request: Request, exc: ProviderQuotaError):
    return JSONResponse(
        status_code=503,
        content={"detail": "AI provider service is currently unavailable due to billing or quota limits."}
    )

@app.exception_handler(ProviderAuthenticationError)
async def provider_auth_handler(request: Request, exc: ProviderAuthenticationError):
    return JSONResponse(
        status_code=502,
        content={"detail": "AI provider authentication failed. Please contact administrator."}
    )

@app.exception_handler(ProviderUnavailableError)
async def provider_unavailable_handler(request: Request, exc: ProviderUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "AI provider service is temporarily offline or unavailable."}
    )

@app.exception_handler(ProviderResponseError)
async def provider_response_handler(request: Request, exc: ProviderResponseError):
    return JSONResponse(
        status_code=502,
        content={"detail": "Received an invalid or malformed response from the AI provider."}
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
def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time()
    }
