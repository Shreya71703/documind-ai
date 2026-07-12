import os
import hashlib
import uuid
import logging
from typing import Tuple
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """
    Sanitize the filename by extracting the basename and removing path traversal components.
    """
    # Extract only the base name (handles Unix/Windows paths safely)
    base = os.path.basename(filename)
    # Remove any absolute path indicators or directory traversal sequences
    base = base.replace("/", "").replace("\\", "")
    # Remove any leading dots to avoid hidden file issues
    while base.startswith("."):
        base = base[1:]
    if not base:
        # Fallback if sanitization results in empty string
        return "unnamed_document"
    return base

def validate_file_extension(filename: str) -> str:
    """
    Validates that the file has an allowed extension.
    Returns the lowercased extension with leading dot.
    Raises HTTPException 400 if invalid.
    """
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not supported. Supported extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    return ext

def validate_file_size(file_size: int) -> None:
    """
    Validates that the file size does not exceed max limits.
    Raises HTTPException 400 if too large.
    """
    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum limit of {settings.MAX_FILE_SIZE_MB} MB."
        )

def calculate_sha256(content: bytes) -> str:
    """
    Calculates SHA-256 hash of the content bytes.
    """
    return hashlib.sha256(content).hexdigest()

def generate_stored_filename(ext: str) -> str:
    """
    Generates a collision-resistant filename using UUID.
    """
    return f"{uuid.uuid4()}{ext}"

def save_file(content: bytes, stored_filename: str) -> str:
    """
    Saves the file to the configured UPLOAD_DIR and returns the relative path.
    """
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    file_path = os.path.join(settings.UPLOAD_DIR, stored_filename)
    
    # Secure validation to ensure the path is within UPLOAD_DIR
    real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    real_file_path = os.path.abspath(file_path)
    if not real_file_path.startswith(real_upload_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File path traversal detected."
        )
        
    with open(file_path, "wb") as f:
        f.write(content)
        
    return file_path

def delete_file(storage_path: str) -> None:
    """
    Deletes the file at storage_path. Logs warnings on failure instead of raising uncaught exceptions.
    """
    # Ensure the path is strictly within the UPLOAD_DIR to prevent arbitrary deletion
    real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    real_file_path = os.path.abspath(storage_path)
    
    if not real_file_path.startswith(real_upload_dir):
        logger.error(f"Attempted deletion of file outside upload directory: {storage_path}")
        return
        
    if os.path.exists(storage_path):
        try:
            os.remove(storage_path)
            logger.info(f"Successfully deleted file from storage: {storage_path}")
        except Exception as e:
            logger.error(f"Failed to delete file from storage: {storage_path}. Error: {e}")
    else:
        logger.warning(f"File not found in storage for deletion: {storage_path}")
