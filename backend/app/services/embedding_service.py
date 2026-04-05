"""
Embedding service for Panda.
Generates vector embeddings using OpenAI, Ollama, or local sentence-transformers.
Optimized for 8GB RAM with all-MiniLM-L6-v2 (80MB model).
Uses global dimension registry to prevent FAISS crashes.
"""

import asyncio
import logging
from typing import List, Optional

import numpy as np
from openai import AsyncOpenAI

from ..core.config import get_settings
from ..core.embedding_registry import embedding_registry, EmbeddingProvider
from ..core.model_cache import model_cache
from ..models.document import DocumentChunk

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating vector embeddings.
    Uses dimension registry to ensure consistency across sessions.
    Priority: OpenAI API > Ollama > Local sentence-transformers
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncOpenAI] = None
        self._ollama_service = None
        
        # Initialize OpenAI client if API key is available
        if self.settings.OPENAI_API_KEY:
            self.client = AsyncOpenAI(api_key=self.settings.OPENAI_API_KEY)
    
    def _get_ollama_service(self):
        """Lazy-load Ollama service."""
        if self._ollama_service is None:
            from .ollama_service import OllamaService
            self._ollama_service = OllamaService()
        return self._ollama_service
    
    def _load_local_model(self):
        """Load local sentence-transformers model using global cache."""
        model_name = self.settings.LOCAL_EMBEDDING_MODEL
        
        def loader():
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local embedding model: {model_name}...")
            model = SentenceTransformer(model_name)
            logger.info(f"Local embedding model loaded: {model_name}")
            return model
        
        return model_cache.get_or_load(f"embedding_{model_name}", loader)
    
    async def generate_embeddings(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Generate embeddings for a list of document chunks (async).
        Uses the locked provider from embedding registry.
        
        Args:
            chunks: List of DocumentChunk objects
            
        Returns:
            List of DocumentChunk objects with embeddings populated
        """
        if not chunks:
            return chunks
        
        # Get locked provider from registry
        provider = embedding_registry.provider
        
        if provider == EmbeddingProvider.OPENAI and self.client:
            return await self._generate_openai_embeddings(chunks)
        elif provider == EmbeddingProvider.OLLAMA:
            return await self._generate_ollama_embeddings(chunks)
        else:
            return await self._generate_local_embeddings(chunks)
    
    async def _generate_openai_embeddings(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Generate embeddings using OpenAI API (async)."""
        texts = [chunk.text for chunk in chunks]
        
        try:
            # Process in batches of 100 (OpenAI limit)
            batch_size = 100
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = await self.client.embeddings.create(
                    model=self.settings.EMBEDDING_MODEL,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                logger.debug(f"Generated embeddings for batch {i//batch_size + 1}")
            
            # Assign embeddings to chunks
            for chunk, embedding in zip(chunks, all_embeddings):
                chunk.embedding = embedding
            
            logger.info(f"Generated {len(chunks)} embeddings using OpenAI/{self.settings.EMBEDDING_MODEL}")
            return chunks
            
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            raise
    
    async def _generate_ollama_embeddings(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Generate embeddings using Ollama with concurrent processing."""
        texts = [chunk.text for chunk in chunks]
        
        # Process with limited concurrency (5 parallel requests)
        semaphore = asyncio.Semaphore(5)
        
        async def embed_single(text: str) -> List[float]:
            async with semaphore:
                return await self._get_ollama_service().generate_query_embedding(text)
        
        # Create tasks for all texts
        tasks = [embed_single(text) for text in texts]
        embeddings = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for errors
        for i, emb in enumerate(embeddings):
            if isinstance(emb, Exception):
                logger.error(f"Ollama embedding failed for chunk {i}: {emb}")
                raise emb
        
        # Assign embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        logger.info(f"Generated {len(chunks)} embeddings using Ollama/{self.settings.OLLAMA_EMBEDDING_MODEL}")
        return chunks
    
    async def _generate_local_embeddings(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Generate embeddings using local sentence-transformers model.
        Uses all-MiniLM-L6-v2 (80MB) for 8GB RAM compatibility.
        """
        texts = [chunk.text for chunk in chunks]
        
        # Get cached model
        model = self._load_local_model()
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(
                texts,
                convert_to_list=True,
                show_progress_bar=False,
                batch_size=32  # Small batches for memory efficiency
            )
        )
        
        # Assign embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        logger.info(f"Generated {len(chunks)} embeddings using local/{self.settings.LOCAL_EMBEDDING_MODEL}")
        return chunks
    
    async def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generate embedding for a query string (async).
        
        Args:
            query: The query text
            
        Returns:
            Embedding vector as list of floats
        """
        provider = embedding_registry.provider
        
        if provider == EmbeddingProvider.OPENAI and self.client:
            try:
                response = await self.client.embeddings.create(
                    model=self.settings.EMBEDDING_MODEL,
                    input=[query]
                )
                return response.data[0].embedding
            except Exception as e:
                logger.error(f"OpenAI query embedding failed: {e}")
                raise
        
        elif provider == EmbeddingProvider.OLLAMA:
            return await self._get_ollama_service().generate_query_embedding(query)
        
        else:
            # Local
            model = self._load_local_model()
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(
                    [query],
                    convert_to_list=True,
                    show_progress_bar=False
                )[0]
            )
            return embedding
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings from the locked registry."""
        return embedding_registry.dimension
