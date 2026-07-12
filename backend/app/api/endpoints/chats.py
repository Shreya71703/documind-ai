import uuid
import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.limiter import limiter
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionUpdate,
    ChatQuestionRequest,
    ChatMessageResponse,
    ChatHistoryResponse
)
from app.services.rag import generate_grounded_answer, RAGError
from app.services.exceptions import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    request: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatSessionResponse:
    """
    Create a new chat session associated with one or more indexed documents.
    """
    # 1. Fetch and validate selected documents
    validated_documents = []
    for doc_id in request.document_ids:
        stmt = select(Document).where(
            Document.id == doc_id,
            Document.user_id == current_user.id
        )
        res = await db.execute(stmt)
        doc = res.scalars().first()
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found."
            )
        
        if doc.index_status != "indexed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document '{doc.original_filename}' is not fully indexed."
            )
        validated_documents.append(doc)

    # 2. Create chat session
    title = request.title.strip() if (request.title and request.title.strip()) else "New Chat"
    session = ChatSession(
        user_id=current_user.id,
        title=title,
        is_pinned=False
    )
    
    # Associate documents
    session.documents.extend(validated_documents)
    
    db.add(session)
    try:
        await db.commit()
        await db.refresh(session)
        # Manually populate document_ids to avoid lazy loading
        session.document_ids = [d.id for d in validated_documents]
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to save chat session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat session."
        )
        
    return session

@router.get("", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[ChatSessionResponse]:
    """
    List all chat sessions belonging to the authenticated user, ordered by pinned first, then newest.
    """
    stmt = (
        select(ChatSession)
        .options(selectinload(ChatSession.documents))
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc())
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()
    return sessions

@router.get("/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatHistoryResponse:
    """
    Retrieve session details and chronological message history.
    """
    # Query session with eager loading of documents and messages
    stmt = (
        select(ChatSession)
        .options(
            selectinload(ChatSession.documents),
            selectinload(ChatSession.messages)
        )
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    session = res.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found."
        )

    # Order messages chronologically
    ordered_messages = sorted(session.messages, key=lambda m: m.created_at)
    
    return ChatHistoryResponse(
        session=session,
        messages=ordered_messages
    )

@router.patch("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: uuid.UUID,
    request: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatSessionResponse:
    """
    Update session metadata (title, is_pinned).
    """
    stmt = (
        select(ChatSession)
        .options(selectinload(ChatSession.documents))
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    session = res.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found."
        )

    if request.title is not None:
        session.title = request.title
    if request.is_pinned is not None:
        session.is_pinned = request.is_pinned
        
    session.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
        await db.refresh(session)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update chat session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chat session."
        )
        
    return session

@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Delete a chat session and its associated message history. Does not delete documents.
    """
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    )
    res = await db.execute(stmt)
    session = res.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found."
        )

    await db.delete(session)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete chat session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat session."
        )
        
    return {"detail": "Chat session deleted successfully."}

@router.post("/{session_id}/messages", response_model=ChatMessageResponse)
@limiter.limit("15/minute")
async def ask_question_endpoint(
    request: Request,  # Required by SlowAPI limiter
    session_id: uuid.UUID,
    question_in: ChatQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatMessageResponse:
    """
    Ask a grounded question in a chat session.
    Persists user question, generates semantic RAG response, and persists validated assistant response.
    """
    # 1. Fetch chat session
    stmt = (
        select(ChatSession)
        .options(selectinload(ChatSession.documents))
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    res = await db.execute(stmt)
    session = res.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found."
        )

    # 2. Verify associated documents remain available and indexed
    document_ids = []
    for doc in session.documents:
        if doc.index_status != "indexed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Associated document '{doc.original_filename}' is not fully indexed."
            )
        document_ids.append(doc.id)

    # 3. Create user message and flush to active transaction
    user_msg = ChatMessage(
        chat_session_id=session_id,
        role=MessageRole.USER,
        content=question_in.question
    )
    db.add(user_msg)
    
    try:
        await db.flush()
    except Exception as e:
        logger.error(f"Failed to flush user message to database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store user message."
        )

    # 4. Generate grounded RAG answer
    try:
        rag_result = await generate_grounded_answer(
            db=db,
            question=question_in.question,
            user_id=current_user.id,
            document_ids=document_ids
        )
    except RAGError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        )
    except ProviderError as exc:
        await db.rollback()
        raise exc
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected RAG execution crash: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Grounded answer generation failed."
        )

    # 5. Persist validated assistant response with citations
    citations_data = [c.model_dump(mode="json") for c in rag_result.citations] if rag_result.citations else None
    
    assistant_msg = ChatMessage(
        chat_session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=rag_result.answer,
        sources=citations_data
    )
    db.add(assistant_msg)
    
    session.updated_at = datetime.now(timezone.utc)
    
    try:
        await db.commit()
        await db.refresh(assistant_msg)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit conversation messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store assistant response."
        )

    return assistant_msg
