import uuid
import enum
from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Table, Column, Float, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.document import Document

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

# Many-to-Many Association Table
# Prevent duplicate session-document mappings by using composite primary keys
chat_session_documents = Table(
    "chat_session_documents",
    Base.metadata,
    Column(
        "chat_session_id", 
        UUID(as_uuid=True), 
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), 
        primary_key=True
    ),
    Column(
        "document_id", 
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"), 
        primary_key=True
    )
)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="New Chat Session", nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", 
        back_populates="chat_session", 
        cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        secondary=chat_session_documents,
        back_populates="chat_sessions"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        index=True
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    
    # RAG Response optional metadata
    sources: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    
    # Relationships
    chat_session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
