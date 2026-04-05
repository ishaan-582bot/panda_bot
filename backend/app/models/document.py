"""
Document models for Panda.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
import uuid


class DocumentMetadata(BaseModel):
    """Metadata for a document."""
    model_config = ConfigDict(validate_assignment=True)
    
    source_file: str
    file_type: str
    page_number: Optional[int] = None
    section_header: Optional[str] = None
    total_pages: Optional[int] = None
    author: Optional[str] = None
    created_date: Optional[str] = None
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    """A chunk of text extracted from a document."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    text: str
    token_count: int
    metadata: DocumentMetadata
    embedding: Optional[List[float]] = None
    chunk_index: int = 0
    total_chunks: int = 1


class Document(BaseModel):
    """Represents an uploaded document."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_type: str
    size_bytes: int
    content: Optional[str] = None
    chunks: List[DocumentChunk] = Field(default_factory=list)
    metadata: DocumentMetadata
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    processing_status: str = "pending"  # pending, processing, completed, error
    error_message: Optional[str] = None
    
    def get_total_tokens(self) -> int:
        """Get total token count across all chunks."""
        return sum(chunk.token_count for chunk in self.chunks)
    
    def get_chunk_count(self) -> int:
        """Get number of chunks."""
        return len(self.chunks)
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary response."""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "size_mb": round(self.size_bytes / (1024 * 1024), 2),
            "total_chunks": self.get_chunk_count(),
            "total_tokens": self.get_total_tokens(),
            "uploaded_at": self.uploaded_at.isoformat(),
            "processing_status": self.processing_status,
            "error": self.error_message
        }