import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentResponse, DocumentProcessResponse, DocumentIndexResponse
from app.services.document_processor import process_document, DocumentProcessingError
from app.services.embeddings import embed_chunks, EmbeddingError, EmbeddingConfigurationError, EmbeddingGenerationError
from app.services.exceptions import ProviderError
from app.services.vector_store import (
    ingest_document_chunks,
    delete_document_vectors,
    AlreadyIndexedError,
    VectorStoreError
)
from app.services.document import (
    sanitize_filename,
    validate_file_extension,
    validate_file_size,
    calculate_sha256,
    generate_stored_filename,
    save_file,
    delete_file
)
from app.core.config import settings

router = APIRouter()

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    """
    Upload a document securely.
    Validates file extension, size, computes hash to check duplicate uploads for the user,
    saves the file physically, and stores document metadata in the database.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is missing."
        )

    # 1. Validate extension
    ext = validate_file_extension(file.filename)

    # 2. Read content safely to validate size
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read upload file: {str(e)}"
        )

    file_size = len(content)
    validate_file_size(file_size)

    # 3. Calculate SHA-256 hash
    doc_hash = calculate_sha256(content)

    # 4. Check duplicate hash for the current user
    stmt = select(Document).where(
        Document.user_id == current_user.id,
        Document.document_hash == doc_hash
    )
    result = await db.execute(stmt)
    existing_doc = result.scalars().first()
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate file: This document has already been uploaded."
        )

    # 5. Sanitize and generate filenames
    sanitized_original = sanitize_filename(file.filename)
    stored_filename = generate_stored_filename(ext)

    # 6. Save file to disk
    try:
        storage_path = save_file(content, stored_filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {str(e)}"
        )

    # 7. Create database record
    db_document = Document(
        user_id=current_user.id,
        original_filename=sanitized_original,
        stored_filename=stored_filename,
        file_type=ext.lstrip("."),
        file_size=file_size,
        storage_path=storage_path,
        status=DocumentStatus.UPLOADED,
        document_hash=doc_hash,
        chunk_count=0
    )

    db.add(db_document)
    try:
        await db.commit()
        await db.refresh(db_document)
    except Exception as e:
        await db.rollback()
        # Clean up the stored file to avoid orphaned files
        delete_file(storage_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist document metadata: {str(e)}"
        )

    return db_document

@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[DocumentResponse]:
    """
    List all documents belonging to the authenticated user, ordered by created_at descending.
    """
    stmt = (
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    documents = result.scalars().all()
    return documents

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    """
    Retrieve metadata for a specific document belonging to the authenticated user.
    """
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id
    )
    result = await db.execute(stmt)
    document = result.scalars().first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document

@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Delete a document owned by the authenticated user, cleaning up database metadata and the stored file.
    """
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id
    )
    result = await db.execute(stmt)
    document = result.scalars().first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    storage_path = document.storage_path

    # Delete record from database first
    await db.delete(document)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document metadata: {str(e)}"
        )

    # Clean up the file from disk (handles logging/warnings inside delete_file)
    delete_file(storage_path)

    # Clean up vectors from ChromaDB
    try:
        delete_document_vectors(user_id=current_user.id, document_id=document_id)
    except Exception as e:
        logger.error(f"Failed to delete ChromaDB vectors for document {document_id}: {e}")

    return {"detail": "Document deleted successfully"}


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
async def process_document_endpoint(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentProcessResponse:
    """
    Process an uploaded document: extracts and normalizes text, splits into chunks,
    and updates the database status.
    """
    # 1. Fetch document with ownership check
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id
    )
    result = await db.execute(stmt)
    document = result.scalars().first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    # 2. Transition status to PROCESSING
    document.status = DocumentStatus.PROCESSING
    await db.commit()
    await db.refresh(document)

    # 3. Perform document processing
    try:
        processing_result = process_document(
            document_id=document.id,
            file_path=document.storage_path,
            original_filename=document.original_filename
        )
    except DocumentProcessingError as exc:
        document.status = DocumentStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        )
    except Exception as e:
        document.status = DocumentStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document processing."
        )

    # 4. Successful processing: update chunk count and transition status to READY
    document.status = DocumentStatus.READY
    document.chunk_count = processing_result.chunk_count
    await db.commit()
    await db.refresh(document)

    return DocumentProcessResponse(
        document_id=document.id,
        status=document.status,
        extracted_text_length=processing_result.extracted_text_length,
        chunk_count=processing_result.chunk_count
    )

@router.post("/{document_id}/index", response_model=DocumentIndexResponse)
async def index_document_endpoint(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentIndexResponse:
    """
    Ingest document chunks into ChromaDB vector database.
    """
    # 1. Fetch document with ownership check
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id
    )
    result = await db.execute(stmt)
    document = result.scalars().first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    # 2. Reject unsupported states
    if document.index_status == "indexing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is currently being indexed."
        )

    # 3. Transition status to indexing in DB
    document.index_status = "indexing"
    await db.commit()
    await db.refresh(document)

    try:
        # 4. Extract and chunk using Step 5 document_processor
        processing_result = process_document(
            document_id=document.id,
            file_path=document.storage_path,
            original_filename=document.original_filename
        )
        
        # 5. Extract texts and generate embeddings
        texts = [chunk.content for chunk in processing_result.chunks]
        embeddings = embed_chunks(texts)
        
        # 6. Ingest into ChromaDB
        ingest_document_chunks(
            user_id=current_user.id,
            document_id=document.id,
            chunks=processing_result.chunks,
            embeddings=embeddings
        )
        
    except AlreadyIndexedError as exc:
        document.index_status = "indexed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    except ProviderError as exc:
        document.index_status = "failed"
        await db.commit()
        raise exc
    except (EmbeddingConfigurationError, EmbeddingGenerationError) as exc:
        document.index_status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    except DocumentProcessingError as exc:
        document.index_status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    except VectorStoreError as exc:
        document.index_status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )
    except Exception as e:
        document.index_status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during document indexing: {str(e)}"
        )

    # 7. Success transition
    document.index_status = "indexed"
    document.chunk_count = processing_result.chunk_count
    await db.commit()
    await db.refresh(document)

    return DocumentIndexResponse(
        document_id=document.id,
        index_status=document.index_status,
        chunk_count=document.chunk_count,
        embedding_model=settings.EMBEDDING_MODEL
    )


