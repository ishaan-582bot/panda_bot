"""
Session models for Panda.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
import uuid


class SessionStatus(str, Enum):
    """Session status enumeration."""
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class SessionConfig(BaseModel):
    """Configuration for a session."""
    model_config = ConfigDict(validate_assignment=True)
    
    max_file_size_mb: int = 50
    max_total_size_mb: int = 100
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100
    max_chunks_per_query: int = 5
    session_timeout_minutes: int = 30
    temperature: float = 0.1
    allowed_extensions: List[str] = Field(
        default=[".pdf", ".docx", ".txt", ".csv", ".json", ".png", ".jpg", ".jpeg"]
    )


class Session(BaseModel):
    """Represents a user session with isolated data."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(minutes=30)
    )
    config: SessionConfig = Field(default_factory=SessionConfig)
    
    # Runtime data (not persisted)
    documents: Dict[str, Any] = Field(default_factory=dict)
    vector_store: Optional[Any] = None
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)
    total_tokens_used: int = 0
    
    # Conversation memory
    conversation_summary: Optional[str] = None  # Running summary of older conversations
    summary_turns_count: int = 0  # Number of turns included in summary
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at
    
    def update_activity(self):
        """Update last activity timestamp and extend expiration."""
        self.last_activity = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(
            minutes=self.config.session_timeout_minutes
        )
    
    def get_time_remaining(self) -> int:
        """Get remaining time in seconds."""
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))
    
    def add_document(self, doc_id: str, document: Any):
        """Add a document to the session."""
        self.documents[doc_id] = document
        self.update_activity()
    
    def get_total_size_mb(self) -> float:
        """Get total size of all uploaded documents in MB."""
        total = 0.0
        for doc in self.documents.values():
            if hasattr(doc, 'size_bytes'):
                total += doc.size_bytes
        return total / (1024 * 1024)
    
    def get_document_count(self) -> int:
        """Get number of uploaded documents."""
        return len(self.documents)
    
    def add_chat_message(self, role: str, content: str):
        """Add a message to chat history."""
        self.chat_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.update_activity()
    
    def get_recent_chat_history(self, max_turns: int = 7) -> List[Dict[str, str]]:
        """
        Get recent chat history for context.
        Returns last N conversation turns (user + assistant pairs).
        """
        # Filter to just role and content for LLM context
        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.chat_history
        ]
        
        # Calculate turns (each turn = user + assistant)
        # We want the last N complete turns
        max_messages = max_turns * 2
        
        if len(messages) <= max_messages:
            return messages
        
        return messages[-max_messages:]
    
    def should_summarize(self, threshold: int = 10) -> bool:
        """Check if conversation should be summarized."""
        # Count turns since last summary
        turns_since_summary = (len(self.chat_history) - self.summary_turns_count) // 2
        return turns_since_summary >= threshold
    
    def update_conversation_summary(self, summary: str):
        """Update the conversation summary."""
        self.conversation_summary = summary
        self.summary_turns_count = len(self.chat_history)
    
    def get_conversation_context(self, max_turns: int = 7) -> Dict[str, Any]:
        """
        Get full conversation context including summary and recent history.
        Returns dict with 'summary' and 'recent_history' keys.
        """
        return {
            "summary": self.conversation_summary,
            "recent_history": self.get_recent_chat_history(max_turns),
            "total_turns": len(self.chat_history) // 2
        }
    
    def to_status_dict(self) -> Dict[str, Any]:
        """Convert session to status response."""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "time_remaining_seconds": self.get_time_remaining(),
            "documents_loaded": self.get_document_count(),
            "total_size_mb": round(self.get_total_size_mb(), 2),
            "total_tokens_used": self.total_tokens_used,
            "chat_turns": len(self.chat_history) // 2,
            "has_conversation_summary": self.conversation_summary is not None,
            "config": {
                "max_file_size_mb": self.config.max_file_size_mb,
                "max_total_size_mb": self.config.max_total_size_mb,
                "session_timeout_minutes": self.config.session_timeout_minutes,
            }
        }
    
    def to_export_dict(self) -> Dict[str, Any]:
        """Export session data for persistence."""
        from ..models.document import Document
        
        # Export documents (without embeddings to save space)
        documents_export = []
        for doc in self.documents.values():
            if isinstance(doc, Document):
                doc_dict = doc.to_summary_dict()
                # Include chunks text but not embeddings
                doc_dict["chunks"] = [
                    {
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "token_count": chunk.token_count,
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": chunk.total_chunks,
                        "metadata": {
                            "source_file": chunk.metadata.source_file,
                            "file_type": chunk.metadata.file_type,
                            "page_number": chunk.metadata.page_number,
                            "section_header": chunk.metadata.section_header,
                        }
                    }
                    for chunk in doc.chunks
                ]
                documents_export.append(doc_dict)
        
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "config": self.config.model_dump(),
            "documents": documents_export,
            "chat_history": self.chat_history,
            "conversation_summary": self.conversation_summary,
            "summary_turns_count": self.summary_turns_count,
            "total_tokens_used": self.total_tokens_used,
            "exported_at": datetime.utcnow().isoformat()
        }
