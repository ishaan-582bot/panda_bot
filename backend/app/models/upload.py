from typing import Dict, List, Any
from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """Summary of a processed document"""
    document_id: str
    filename: str
    file_type: str
    size_mb: float
    total_chunks: int
    total_tokens: int
    processing_status: str


class UploadResponse(BaseModel):
    """Response for file upload"""
    session_id: str
    documents_processed: int
    documents: List[DocumentSummary]
    total_size_mb: float
    total_chunks: int
    total_tokens: int
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc-123",
                "documents_processed": 2,
                "documents": [
                    {
                        "document_id": "doc-1",
                        "filename": "annual_report.pdf",
                        "file_type": "pdf",
                        "size_mb": 2.5,
                        "total_chunks": 15,
                        "total_tokens": 7500,
                        "processing_status": "completed"
                    }
                ],
                "total_size_mb": 2.5,
                "total_chunks": 15,
                "total_tokens": 7500,
                "message": "Successfully processed 1 document(s)"
            }
        }