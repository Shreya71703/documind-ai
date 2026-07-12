import uuid
from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.document import RetrievedSource

class ChatSessionCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=100, description="Optional custom title for the chat session")
    document_ids: List[uuid.UUID] = Field(..., description="List of document IDs to associate with the chat session")

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        if not v:
            raise ValueError("At least one document ID must be provided.")
        if len(v) != len(set(v)):
            raise ValueError("document_ids must not contain duplicates.")
        return v

class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    document_ids: List[uuid.UUID] = []

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_document_ids(cls, data: Any) -> Any:
        # Extract list of document IDs from associated ORM documents list safely
        from sqlalchemy import inspect
        try:
            state = inspect(data)
            # If documents relation is in state.dict, it is loaded!
            if "documents" in state.dict and state.dict["documents"] is not None:
                data.document_ids = [d.id for d in state.dict["documents"]]
        except Exception:
            # Fallback for non-ORM objects or mocks
            if hasattr(data, "documents") and getattr(data, "documents") is not None:
                try:
                    data.document_ids = [d.id for d in data.documents]
                except Exception:
                    pass
        return data

class ChatSessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100, description="New title for the session")
    is_pinned: Optional[bool] = Field(None, description="Whether to pin the session")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError("Title cannot be empty or whitespace only.")
            return v.strip()
        return v

class ChatQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="The RAG grounded question to ask")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Question must not be empty or whitespace only.")
        return v.strip()

class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: Optional[List[RetrievedSource]] = Field(None, alias="sources")
    created_at: datetime

    # Configure Pydantic v2 to load from ORM attributes and allow aliases in serialization
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ChatHistoryResponse(BaseModel):
    session: ChatSessionResponse
    messages: List[ChatMessageResponse]
