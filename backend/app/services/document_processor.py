import os
import re
import uuid
import logging
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from pypdf import PdfReader
import docx

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Custom Service Exceptions
# -------------------------------------------------------------

class DocumentProcessingError(Exception):
    """Base exception for document processing errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class UnsupportedFileTypeError(DocumentProcessingError):
    """Raised when the file type is not supported."""
    pass

class StoredFileMissingError(DocumentProcessingError):
    """Raised when the physical file is missing from storage."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)

class UnreadableFileError(DocumentProcessingError):
    """Raised when the file cannot be read/parsed."""
    pass

class EmptyExtractedContentError(DocumentProcessingError):
    """Raised when no text can be extracted from the file."""
    pass

class ExtractionFailureError(DocumentProcessingError):
    """Raised when text extraction fails."""
    pass

class ChunkingFailureError(DocumentProcessingError):
    """Raised when chunking fails."""
    pass

# -------------------------------------------------------------
# Structured Processing Result Models
# -------------------------------------------------------------

class ChunkResult(BaseModel):
    content: str
    metadata: Dict[str, Any]

class DocumentProcessingResult(BaseModel):
    document_id: uuid.UUID
    extracted_text_length: int
    chunk_count: int
    chunks: List[ChunkResult]
    status: str

# -------------------------------------------------------------
# Text Normalization
# -------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Applies conservative text normalization to:
    - Standardize line endings (\r\n -> \n)
    - Collapse multiple spaces/tabs to a single space
    - Collapse three or more consecutive newlines to exactly two newlines
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    # Standardize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple consecutive spaces/tabs to a single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse three or more consecutive newlines to exactly two newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# -------------------------------------------------------------
# Text Extraction Helpers
# -------------------------------------------------------------

def extract_pdf_pages(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page by page from a PDF.
    Returns list of dicts with keys "text" and "metadata" (page_number).
    """
    pages = []
    try:
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            num_pages = len(reader.pages)
            if num_pages == 0:
                raise EmptyExtractedContentError("PDF contains no pages.")
            for i in range(num_pages):
                page_num = i + 1
                try:
                    page = reader.pages[i]
                    text = page.extract_text() or ""
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num}: {e}")
                    text = ""
                pages.append({
                    "text": text,
                    "metadata": {"page_number": page_num}
                })
    except EmptyExtractedContentError:
        raise
    except Exception as e:
        raise ExtractionFailureError(f"Error opening or reading PDF file: {str(e)}")
    return pages

def extract_docx_paragraphs(file_path: str) -> List[str]:
    """
    Extracts non-empty paragraph text from a Word DOCX.
    """
    try:
        doc = docx.Document(file_path)
        paragraphs = []
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                paragraphs.append(p.text)
        return paragraphs
    except Exception as e:
        raise ExtractionFailureError(f"Error reading DOCX file: {str(e)}")

def extract_text_file(file_path: str) -> str:
    """
    Reads a raw text/markdown file, safely decoding with UTF-8 BOM or UTF-8 replacement fallback.
    """
    try:
        with open(file_path, "rb") as f:
            content_bytes = f.read()
        try:
            return content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise ExtractionFailureError(f"Error reading text file: {str(e)}")

# -------------------------------------------------------------
# Main Processing Service Function
# -------------------------------------------------------------

def process_document(
    document_id: uuid.UUID,
    file_path: str,
    original_filename: str
) -> DocumentProcessingResult:
    """
    Processes a document: validates existences, extracts text, normalizes it,
    splits it into chunks, and returns a structured processing result.
    """
    # 1. Verify file exists
    if not os.path.exists(file_path):
        raise StoredFileMissingError(f"File not found at storage path: {file_path}")

    # 2. Extract text based on file extension
    _, ext = os.path.splitext(original_filename.lower())
    
    extracted_chunks_raw: List[Dict[str, Any]] = []
    
    # We maintain a single text variable for simple length reporting
    total_raw_text = ""

    if ext == ".pdf":
        pages = extract_pdf_pages(file_path)
        # Check if we got any text at all
        has_any_text = any(p["text"].strip() for p in pages)
        if not has_any_text:
            raise EmptyExtractedContentError("PDF contains no extractable text.")
        
        # Keep pages separate to preserve page number metadata
        for p in pages:
            normalized_page = normalize_text(p["text"])
            if normalized_page:
                extracted_chunks_raw.append({
                    "text": normalized_page,
                    "metadata": p["metadata"]
                })
                total_raw_text += p["text"]

    elif ext == ".docx":
        paragraphs = extract_docx_paragraphs(file_path)
        joined_text = "\n\n".join(paragraphs)
        normalized_text = normalize_text(joined_text)
        if not normalized_text:
            raise EmptyExtractedContentError("DOCX contains no extractable text.")
        
        extracted_chunks_raw.append({
            "text": normalized_text,
            "metadata": {}
        })
        total_raw_text = joined_text

    elif ext in [".txt", ".md"]:
        raw_text = extract_text_file(file_path)
        normalized_text = normalize_text(raw_text)
        if not normalized_text:
            raise EmptyExtractedContentError("Text file contains no extractable text.")
        
        extracted_chunks_raw.append({
            "text": normalized_text,
            "metadata": {}
        })
        total_raw_text = raw_text

    else:
        raise UnsupportedFileTypeError(f"Unsupported file type extension: {ext}")

    # 3. Perform chunking using RecursiveCharacterTextSplitter
    try:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""]
        )
    except Exception as e:
        raise ChunkingFailureError(f"Failed to initialize text splitter: {str(e)}")

    processed_chunks: List[ChunkResult] = []
    chunk_index = 0

    for raw_chunk in extracted_chunks_raw:
        chunk_text = raw_chunk["text"]
        source_metadata = raw_chunk["metadata"]

        try:
            split_texts = splitter.split_text(chunk_text)
        except Exception as e:
            raise ChunkingFailureError(f"Failed during text split execution: {str(e)}")

        for text_part in split_texts:
            stripped_text = text_part.strip()
            if not stripped_text:
                continue

            # Build metadata for this chunk
            chunk_metadata = {
                "chunk_index": chunk_index,
                "document_id": str(document_id),
                "source_filename": os.path.basename(original_filename),
                "file_type": ext.lstrip(".")
            }
            # Append source location (e.g., PDF page_number) if available
            chunk_metadata.update(source_metadata)

            processed_chunks.append(
                ChunkResult(content=stripped_text, metadata=chunk_metadata)
            )
            chunk_index += 1

    if not processed_chunks:
        raise ChunkingFailureError("Chunking resulted in 0 non-empty chunks.")

    return DocumentProcessingResult(
        document_id=document_id,
        extracted_text_length=len(total_raw_text),
        chunk_count=len(processed_chunks),
        chunks=processed_chunks,
        status="ready"
    )
