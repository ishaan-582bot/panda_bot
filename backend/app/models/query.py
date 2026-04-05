from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """Source attribution for a response"""
    file: str
    page: Optional[int] = None
    section: Optional[str] = None
    text: str
    chunk_index: int = 0
    relevance_score: float = 0.0


class QueryRequest(BaseModel):
    """Request model for querying the chatbot"""
    question: str = Field(..., min_length=1, max_length=2000)
    max_chunks: Optional[int] = None
    temperature: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What was Q3 revenue?",
                "max_chunks": 5,
                "temperature": 0.1
            }
        }


class QueryResponse(BaseModel):
    """Response model for chatbot queries"""
    answer: str
    sources: List[SourceCitation]
    confidence: Literal["high", "medium", "low"]
    session_id: str
    tokens_used: int
    processing_time_ms: float
    query: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Q3 2024 revenue was $4.2 million",
                "sources": [
                    {
                        "file": "annual_report.pdf",
                        "page": 7,
                        "section": "Financial Results",
                        "text": "Q3 2024 revenue increased to $4.2 million...",
                        "chunk_index": 3,
                        "relevance_score": 0.92
                    }
                ],
                "confidence": "high",
                "session_id": "abc-123",
                "tokens_used": 245,
                "processing_time_ms": 1250.5,
                "query": "What was Q3 revenue?"
            }
        }