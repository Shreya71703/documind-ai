import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.document import Document
from app.schemas.document import RetrievalResponse, RetrievedSource
from app.services.embeddings import embed_query
from app.services.vector_store import query_similarity
from app.services.exceptions import ProviderError

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Service Exceptions
# -------------------------------------------------------------

class RetrievalError(Exception):
    """Base exception for retrieval service."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class DocumentNotIndexedError(RetrievalError):
    """Raised when a selected document is not indexed or unavailable."""
    pass

class InvalidRetrievalQueryError(RetrievalError):
    """Raised when a retrieval query is invalid."""
    pass

# -------------------------------------------------------------
# Semantic Retrieval Service Function
# -------------------------------------------------------------

async def auto_rehydrate_user_documents(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None
) -> None:
    """
    Ensures that vector store in memory contains chunks for all indexed documents belonging to user_id.
    If server restarted and _inmemory_store was wiped, this transparently re-extracts and re-embeds
    documents directly from storage.
    """
    from app.services.vector_store import count_document_vectors, ingest_document_chunks
    from app.services.document_processor import process_document
    from app.services.embeddings import embed_chunks

    stmt = select(Document).where(
        Document.user_id == user_id,
        Document.index_status == "indexed"
    )
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))
        
    res = await db.execute(stmt)
    docs = res.scalars().all()
    
    for doc in docs:
        if count_document_vectors(user_id, doc.id) == 0:
            logger.info(f"[Auto-Rehydrate] Re-indexing missing vectors in memory for document: '{doc.original_filename}' (ID: {doc.id})")
            try:
                processing_result = process_document(
                    document_id=doc.id,
                    file_path=doc.storage_path,
                    original_filename=doc.original_filename,
                    fallback_text=doc.extracted_text
                )
                if processing_result.chunks:
                    texts = [c.content for c in processing_result.chunks]
                    embeddings = embed_chunks(texts)
                    ingest_document_chunks(
                        user_id=user_id,
                        document_id=doc.id,
                        chunks=processing_result.chunks,
                        embeddings=embeddings
                    )
                    logger.info(f"[Auto-Rehydrate] Successfully re-hydrated {len(processing_result.chunks)} chunks for '{doc.original_filename}'")
            except Exception as e:
                logger.error(f"[Auto-Rehydrate] Failed to re-hydrate doc {doc.id}: {e}")

async def retrieve_context(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None,
    top_k: Optional[int] = None
) -> RetrievalResponse:
    """
    Performs secure semantic retrieval.
    1. Validates selected documents ownership and indexing state.
    2. Auto-rehydrates vector store if memory was wiped (e.g. after server restart).
    3. Embeds the query.
    4. Queries vector store for top_k matches with user isolation.
    5. Normalizes, deduplicates, and validates results.
    6. Assembles context bounded by RAG_MAX_CONTEXT_CHARS.
    """
    # 1. Validate query
    if not query or not query.strip():
        raise InvalidRetrievalQueryError("Query must not be empty or whitespace only.")

    # 2. Validate selected documents if provided
    if document_ids:
        for doc_id in document_ids:
            stmt = select(Document).where(
                Document.id == doc_id,
                Document.user_id == user_id
            )
            res = await db.execute(stmt)
            doc = res.scalars().first()
            if not doc:
                raise DocumentNotIndexedError("Document not found.", status_code=404)
            if doc.index_status != "indexed":
                raise DocumentNotIndexedError(
                    f"Document '{doc.original_filename}' is not fully indexed. Current status: {doc.index_status}",
                    status_code=400
                )

    # 2b. AUTO-REHYDRATE: If vectors were lost (e.g. server restart), re-index on the fly!
    await auto_rehydrate_user_documents(db, user_id, document_ids)

    # 3. Generate query embedding
    import time
    from app.core.logging_config import log_structured
    
    t_start = time.perf_counter()
    try:
        query_embedding = embed_query(query)
    except ProviderError as exc:
        raise exc
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        raise RetrievalError(f"Embedding generation failed: {str(e)}", status_code=500)

    dur_emb = (time.perf_counter() - t_start) * 1000.0
    log_structured(
        logging.INFO,
        "query_embedding_complete",
        "query_embedding",
        duration_ms=dur_emb,
        provider=settings.AI_PROVIDER,
        user_id=user_id
    )

    # 4. Query vector store with retry logic (STEP 9)
    t_start = time.perf_counter()
    search_limit = top_k if top_k is not None else settings.RAG_TOP_K
    try:
        raw_results = query_similarity(
            query_embedding=query_embedding,
            user_id=user_id,
            document_ids=document_ids,
            top_k=search_limit
        )
        
        # STEP 9: RETRY RETRIEVAL if zero matches found
        if not raw_results and document_ids:
            logger.warning(f"[RAG Retry] 0 matches with strict document_ids filter {document_ids}. Retrying without document filter...")
            raw_results = query_similarity(
                query_embedding=query_embedding,
                user_id=user_id,
                document_ids=None,  # search all user's documents
                top_k=max(search_limit, 10)
            )

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise RetrievalError(f"Vector search failed: {str(e)}", status_code=500)
    dur_retrieval = (time.perf_counter() - t_start) * 1000.0
    log_structured(
        logging.INFO,
        "vector_retrieval_complete",
        "vector_retrieval",
        duration_ms=dur_retrieval,
        user_id=user_id,
        extra={"document_ids": [str(d) for d in document_ids] if document_ids else []}
    )

    # Check slow retrieval threshold
    if dur_retrieval > settings.SLOW_QUERY_THRESHOLD_RETRIEVAL:
        log_structured(
            logging.WARNING,
            "slow_query_warning",
            "vector_retrieval",
            duration_ms=dur_retrieval,
            user_id=user_id,
            extra={
                "threshold_ms": settings.SLOW_QUERY_THRESHOLD_RETRIEVAL,
                "document_ids": [str(d) for d in document_ids] if document_ids else []
            }
        )

    # 5. Normalize results with defense-in-depth ownership checks and deduplication
    t_assembly_start = time.perf_counter()
    normalized_chunks = []
    seen_vector_ids = set()
    seen_contents = set()

    for item in raw_results:
        vector_id = item.get("id")
        content = item.get("content")
        metadata = item.get("metadata", {})
        distance = item.get("distance", 0.0)

        if not vector_id or not content:
            continue

        # Defense-in-depth: exclude any mismatches in user ownership metadata
        retrieved_user_id = metadata.get("user_id")
        if retrieved_user_id != str(user_id):
            logger.warning(
                f"Security Warning: Vector chunk user mismatch. Expected {user_id}, got {retrieved_user_id}."
            )
            continue

        # Deduplicate exact vector IDs
        if vector_id in seen_vector_ids:
            continue
        seen_vector_ids.add(vector_id)

        # Deduplicate identical content strings (case-insensitive whitespace normalization)
        norm_content = content.strip()
        if norm_content in seen_contents:
            continue
        seen_contents.add(norm_content)

        try:
            chunk_doc_id = uuid.UUID(metadata["document_id"])
        except ValueError:
            logger.error(f"Invalid UUID in vector metadata: {metadata['document_id']}")
            continue

        normalized_chunks.append({
            "vector_id": vector_id,
            "content": content,
            "document_id": chunk_doc_id,
            "chunk_index": int(metadata["chunk_index"]),
            "source_filename": metadata["source_filename"],
            "file_type": metadata["file_type"],
            "page_number": int(metadata["page_number"]) if "page_number" in metadata and metadata["page_number"] is not None else None,
            "distance": float(distance)
        })

    # 6. Assemble context respecting RAG_MAX_CONTEXT_CHARS limit
    context_parts = []
    sources = []
    context_truncated = False
    current_chars = 0
    citation_idx = 1

    for chunk in normalized_chunks:
        citation_label = f"SOURCE {citation_idx}"
        
        # Build structured chunk header
        header = f"[{citation_label}]\nFile: {chunk['source_filename']}\n"
        if chunk["page_number"] is not None:
            header += f"Page: {chunk['page_number']}\n"
        header += f"Chunk: {chunk['chunk_index']}\n\n"
        
        body = f"{chunk['content']}\n\n"
        full_text = header + body

        if current_chars + len(full_text) <= settings.RAG_MAX_CONTEXT_CHARS:
            context_parts.append(full_text)
            current_chars += len(full_text)
            
            sources.append(
                RetrievedSource(
                    citation_id=citation_label,
                    document_id=chunk["document_id"],
                    source_filename=chunk["source_filename"],
                    file_type=chunk["file_type"],
                    page_number=chunk["page_number"],
                    chunk_index=chunk["chunk_index"],
                    distance=chunk["distance"]
                )
            )
            citation_idx += 1
        else:
            context_truncated = True
            # Edge-case: If first chunk alone exceeds context limit, truncate it safely
            if not context_parts:
                allowed_chars = settings.RAG_MAX_CONTEXT_CHARS - len(header)
                if allowed_chars > 0:
                    truncated_content = chunk["content"][:allowed_chars]
                    context_parts.append(header + truncated_content + "\n\n")
                    sources.append(
                        RetrievedSource(
                          citation_id=citation_label,
                          document_id=chunk["document_id"],
                          source_filename=chunk["source_filename"],
                          file_type=chunk["file_type"],
                          page_number=chunk["page_number"],
                          chunk_index=chunk["chunk_index"],
                          distance=chunk["distance"]
                        )
                    )
            break

    assembled_context = "".join(context_parts).strip()
    dur_assembly = (time.perf_counter() - t_assembly_start) * 1000.0
    log_structured(
        logging.INFO,
        "context_assembly_complete",
        "context_assembly",
        duration_ms=dur_assembly,
        user_id=user_id
    )

    return RetrievalResponse(
        query=query,
        retrieved_count=len(normalized_chunks),
        included_count=len(sources),
        context=assembled_context,
        sources=sources,
        context_truncated=context_truncated
    )
