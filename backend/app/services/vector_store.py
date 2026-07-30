import os
import uuid
import logging
import math
from typing import List, Dict, Any, Optional

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

def get_chroma_client() -> Any:
    return None

def get_active_collection_name() -> str:
    return "in_memory_collection"

def get_collection() -> Any:
    return None

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------

def generate_vector_id(document_id: uuid.UUID, chunk_index: int) -> str:
    return f"doc_{document_id}_chunk_{chunk_index}"

def has_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    for item in _inmemory_store.values():
        if item["user_id"] == str(user_id) and item["document_id"] == str(document_id):
            return True
    return False

# -------------------------------------------------------------
# In-Memory Fallback Store (Zero OOM Overhead)
# -------------------------------------------------------------
_inmemory_store: Dict[str, Dict[str, Any]] = {}

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
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
    if len(chunks) != len(embeddings):
        raise VectorStoreError(
            f"Count mismatch: received {len(chunks)} chunks and {len(embeddings)} embeddings."
        )

    for idx, chunk in enumerate(chunks):
        vector_id = generate_vector_id(document_id, idx)
        meta = {
            "user_id": str(user_id),
            "document_id": str(document_id),
            "chunk_index": int(idx),
            "source_filename": str(chunk.metadata.get("source_filename", "")),
            "file_type": str(chunk.metadata.get("file_type", ""))
        }
        _inmemory_store[vector_id] = {
            "id": vector_id,
            "user_id": str(user_id),
            "document_id": str(document_id),
            "content": chunk.content,
            "embedding": embeddings[idx],
            "metadata": meta
        }
    logger.info(f"Successfully indexed {len(chunks)} chunks for document {document_id}")

def delete_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    to_delete = [
        vid for vid, item in _inmemory_store.items()
        if item["user_id"] == str(user_id) and item["document_id"] == str(document_id)
    ]
    for vid in to_delete:
        _inmemory_store.pop(vid, None)

def count_document_vectors(user_id: uuid.UUID, document_id: uuid.UUID) -> int:
    return sum(
        1 for item in _inmemory_store.values()
        if item["user_id"] == str(user_id) and item["document_id"] == str(document_id)
    )

def query_similarity(
    query_embedding: List[float],
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None,
    top_k: int = 4
) -> List[Dict[str, Any]]:
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



