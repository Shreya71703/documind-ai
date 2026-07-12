import os
import uuid
import logging
from typing import List, Dict, Any, Optional
import chromadb

from app.core.config import settings

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Service Exceptions
# -------------------------------------------------------------

class VectorStoreError(Exception):
    """Base exception for vector store errors."""
    pass

class AlreadyIndexedError(VectorStoreError):
    """Raised when a document is already indexed in vector database."""
    pass

# -------------------------------------------------------------
# Lazy Chroma Client and Collection Access
# -------------------------------------------------------------

_chroma_client = None

def get_chroma_client() -> chromadb.PersistentClient:
    """
    Lazily initializes and returns a persistent ChromaDB client.
    """
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    try:
        # Create storage directory if needed
        os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)
        return _chroma_client
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB PersistentClient: {e}")
        raise VectorStoreError(f"ChromaDB client initialization failed: {str(e)}")

_active_collection_name = None

def get_active_collection_name() -> str:
    """
    Derives and caches the active ChromaDB collection name based on the active provider,
    model name, and embedding dimension.
    """
    global _active_collection_name
    if _active_collection_name is not None:
        return _active_collection_name

    provider = settings.AI_PROVIDER.lower()
    if provider == "gemini":
        model_raw = settings.GEMINI_EMBEDDING_MODEL
    else:
        model_raw = settings.EMBEDDING_MODEL

    # Normalize model name: replace non-alphanumeric characters with underscores
    import re
    model_clean = re.sub(r'[^a-zA-Z0-9_-]', '_', model_raw)
    model_clean = re.sub(r'_+', '_', model_clean).strip('_')

    # Get active dimension
    try:
        from app.services.embeddings import get_embeddings_client
        emb_client = get_embeddings_client()
        test_emb = emb_client.embed_query("test")
        dimension = len(test_emb)
    except Exception as e:
        logger.error(f"Failed to resolve active embedding dimension: {e}")
        # Default fallback dimensions if API key is not ready or call fails
        if "gemini" in model_clean.lower():
            dimension = 3072
        else:
            dimension = 1536

    col_name = f"rag_{provider}_{model_clean}_{dimension}"
    col_name = col_name[:63].strip('_').strip('-')
    _active_collection_name = col_name
    logger.info(f"Resolved active ChromaDB collection name: {_active_collection_name}")
    return _active_collection_name

def get_collection() -> Any:
    """
    Gets or creates the isolated RAG collection based on active provider and model settings.
    """
    client = get_chroma_client()
    collection_name = get_active_collection_name()
    try:
        return client.get_or_create_collection(name=collection_name)
    except Exception as e:
        logger.error(f"Failed to access ChromaDB collection '{collection_name}': {e}")
        raise VectorStoreError(f"ChromaDB collection access failed: {str(e)}")

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------

def generate_vector_id(document_id: uuid.UUID, chunk_index: int) -> str:
    """
    Generates a deterministic vector ID for a document chunk.
    """
    return f"doc_{document_id}_chunk_{chunk_index}"

def has_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    """
    Checks if vectors already exist for the specified user and document.
    """
    try:
        collection = get_collection()
        results = collection.get(
            where={
                "$and": [
                    {"user_id": str(user_id)},
                    {"document_id": str(document_id)}
                ]
            },
            limit=1
        )
        return len(results.get("ids", [])) > 0
    except Exception as e:
        logger.error(f"Failed to query existing document vectors: {e}")
        raise VectorStoreError(f"Error checking vector existence: {str(e)}")

# -------------------------------------------------------------
# Ingestion, Deletion, Counting, and Querying
# -------------------------------------------------------------

def ingest_document_chunks(
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    chunks: List[Any],
    embeddings: List[List[float]]
) -> None:
    """
    Ingests document chunks and their embeddings into ChromaDB.
    Validates structure, enforces per-user idempotency, and handles failures cleanly.
    """
    # 1. Check if document has already been indexed
    if has_document_vectors(user_id, document_id):
        raise AlreadyIndexedError(
            f"Document {document_id} has already been indexed for this user."
        )

    # 2. Validate embedding counts
    if len(chunks) != len(embeddings):
        raise VectorStoreError(
            f"Count mismatch: received {len(chunks)} chunks and {len(embeddings)} embeddings."
        )

    collection = get_collection()

    ids = []
    documents = []
    metadatas = []

    # 3. Format items and sanitize metadata
    for idx, chunk in enumerate(chunks):
        vector_id = generate_vector_id(document_id, idx)
        
        # Build metadata keeping only valid scalar values (no Nones or complex types)
        meta = {
            "user_id": str(user_id),
            "document_id": str(document_id),
            "chunk_index": int(idx),
            "source_filename": str(chunk.metadata["source_filename"]),
            "file_type": str(chunk.metadata["file_type"])
        }
        
        # page_number is optional but preserved if it exists
        if "page_number" in chunk.metadata and chunk.metadata["page_number"] is not None:
            meta["page_number"] = int(chunk.metadata["page_number"])

        ids.append(vector_id)
        documents.append(chunk.content)
        metadatas.append(meta)

    # 4. Write to ChromaDB
    try:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Successfully indexed {len(ids)} chunks for document {document_id}")
    except Exception as e:
        logger.error(f"Failed to add vectors to collection: {e}")
        # Perform document-scoped rollback cleanup in active collection
        try:
            collection.delete(
                where={
                    "$and": [
                        {"user_id": str(user_id)},
                        {"document_id": str(document_id)}
                    ]
                }
            )
            logger.info("Cleaned up partial ingestion vectors successfully.")
        except Exception as cleanup_err:
            logger.error(f"Failed to clean up partial vectors: {cleanup_err}")
        raise VectorStoreError(f"ChromaDB ingestion failed: {str(e)}")

def delete_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """
    Deletes all vectors belonging to a user's specific document.
    """
    try:
        collection = get_collection()
        collection.delete(
            where={
                "$and": [
                    {"user_id": str(user_id)},
                    {"document_id": str(document_id)}
                ]
            }
        )
        logger.info(f"Deleted vectors for document {document_id}")
    except Exception as e:
        logger.error(f"Failed to delete document vectors: {e}")
        raise VectorStoreError(f"Vector deletion failed: {str(e)}")

def count_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> int:
    """
    Returns the count of vectors for a user's document.
    """
    try:
        collection = get_collection()
        results = collection.get(
            where={
                "$and": [
                    {"user_id": str(user_id)},
                    {"document_id": str(document_id)}
                ]
            }
        )
        return len(results.get("ids", []))
    except Exception as e:
        logger.error(f"Failed to count vectors for document {document_id}: {e}")
        raise VectorStoreError(f"Vector counting failed: {str(e)}")

def query_similarity(
    query_embedding: List[float],
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None,
    top_k: int = 4
) -> List[Dict[str, Any]]:
    """
    Performs similarity search on document chunks, enforcing user ownership.
    If document_ids is provided, limits search to only those documents.
    """
    try:
        collection = get_collection()
        
        # Build strict ownership filter
        filters = [{"user_id": str(user_id)}]
        
        if document_ids:
            if len(document_ids) == 1:
                filters.append({"document_id": str(document_ids[0])})
            elif len(document_ids) > 1:
                filters.append({"document_id": {"$in": [str(d) for d in document_ids]}})
        
        where_filter = {"$and": filters} if len(filters) > 1 else filters[0]
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter
        )
        
        formatted = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0] if results.get("distances") else [0.0] * len(ids)
            
            for i in range(len(ids)):
                formatted.append({
                    "id": ids[i],
                    "content": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else 0.0
                })
        return formatted
    except Exception as e:
        logger.error(f"Similarity query failed: {e}")
        raise VectorStoreError(f"Similarity search failed: {str(e)}")
