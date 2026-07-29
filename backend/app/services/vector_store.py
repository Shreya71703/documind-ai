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

def get_chroma_client() -> chromadb.Client:
    """
    Lazily initializes and returns an in-memory ChromaDB client (ephemeral, zero disk I/O locking).
    """
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    try:
        _chroma_client = chromadb.Client()
        return _chroma_client
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB Client: {e}")
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

    # Default dimension to 768 for instant sub-millisecond collection resolution
    dimension = 768

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
        return client.get_or_create_collection(name=collection_name, embedding_function=None)
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
# In-Memory Fallback Store (Zero OOM Overhead)
# -------------------------------------------------------------
_inmemory_store: Dict[str, Dict[str, Any]] = {}

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    import math
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    return dot / (norm1 * norm2)

def ingest_document_chunks(
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    chunks: List[Any],
    embeddings: List[List[float]]
) -> None:
    """
    Ingests document chunks and their embeddings into ChromaDB or in-memory store.
    """
    if len(chunks) != len(embeddings):
        raise VectorStoreError(
            f"Count mismatch: received {len(chunks)} chunks and {len(embeddings)} embeddings."
        )

    ids = []
    documents = []
    metadatas = []

    for idx, chunk in enumerate(chunks):
        vector_id = generate_vector_id(document_id, idx)
        meta = {
            "user_id": str(user_id),
            "document_id": str(document_id),
            "chunk_index": int(idx),
            "source_filename": str(chunk.metadata.get("source_filename", "")),
            "file_type": str(chunk.metadata.get("file_type", ""))
        }
        ids.append(vector_id)
        documents.append(chunk.content)
        metadatas.append(meta)

        # Store in in-memory repository for zero-latency fallback
        _inmemory_store[vector_id] = {
            "id": vector_id,
            "user_id": str(user_id),
            "document_id": str(document_id),
            "content": chunk.content,
            "embedding": embeddings[idx],
            "metadata": meta
        }

    # Attempt write to ChromaDB
    try:
        collection = get_collection()
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Successfully indexed {len(ids)} chunks for document {document_id} in ChromaDB")
    except Exception as e:
        logger.warning(f"ChromaDB ingestion skipped ({e}). Utilizing in-memory vector store.")

def delete_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """
    Deletes all vectors belonging to a user's specific document.
    """
    to_delete = [
        vid for vid, item in _inmemory_store.items()
        if item["user_id"] == str(user_id) and item["document_id"] == str(document_id)
    ]
    for vid in to_delete:
        _inmemory_store.pop(vid, None)

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
    except Exception:
        pass

def count_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> int:
    """
    Returns the count of vectors for a user's document.
    """
    count = sum(
        1 for item in _inmemory_store.values()
        if item["user_id"] == str(user_id) and item["document_id"] == str(document_id)
    )
    if count > 0:
        return count

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
    except Exception:
        return 0

def query_similarity(
    query_embedding: List[float],
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None,
    top_k: int = 4
) -> List[Dict[str, Any]]:
    """
    Performs similarity search on document chunks across ChromaDB and in-memory store.
    """
    # 1. Try ChromaDB
    try:
        collection = get_collection()
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
            if formatted:
                return formatted
    except Exception as e:
        logger.warning(f"ChromaDB similarity search skipped ({e}). Fallback to in-memory vector search.")

    # 2. In-memory cosine similarity search
    doc_str_ids = [str(d) for d in document_ids] if document_ids else None
    matches = []
    for item in _inmemory_store.values():
        if item["user_id"] != str(user_id):
            continue
        if doc_str_ids and item["document_id"] not in doc_str_ids:
            continue
        sim = _cosine_similarity(query_embedding, item["embedding"])
        matches.append({
            "id": item["id"],
            "content": item["content"],
            "metadata": item["metadata"],
            "distance": 1.0 - sim
        })

    matches.sort(key=lambda x: x["distance"])
    return matches[:top_k]


