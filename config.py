"""
Application configuration settings.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App settings
    APP_NAME: str = "Panda API"
    DEBUG: bool = False
    
    # Session settings
    SESSION_TIMEOUT_MINUTES: int = 30
    MAX_FILE_SIZE_MB: int = 50
    MAX_TOTAL_SIZE_MB: int = 100
    
    # Chunking settings
    CHUNK_SIZE_TOKENS: int = 500
    CHUNK_OVERLAP_TOKENS: int = 100
    MAX_CHUNKS_PER_QUERY: int = 5
    
    # LLM settings - OpenAI
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2000
    
    # Ollama settings - Local LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2:3b"  # or "phi4" (3B parameters, fits in 8GB RAM)
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_ENABLED: bool = True  # Auto-detect Ollama on startup
    
    # Local embedding fallback
    LOCAL_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # 80MB, fits in 8GB RAM
    
    # Chat memory settings
    MAX_CHAT_HISTORY_TURNS: int = 7  # Last N conversation turns to include
    CONVERSATION_SUMMARY_THRESHOLD: int = 10  # Summarize after N turns
    MAX_SUMMARY_TOKENS: int = 500
    
    # RAG settings
    RELEVANCE_THRESHOLD: float = 0.7  # Minimum similarity score for responses
    ENABLE_HYBRID_SEARCH: bool = True  # Combine FAISS + BM25
    BM25_WEIGHT: float = 0.3  # Weight for BM25 in hybrid search (0-1)
    
    # Performance settings for 8GB RAM
    DOCUMENT_BATCH_SIZE: int = 3  # Process PDF pages in chunks
    MAX_CONCURRENT_REQUESTS: int = 3  # Request queue limit
    
    # Session persistence
    BACKUP_DIR: str = "backups"  # Directory for session exports
    ENABLE_SESSION_PERSISTENCE: bool = True
    
    # Vector store settings
    VECTOR_DIMENSION: int = 1536  # For text-embedding-3-small
    LOCAL_EMBEDDING_DIMENSION: int = 384  # For all-MiniLM-L6-v2
    
    # Security
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=[
            ".pdf", ".docx", ".txt", ".csv", ".json",
            ".png", ".jpg", ".jpeg", ".tiff", ".bmp"
        ]
    )
    
    # CORS - STRICT WHITELIST (security critical)
    # Default allows only localhost for development
    # In production, set this to your frontend domain(s)
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])
    
    # Rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 10
    RATE_LIMIT_SESSION_CREATION_PER_MINUTE: int = 5
    
    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Split by comma if provided as string
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
