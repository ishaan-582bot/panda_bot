"""
File validation utilities including magic number checking.
"""

import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Magic numbers for file type validation
MAGIC_NUMBERS = {
    # PDF
    b'%PDF': 'pdf',
    # PNG
    b'\x89PNG\r\n\x1a\n': 'png',
    # JPEG
    b'\xff\xd8\xff': 'jpeg',
    # GIF
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    # ZIP (DOCX, XLSX are ZIP-based)
    b'PK\x03\x04': 'zip',
    # TIFF
    b'II*\x00': 'tiff',  # Little-endian
    b'MM\x00*': 'tiff',  # Big-endian
    # BMP
    b'BM': 'bmp',
}

# MIME type to extension mapping
MIME_TO_EXT = {
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/msword': 'doc',
    'text/plain': 'txt',
    'text/csv': 'csv',
    'application/json': 'json',
    'image/png': 'png',
    'image/jpeg': 'jpeg',
    'image/jpg': 'jpeg',
    'image/tiff': 'tiff',
    'image/bmp': 'bmp',
    'application/zip': 'zip',
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Args:
        filename: Original filename from user input
        
    Returns:
        Sanitized filename safe for filesystem operations
    """
    if not filename:
        return "unnamed"
    
    # Remove null bytes (null byte injection attack)
    filename = filename.replace('\x00', '')
    
    # Get basename (remove any path components)
    filename = os.path.basename(filename)
    
    # Remove any remaining path separators
    filename = filename.replace('/', '').replace('\\', '')
    
    # Remove leading dots (hidden files)
    filename = filename.lstrip('.')
    
    # Replace dangerous characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    
    # If empty after sanitization, use default
    if not filename:
        filename = "unnamed"
    
    return filename


def detect_file_type_from_content(content: bytes) -> Optional[str]:
    """
    Detect file type from magic numbers in content.
    
    Args:
        content: First few bytes of file content
        
    Returns:
        Detected file type or None
    """
    if not content:
        return None
    
    # Check magic numbers (longest first to avoid false matches)
    for magic, file_type in sorted(MAGIC_NUMBERS.items(), key=lambda x: -len(x[0])):
        if content.startswith(magic):
            # Special handling for ZIP-based formats
            if file_type == 'zip':
                # Check for DOCX/XLSX by looking at internal structure
                if b'word/document.xml' in content[:8192]:
                    return 'docx'
                elif b'xl/workbook.xml' in content[:8192]:
                    return 'xlsx'
                return 'zip'
            return file_type
    
    # Check for text files by looking for non-printable characters
    sample = content[:1024]
    try:
        sample.decode('utf-8')
        # If it decodes as UTF-8, it might be text
        # Check for JSON
        if content.strip().startswith(b'{') or content.strip().startswith(b'['):
            return 'json'
        # Check for CSV (simple heuristic)
        if b',' in content and b'\n' in content:
            # Count commas vs newlines
            lines = content.split(b'\n')
            if len(lines) > 1:
                first_line_commas = lines[0].count(b',')
                if first_line_commas > 0 and first_line_commas < 50:
                    return 'csv'
        return 'txt'
    except UnicodeDecodeError:
        pass
    
    return None


def validate_file_content(
    content: bytes, 
    claimed_filename: str,
    allowed_extensions: list[str]
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate file content against claimed type.
    
    Args:
        content: File content bytes
        claimed_filename: Filename provided by user
        allowed_extensions: List of allowed file extensions
        
    Returns:
        Tuple of (is_valid, error_message, detected_type)
    """
    # Sanitize filename
    safe_filename = sanitize_filename(claimed_filename)
    
    # Get claimed extension
    _, claimed_ext = os.path.splitext(safe_filename.lower())
    claimed_ext = claimed_ext.lstrip('.')
    
    # Check if claimed extension is allowed
    if claimed_ext not in [ext.lstrip('.') for ext in allowed_extensions]:
        return False, f"File type '.{claimed_ext}' not allowed", None
    
    # Detect actual type from content
    detected_type = detect_file_type_from_content(content[:8192])
    
    if detected_type is None:
        return False, "Could not determine file type from content", None
    
    # Validate that detected type matches claimed type
    type_mapping = {
        'jpeg': ['jpg', 'jpeg'],
        'zip': ['docx', 'xlsx'],
    }
    
    valid_extensions = type_mapping.get(detected_type, [detected_type])
    
    if claimed_ext not in valid_extensions:
        # Extension spoofing detected
        logger.warning(
            f"File type mismatch: claimed '{claimed_ext}' but detected '{detected_type}'"
        )
        return (
            False, 
            f"File content does not match extension. Detected: {detected_type}, Claimed: {claimed_ext}",
            detected_type
        )
    
    return True, "", detected_type


def get_safe_filename(original_filename: str) -> str:
    """
    Get a safe filename for display/storage.
    
    Args:
        original_filename: Original filename from user
        
    Returns:
        Sanitized filename
    """
    return sanitize_filename(original_filename)