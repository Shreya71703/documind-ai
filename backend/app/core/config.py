import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG Document Assistant"
    API_V1_STR: str = "/api/v1"
    
    # Database Configuration
    # Fallback to sqlite if database url is not provided (useful for quick local tests without docker)
    DATABASE_URL: str = "postgresql+asyncpg://rag_user:rag_password@localhost:5432/rag_db"
    
    # Vector Database Configuration
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_NAME: str = "rag_documents"
    CHROMA_PERSIST_DIRECTORY: str = "chroma_db"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Security and Auth Configuration
    JWT_SECRET: str = "super-secret-key-change-in-production-at-least-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # OpenAI Config
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Configurable AI Provider
    AI_PROVIDER: str = "openai"  # "openai" or "gemini"
    
    # Gemini Config
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-1.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    
    # Storage Configuration
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".txt", ".md"]
    
    # Chunking Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Retrieval Configuration
    RAG_TOP_K: int = 5
    RAG_MAX_TOP_K: int = 20
    RAG_MAX_CONTEXT_CHARS: int = 12000
    
    # RAG Chat Configuration
    CHAT_MODEL: str = "gpt-4o-mini"
    CHAT_TEMPERATURE: float = 0.0
    RAG_MAX_QUESTION_CHARS: int = 1000
    
    # Provider Timeouts (seconds)
    PROVIDER_TIMEOUT_EMBEDDING: float = 10.0
    PROVIDER_TIMEOUT_CHAT: float = 30.0

    # Slow Query Thresholds (milliseconds)
    SLOW_QUERY_THRESHOLD_RETRIEVAL: float = 1500.0
    SLOW_QUERY_THRESHOLD_LLM: float = 5000.0
    SLOW_QUERY_THRESHOLD_TOTAL: float = 8000.0
    
    # CORS Origins (JSON list or comma separated)
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
