"""
Retrieval service for Panda.
Retrieves relevant document chunks using hybrid search:
- FAISS vector similarity
- BM25 keyword scoring
Uses FAISS for efficient in-memory vector search.
Thread-safe with per-session locks.
"""

import asyncio
import logging
import re
from typing import List, Optional, Tuple, Dict
from collections import defaultdict

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from ..core.config import get_settings
from ..core.embedding_registry import embedding_registry
from ..models.document import DocumentChunk
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    Service for retrieving relevant document chunks using hybrid search.
    Combines FAISS vector similarity with BM25 keyword scoring.
    Thread-safe with per-session locking for FAISS operations.
    """
    
    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.settings = get_settings()
        self.embedding_service = embedding_service or EmbeddingService()
        
        # Get dimension from locked registry
        self.dimension = embedding_registry.dimension
        
        # FAISS index
        self.index: Optional[faiss.Index] = None
        self.chunks: List[DocumentChunk] = []
        
        # BM25 index - incremental update support
        self.bm25: Optional[BM25Okapi] = None
        self.tokenized_chunks: List[List[str]] = []
        self.bm25_doc_freqs: Dict[str, int] = defaultdict(int)
        self.total_docs: int = 0
        
        # Chunk ID to index mapping for hybrid scoring
        self.chunk_id_to_index: Dict[str, int] = {}
        
        # Thread-safety lock for FAISS operations
        self._lock: asyncio.Lock = asyncio.Lock()
        
        logger.info(f"RetrievalService initialized with dimension: {self.dimension}")
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for BM25."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.split()
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'and', 'but', 'or', 'yet', 'so', 'if',
                      'because', 'although', 'though', 'while', 'where', 'when',
                      'that', 'which', 'who', 'whom', 'whose', 'what', 'this',
                      'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
        return [t for t in tokens if t not in stop_words and len(t) > 2]
    
    def _update_bm25_incrementally(self, new_chunks: List[DocumentChunk]) -> None:
        """
        Incrementally update BM25 index without full rebuild.
        Much faster for large sessions.
        """
        if not new_chunks:
            return
        
        # Tokenize new chunks
        new_tokenized = [self._tokenize_text(chunk.text) for chunk in new_chunks]
        
        # Add to existing tokenized chunks
        start_idx = len(self.tokenized_chunks)
        self.tokenized_chunks.extend(new_tokenized)
        
        # Update document frequencies
        for tokens in new_tokenized:
            seen = set()
            for token in tokens:
                if token not in seen:
                    self.bm25_doc_freqs[token] += 1
                    seen.add(token)
        
        self.total_docs = len(self.tokenized_chunks)
        
        # Build chunk ID mapping
        for i, chunk in enumerate(new_chunks):
            self.chunk_id_to_index[chunk.chunk_id] = start_idx + i
        
        # Rebuild BM25 with updated corpus (BM25Okapi doesn't support true incremental updates)
        # But we avoid re-tokenizing existing chunks
        self.bm25 = BM25Okapi(self.tokenized_chunks)
        
        logger.debug(f"Incrementally updated BM25 with {len(new_chunks)} new documents")
    
    async def _ensure_embeddings(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """
        Ensure all chunks have embeddings, generating if needed.
        Pure async pattern - no event loop detection.
        """
        chunks_without_embeddings = [c for c in chunks if c.embedding is None]
        
        if chunks_without_embeddings:
            logger.info(f"Generating embeddings for {len(chunks_without_embeddings)} chunks")
            await self.embedding_service.generate_embeddings(chunks_without_embeddings)
        
        return chunks
    
    async def build_index(self, chunks: List[DocumentChunk]) -> bool:
        """
        Build FAISS and BM25 indexes from document chunks.
        Thread-safe with locking.
        
        Args:
            chunks: List of DocumentChunk objects with embeddings
            
        Returns:
            True if index was built successfully
        """
        if not chunks:
            logger.warning("No chunks provided to build index")
            return False
        
        async with self._lock:
            # Ensure embeddings
            chunks = await self._ensure_embeddings(chunks)
            
            # Filter chunks with embeddings
            chunks_with_embeddings = [c for c in chunks if c.embedding is not None]
            
            if not chunks_with_embeddings:
                logger.warning("No chunks have embeddings")
                return False
            
            # Validate dimensions match
            for chunk in chunks_with_embeddings:
                if len(chunk.embedding) != self.dimension:
                    logger.error(
                        f"Dimension mismatch: expected {self.dimension}, "
                        f"got {len(chunk.embedding)} for chunk {chunk.chunk_id}"
                    )
                    raise ValueError(
                        f"Embedding dimension mismatch. Expected {self.dimension}, "
                        f"got {len(chunk.embedding)}. This usually means the embedding "
                        f"provider changed mid-session."
                    )
            
            # Create embeddings matrix
            embeddings = np.array([c.embedding for c in chunks_with_embeddings]).astype("float32")
            
            # Normalize for cosine similarity
            faiss.normalize_L2(embeddings)
            
            # Create FAISS index
            self.index = faiss.IndexFlatIP(self.dimension)
            
            # Add vectors to index
            self.index.add(embeddings)
            
            # Store chunks
            self.chunks = chunks_with_embeddings
            
            # Build BM25 index incrementally
            self._update_bm25_incrementally(chunks_with_embeddings)
            
            logger.info(f"Built hybrid index with {len(chunks_with_embeddings)} vectors")
            return True
    
    async def add_document_chunks(self, new_chunks: List[DocumentChunk]) -> bool:
        """
        Incrementally add new document chunks to existing indexes.
        Thread-safe with locking.
        
        Args:
            new_chunks: List of new DocumentChunk objects with embeddings
            
        Returns:
            True if chunks were added successfully
        """
        if not new_chunks:
            return True
        
        async with self._lock:
            # Ensure embeddings
            new_chunks = await self._ensure_embeddings(new_chunks)
            
            # Filter to only chunks with embeddings
            chunks_with_embeddings = [c for c in new_chunks if c.embedding is not None]
            
            if not chunks_with_embeddings:
                logger.warning("No new chunks have embeddings")
                return False
            
            # Validate dimensions
            for chunk in chunks_with_embeddings:
                if len(chunk.embedding) != self.dimension:
                    logger.error(
                        f"Dimension mismatch: expected {self.dimension}, "
                        f"got {len(chunk.embedding)} for chunk {chunk.chunk_id}"
                    )
                    raise ValueError(f"Embedding dimension mismatch in add_document_chunks")
            
            # If no index exists yet, build one
            if self.index is None:
                return await self.build_index(chunks_with_embeddings)
            
            # Add to FAISS index
            embeddings = np.array([c.embedding for c in chunks_with_embeddings]).astype("float32")
            faiss.normalize_L2(embeddings)
            self.index.add(embeddings)
            
            # Store chunks
            start_idx = len(self.chunks)
            self.chunks.extend(chunks_with_embeddings)
            
            # Update BM25 incrementally
            self._update_bm25_incrementally(chunks_with_embeddings)
            
            logger.info(f"Incrementally added {len(chunks_with_embeddings)} vectors (total: {len(self.chunks)})")
            return True
    
    async def search(
        self, 
        query: str, 
        top_k: Optional[int] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Search for relevant chunks using hybrid search.
        Thread-safe with locking for FAISS operations.
        
        Args:
            query: The search query
            top_k: Number of results to return (default from config)
            
        Returns:
            List of (chunk, score) tuples sorted by relevance
        """
        async with self._lock:
            if self.index is None or not self.chunks:
                logger.warning("No index available for search")
                return []
            
            top_k = top_k or self.settings.MAX_CHUNKS_PER_QUERY
            
            # Vector search with FAISS
            vector_results = await self._vector_search(query, top_k * 2)
            
            # Keyword search with BM25
            keyword_results = self._keyword_search(query, top_k * 2)
            
            # Combine results
            if self.settings.ENABLE_HYBRID_SEARCH and self.bm25 is not None:
                combined_results = self._combine_hybrid_results(
                    vector_results, keyword_results, top_k
                )
            else:
                combined_results = vector_results[:top_k]
            
            logger.debug(f"Hybrid search found {len(combined_results)} results for: {query[:50]}...")
            return combined_results
    
    async def _vector_search(
        self, 
        query: str, 
        top_k: int
    ) -> List[Tuple[DocumentChunk, float]]:
        """Search using FAISS vector similarity."""
        # Generate query embedding
        query_embedding = await self.embedding_service.generate_query_embedding(query)
        
        # Validate dimension
        if len(query_embedding) != self.dimension:
            logger.error(
                f"Query embedding dimension mismatch: expected {self.dimension}, "
                f"got {len(query_embedding)}"
            )
            raise ValueError("Query embedding dimension mismatch")
        
        query_vector = np.array([query_embedding]).astype("float32")
        faiss.normalize_L2(query_vector)
        
        # Search index
        scores, indices = self.index.search(query_vector, min(top_k, len(self.chunks)))
        
        # Retrieve chunks
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.chunks):
                chunk = self.chunks[idx]
                results.append((chunk, float(score)))
        
        return results
    
    def _keyword_search(self, query: str, top_k: int) -> List[Tuple[DocumentChunk, float]]:
        """Search using BM25 keyword scoring."""
        if self.bm25 is None or not self.tokenized_chunks:
            return []
        
        tokenized_query = self._tokenize_text(query)
        
        if not tokenized_query:
            return []
        
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk = self.chunks[idx]
                normalized_score = min(1.0, scores[idx] / 10.0)
                results.append((chunk, normalized_score))
        
        return results
    
    def _combine_hybrid_results(
        self,
        vector_results: List[Tuple[DocumentChunk, float]],
        keyword_results: List[Tuple[DocumentChunk, float]],
        top_k: int
    ) -> List[Tuple[DocumentChunk, float]]:
        """Combine vector and keyword results using weighted scoring."""
        vector_weight = 1.0 - self.settings.BM25_WEIGHT
        keyword_weight = self.settings.BM25_WEIGHT
        
        vector_scores = {chunk.chunk_id: score for chunk, score in vector_results}
        keyword_scores = {chunk.chunk_id: score for chunk, score in keyword_results}
        
        all_chunk_ids = set(vector_scores.keys()) | set(keyword_scores.keys())
        
        chunk_lookup = {chunk.chunk_id: chunk for chunk, _ in vector_results}
        chunk_lookup.update({chunk.chunk_id: chunk for chunk, _ in keyword_results})
        
        combined = []
        for chunk_id in all_chunk_ids:
            v_score = vector_scores.get(chunk_id, 0.0)
            k_score = keyword_scores.get(chunk_id, 0.0)
            combined_score = (vector_weight * v_score) + (keyword_weight * k_score)
            
            if chunk_id in chunk_lookup:
                combined.append((chunk_lookup[chunk_id], combined_score))
        
        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_k]
    
    async def search_with_threshold(
        self, 
        query: str, 
        top_k: Optional[int] = None,
        min_score: Optional[float] = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Search with minimum relevance threshold.
        Uses dynamic threshold calibration based on score distribution.
        """
        min_score = min_score or self.settings.RELEVANCE_THRESHOLD
        
        results = await self.search(query, top_k)
        
        if not results:
            return []
        
        # Dynamic threshold calibration
        all_scores = [score for _, score in results]
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
            max_score = max(all_scores)
            
            # If top score is significantly below threshold but there's a score gap
            if results[0][1] < min_score and len(results) > 1:
                score_gap = results[0][1] - results[1][1] if len(results) > 1 else 0
                
                # If there's a clear winner, lower threshold temporarily
                if score_gap > 0.1:
                    adjusted_threshold = min_score * 0.7
                    filtered = [(chunk, score) for chunk, score in results if score >= adjusted_threshold]
                    logger.debug(f"Adjusted threshold to {adjusted_threshold:.2f} due to score gap")
                    return filtered
        
        # Standard threshold filtering
        if results and results[0][1] < min_score:
            logger.info(f"Top result score {results[0][1]:.2f} below threshold {min_score}")
            return []
        
        filtered = [(chunk, score) for chunk, score in results if score >= min_score]
        return filtered
    
    def get_index_stats(self) -> dict:
        """Get statistics about the current index."""
        if self.index is None:
            return {
                "total_vectors": 0,
                "is_trained": False,
                "dimension": self.dimension,
                "bm25_enabled": False
            }
        
        return {
            "total_vectors": self.index.ntotal,
            "is_trained": self.index.is_trained,
            "dimension": self.dimension,
            "bm25_enabled": self.bm25 is not None,
            "bm25_documents": len(self.tokenized_chunks) if self.bm25 else 0
        }
    
    async def clear(self) -> None:
        """Clear the index and all stored data."""
        async with self._lock:
            if self.index is not None:
                del self.index
                self.index = None
            
            self.bm25 = None
            self.tokenized_chunks = []
            self.chunk_id_to_index = {}
            self.bm25_doc_freqs.clear()
            self.total_docs = 0
            
            for chunk in self.chunks:
                if chunk.embedding is not None:
                    for i in range(len(chunk.embedding)):
                        chunk.embedding[i] = 0.0
                    chunk.embedding = None
            
            self.chunks = []
            logger.info("RetrievalService index cleared")
