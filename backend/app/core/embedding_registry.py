"""
Embedding Registry - Manages embedding dimensions and provider selection.
Ensures consistent dimensions across sessions to prevent FAISS crashes.
"""

import logging
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class EmbeddingProvider(str, Enum):
    """Embedding provider types."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    LOCAL = "local"


class EmbeddingRegistry:
    """
    Singleton registry that manages embedding configuration.
    Once initialized, the dimension is locked for the lifetime of the application.
    This prevents FAISS dimension mismatch crashes.
    """
    
    _instance: Optional['EmbeddingRegistry'] = None
    _initialized: bool = False
    
    # Dimension constants
    OPENAI_DIMENSION = 1536
    OLLAMA_DIMENSION = 768  # nomic-embed-text
    LOCAL_DIMENSION = 384   # all-MiniLM-L6-v2
    
    def __new__(cls) -> 'EmbeddingRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._dimension: Optional[int] = None
            cls._instance._provider: Optional[EmbeddingProvider] = None
            cls._instance._locked: bool = False
        return cls._instance
    
    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize the registry by detecting available providers.
        Once initialized, the dimension is locked.
        
        Priority: OpenAI > Ollama > Local
        
        Returns:
            Dict with provider, dimension, and status
        """
        if self._locked:
            return {
                "provider": self._provider.value,
                "dimension": self._dimension,
                "locked": True
            }
        
        from ..core.config import get_settings
        settings = get_settings()
        
        # Priority 1: OpenAI (if API key available)
        if settings.OPENAI_API_KEY:
            self._provider = EmbeddingProvider.OPENAI
            self._dimension = self.OPENAI_DIMENSION
            self._locked = True
            logger.info(f"EmbeddingRegistry locked to OpenAI with dimension {self._dimension}")
            return {
                "provider": self._provider.value,
                "dimension": self._dimension,
                "locked": True
            }
        
        # Priority 2: Ollama (if available)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get('name', '') for m in data.get('models', [])]
                    if any(settings.OLLAMA_EMBEDDING_MODEL in m for m in models):
                        self._provider = EmbeddingProvider.OLLAMA
                        self._dimension = self.OLLAMA_DIMENSION
                        self._locked = True
                        logger.info(f"EmbeddingRegistry locked to Ollama with dimension {self._dimension}")
                        return {
                            "provider": self._provider.value,
                            "dimension": self._dimension,
                            "locked": True
                        }
        except Exception as e:
            logger.debug(f"Ollama not available during registry init: {e}")
        
        # Priority 3: Local (fallback)
        self._provider = EmbeddingProvider.LOCAL
        self._dimension = self.LOCAL_DIMENSION
        self._locked = True
        logger.info(f"EmbeddingRegistry locked to Local with dimension {self._dimension}")
        return {
            "provider": self._provider.value,
            "dimension": self._dimension,
            "locked": True
        }
    
    @property
    def dimension(self) -> int:
        """Get the locked dimension. Raises if not initialized."""
        if self._dimension is None:
            raise RuntimeError("EmbeddingRegistry not initialized. Call initialize() first.")
        return self._dimension
    
    @property
    def provider(self) -> EmbeddingProvider:
        """Get the locked provider. Raises if not initialized."""
        if self._provider is None:
            raise RuntimeError("EmbeddingRegistry not initialized. Call initialize() first.")
        return self._provider
    
    @property
    def is_locked(self) -> bool:
        """Check if the registry is locked."""
        return self._locked
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """Get current embedding configuration."""
        return {
            "provider": self._provider.value if self._provider else None,
            "dimension": self._dimension,
            "locked": self._locked
        }


# Global registry instance
embedding_registry = EmbeddingRegistry()
