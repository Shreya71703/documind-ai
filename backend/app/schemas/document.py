import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.document import DocumentStatus
from app.core.config import settings

class DocumentResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    index_status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    # Configure Pydantic v2 for ORM mode
    model_config = ConfigDict(from_attributes=True)

class DocumentProcessResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    extracted_text_length: int
    chunk_count: int

class DocumentIndexResponse(BaseModel):
    document_id: uuid.UUID
    index_status: str
    chunk_count: int
    embedding_model: str

class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Semantic search query")
    document_ids: Optional[List[uuid.UUID]] = Field(None, description="Optional list of document IDs to search within")
    top_k: Optional[int] = Field(None, description="Number of results to retrieve")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query must not be empty or whitespace only.")
        return v.strip()

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, v: Optional[List[uuid.UUID]]) -> Optional[List[uuid.UUID]]:
        if v is not None:
            if len(v) != len(set(v)):
                raise ValueError("document_ids must not contain duplicates.")
        return v

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 1:
                raise ValueError("top_k must be at least 1.")
            if v > settings.RAG_MAX_TOP_K:
                raise ValueError(f"top_k must not exceed maximum limit of {settings.RAG_MAX_TOP_K}.")
        return v

class RetrievedSource(BaseModel):
    citation_id: str
    document_id: uuid.UUID
    source_filename: str
    file_type: str
    page_number: Optional[int] = None
    chunk_index: int
    distance: float

class RetrievalResponse(BaseModel):
    query: str
    retrieved_count: int
    included_count: int
    context: str
    sources: List[RetrievedSource]
    context_truncated: bool
