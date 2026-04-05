"""
Model Cache - Global singleton cache for ML models.
Prevents reloading models for each session, reducing memory and startup time.
"""

import logging
import threading
from typing import Optional, Any

logger = logging.getLogger(__name__)


class ModelCache:
    """
    Thread-safe singleton cache for ML models.
    Models are loaded once and reused across all sessions.
    """
    
    _instance: Optional['ModelCache'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'ModelCache':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._models: dict = {}
                    cls._instance._loading: dict = {}
        return cls._instance
    
    def get_or_load(self, model_name: str, loader_fn) -> Any:
        """
        Get a model from cache or load it if not present.
        
        Args:
            model_name: Unique identifier for the model
            loader_fn: Function that loads and returns the model
            
        Returns:
            The cached or newly loaded model
        """
        # Fast path: check if already loaded
        if model_name in self._models:
            return self._models[model_name]
        
        # Slow path: load with locking
        with self._lock:
            # Double-check after acquiring lock
            if model_name in self._models:
                return self._models[model_name]
            
            # Check if another thread is loading
            if model_name in self._loading:
                # Wait for loading to complete
                while model_name in self._loading:
                    self._lock.release()
                    import time
                    time.sleep(0.01)
                    self._lock.acquire()
                return self._models[model_name]
            
            # Mark as loading
            self._loading[model_name] = True
        
        try:
            # Load the model (outside lock to allow concurrent loading of different models)
            logger.info(f"Loading model: {model_name}")
            model = loader_fn()
            
            with self._lock:
                self._models[model_name] = model
                del self._loading[model_name]
            
            logger.info(f"Model loaded and cached: {model_name}")
            return model
            
        except Exception as e:
            with self._lock:
                if model_name in self._loading:
                    del self._loading[model_name]
            raise
    
    def get(self, model_name: str) -> Optional[Any]:
        """Get a model from cache if present."""
        return self._models.get(model_name)
    
    def clear(self, model_name: Optional[str] = None):
        """Clear cached model(s)."""
        with self._lock:
            if model_name:
                if model_name in self._models:
                    del self._models[model_name]
                    logger.info(f"Cleared model from cache: {model_name}")
            else:
                self._models.clear()
                logger.info("Cleared all models from cache")
    
    def list_cached(self) -> list:
        """List all cached model names."""
        return list(self._models.keys())


# Global model cache instance
model_cache = ModelCache()


# Tiktoken encoder cache
tiktoken_cache: dict = {}
tiktoken_lock = threading.Lock()


def get_tiktoken_encoder(encoding_name: str = "cl100k_base"):
    """
    Get a cached tiktoken encoder.
    Prevents creating multiple encoder instances (5MB each).
    """
    global tiktoken_cache
    
    if encoding_name not in tiktoken_cache:
        with tiktoken_lock:
            if encoding_name not in tiktoken_cache:
                import tiktoken
                tiktoken_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
                logger.info(f"Cached tiktoken encoder: {encoding_name}")
    
    return tiktoken_cache[encoding_name]
