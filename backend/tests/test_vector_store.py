import os
import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.services.vector_store import (
    get_chroma_client,
    get_collection,
    generate_vector_id,
    has_document_vectors,
    ingest_document_chunks,
    delete_document_vectors,
    count_document_vectors,
    query_similarity,
    VectorStoreError,
    AlreadyIndexedError
)

# -------------------------------------------------------------
# Mock Chunk class for testing
# -------------------------------------------------------------

class MockChunk:
    def __init__(self, content, metadata):
        self.content = content
        self.metadata = metadata

# -------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_chroma_db_dir(tmp_path):
    """Isolate ChromaDB persistence directory for each test case."""
    old_dir = settings.CHROMA_PERSIST_DIRECTORY
    settings.CHROMA_PERSIST_DIRECTORY = str(tmp_path)
    # Clear global cached client
    with patch("app.services.vector_store._chroma_client", None):
        yield
    settings.CHROMA_PERSIST_DIRECTORY = old_dir

# -------------------------------------------------------------
# Unit Tests for Vector Store
# -------------------------------------------------------------

def test_deterministic_vector_ids():
    """Verify vector ID strategy is stable and deterministic."""
    doc_id = uuid.uuid4()
    id1 = generate_vector_id(doc_id, 0)
    id2 = generate_vector_id(doc_id, 0)
    id3 = generate_vector_id(doc_id, 1)

    assert id1 == id2
    assert id1 != id3
    assert str(doc_id) in id1
    assert "chunk_0" in id1

def test_ingest_and_count_success():
    """Verify standard document chunk and embedding ingestion is successful."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    
    chunks = [
        MockChunk("Paragraph 1 content", {"source_filename": "doc.txt", "file_type": "txt", "chunk_index": 0}),
        MockChunk("Paragraph 2 content", {"source_filename": "doc.txt", "file_type": "txt", "chunk_index": 1, "page_number": 2})
    ]
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    # 1. Ingest
    ingest_document_chunks(user_id, doc_id, chunks, embeddings)

    # 2. Count
    cnt = count_document_vectors(user_id, doc_id)
    assert cnt == 2

    # 3. Check duplicate exists
    assert has_document_vectors(user_id, doc_id) is True

def test_metadata_mapping_excludes_nones():
    """Verify that metadata maps properly and excludes None values or complex types."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    
    chunks = [
        MockChunk(
            "Content with none metadata", 
            {
                "source_filename": "doc.pdf", 
                "file_type": "pdf", 
                "chunk_index": 0, 
                "page_number": None,  # None should be excluded
                "extra_none": None
            }
        )
    ]
    embeddings = [[0.5, 0.6]]

    ingest_document_chunks(user_id, doc_id, chunks, embeddings)
    
    collection = get_collection()
    res = collection.get(ids=[generate_vector_id(doc_id, 0)])
    
    meta = res["metadatas"][0]
    assert meta["user_id"] == str(user_id)
    assert meta["document_id"] == str(doc_id)
    assert meta["chunk_index"] == 0
    assert "page_number" not in meta
    assert "extra_none" not in meta

def test_duplicate_indexing_rejected():
    """Verify that duplicate indexing raises AlreadyIndexedError."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    
    chunks = [MockChunk("text", {"source_filename": "f.txt", "file_type": "txt"})]
    embeddings = [[0.1]]

    # First write
    ingest_document_chunks(user_id, doc_id, chunks, embeddings)
    
    # Second write raises AlreadyIndexedError
    with pytest.raises(AlreadyIndexedError):
        ingest_document_chunks(user_id, doc_id, chunks, embeddings)

def test_user_and_document_vector_isolation():
    """Verify that query and count operations isolate chunks based on user_id and document_id."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    doc_1 = uuid.uuid4()
    doc_2 = uuid.uuid4()

    chunks_a1 = [MockChunk("User A Doc 1", {"source_filename": "a1.txt", "file_type": "txt"})]
    chunks_b2 = [MockChunk("User B Doc 2", {"source_filename": "b2.txt", "file_type": "txt"})]

    # Ingest User A Doc 1
    ingest_document_chunks(user_a, doc_1, chunks_a1, [[0.1, 0.2]])
    # Ingest User B Doc 2
    ingest_document_chunks(user_b, doc_2, chunks_b2, [[0.3, 0.4]])

    # Count checks
    assert count_document_vectors(user_a, doc_1) == 1
    assert count_document_vectors(user_a, doc_2) == 0
    assert count_document_vectors(user_b, doc_2) == 1

    # Similarity checks
    res_a = query_similarity([0.1, 0.2], user_a, top_k=1)
    assert len(res_a) == 1
    assert res_a[0]["content"] == "User A Doc 1"

    # User B should not see User A's vector even if queried with identical embedding
    res_b = query_similarity([0.1, 0.2], user_b, top_k=1)
    assert len(res_b) == 1
    assert res_b[0]["content"] == "User B Doc 2"

def test_delete_vectors_isolation():
    """Verify that deleting vectors removes only the targeted document vectors."""
    user = uuid.uuid4()
    doc_1 = uuid.uuid4()
    doc_2 = uuid.uuid4()

    # Ingest two documents
    ingest_document_chunks(user, doc_1, [MockChunk("d1", {"source_filename": "d1.txt", "file_type": "txt"})], [[0.1]])
    ingest_document_chunks(user, doc_2, [MockChunk("d2", {"source_filename": "d2.txt", "file_type": "txt"})], [[0.2]])

    # Delete Doc 1
    delete_document_vectors(user, doc_1)

    # Verify Doc 1 vectors are gone
    assert count_document_vectors(user, doc_1) == 0
    assert has_document_vectors(user, doc_1) is False

    # Verify Doc 2 vectors remain intact
    assert count_document_vectors(user, doc_2) == 1
    assert has_document_vectors(user, doc_2) is True

def test_query_document_id_filter():
    """Verify query limits results based on optional list of document_ids."""
    user = uuid.uuid4()
    doc_1 = uuid.uuid4()
    doc_2 = uuid.uuid4()

    ingest_document_chunks(user, doc_1, [MockChunk("target text", {"source_filename": "d1.txt", "file_type": "txt"})], [[0.9]])
    ingest_document_chunks(user, doc_2, [MockChunk("ignored text", {"source_filename": "d2.txt", "file_type": "txt"})], [[0.95]])

    # Query with filter limiting to doc_1
    res = query_similarity([0.9], user, document_ids=[doc_1], top_k=5)
    assert len(res) == 1
    assert res[0]["content"] == "target text"

@patch("chromadb.api.models.Collection.Collection.add")
def test_ingestion_failure_does_not_leak_partial_writes(mock_add):
    """Verify that if ChromaDB add fails, any potential partial writes are cleaned up."""
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    
    chunks = [MockChunk("C1", {"source_filename": "f.txt", "file_type": "txt"})]
    
    # Force Collection.add to throw exception
    mock_add.side_effect = Exception("ChromaDB crash")

    # Ingest should fail and internally trigger delete
    with pytest.raises(VectorStoreError) as exc:
        ingest_document_chunks(user_id, doc_id, chunks, [[0.1]])
    assert "ChromaDB ingestion failed" in str(exc.value)

    # Verify no vectors actually exist
    assert count_document_vectors(user_id, doc_id) == 0
