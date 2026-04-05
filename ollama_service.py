"""
Ollama service for Panda.
Provides local LLM and embedding capabilities via Ollama API.
Optimized for 8GB RAM with 3B parameter models.
Includes exponential backoff retry and prompt compression.
"""

import asyncio
import logging
from typing import List, Optional, Tuple, Dict, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import get_settings
from ..core.model_cache import get_tiktoken_encoder
from ..models.document import DocumentChunk
from ..models.query import SourceCitation

logger = logging.getLogger(__name__)


class OllamaService:
    """
    Service for generating responses using local Ollama LLM.
    Uses llama3.2:3b or phi4 (3B parameters) for 8GB RAM compatibility.
    Includes exponential backoff retry and prompt compression.
    """
    
    # Compressed system prompt for 3B models (under 200 tokens)
    COMPRESSED_SYSTEM_PROMPT = """Answer ONLY using the provided context. If the answer is not in the context, say "This information is not present in your uploaded data." Cite sources as [Source: filename, Page X]."""
    
    # Maximum context length for 3B models (in characters, not tokens)
    MAX_CONTEXT_CHARS = 6000  # Approx 2000 tokens
    MAX_CONVERSATION_CHARS = 1500  # Approx 500 tokens
    MAX_CHUNK_CHARS = 800  # Per chunk limit
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip('/')
        self.llm_model = self.settings.OLLAMA_LLM_MODEL
        self.embedding_model = self.settings.OLLAMA_EMBEDDING_MODEL
        self.client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=300.0)
        return self.client
    
    async def check_availability(self) -> bool:
        """Check if Ollama is running and responsive."""
        if self._available is not None:
            return self._available
            
        if not self.settings.OLLAMA_ENABLED:
            self._available = False
            return False
        
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                models = [m.get('name', '') for m in data.get('models', [])]
                
                llm_available = any(self.llm_model in m for m in models)
                embedding_available = any(self.embedding_model in m for m in models)
                
                if llm_available:
                    logger.info(f"Ollama available. LLM: {self.llm_model}, Embedding: {embedding_available}")
                    self._available = True
                    return True
                else:
                    logger.warning(f"Ollama running but {self.llm_model} not found. Available: {models}")
                    self._available = False
                    return False
            else:
                logger.warning(f"Ollama returned status {response.status_code}")
                self._available = False
                return False
        except httpx.ConnectError:
            logger.info("Ollama not available at " + self.base_url)
            self._available = False
            return False
        except Exception as e:
            logger.warning(f"Error checking Ollama availability: {e}")
            self._available = False
            return False
    
    def _compress_context(self, context_chunks: List[Tuple[DocumentChunk, float]]) -> str:
        """
        Compress context to fit within 3B model limits.
        Truncates chunks while preserving most relevant content.
        """
        if not context_chunks:
            return ""
        
        compressed_parts = []
        remaining_chars = self.MAX_CONTEXT_CHARS
        
        for i, (chunk, score) in enumerate(context_chunks, 1):
            meta = chunk.metadata
            source_info = f"[{i}] {meta.source_file}"
            if meta.page_number:
                source_info += f", P{meta.page_number}"
            
            # Calculate available space for this chunk
            header_len = len(source_info) + 20  # Buffer for formatting
            available = min(self.MAX_CHUNK_CHARS, remaining_chars - header_len)
            
            if available <= 0:
                break
            
            # Truncate chunk text if needed
            chunk_text = chunk.text
            if len(chunk_text) > available:
                # Try to truncate at sentence boundary
                truncated = chunk_text[:available]
                last_period = truncated.rfind('.')
                if last_period > available * 0.7:  # If we can keep 70%
                    truncated = truncated[:last_period + 1]
                chunk_text = truncated + "..."
            
            compressed_parts.append(f"{source_info}\n{chunk_text}")
            remaining_chars -= (header_len + len(chunk_text))
        
        return "\n\n".join(compressed_parts)
    
    def _compress_conversation_history(
        self,
        chat_history: Optional[List[Dict[str, str]]],
        conversation_summary: Optional[str]
    ) -> str:
        """
        Compress conversation history to fit within limits.
        Prioritizes summary over individual messages.
        """
        parts = []
        remaining = self.MAX_CONVERSATION_CHARS
        
        if conversation_summary:
            summary_text = f"Summary: {conversation_summary}"
            if len(summary_text) > remaining:
                summary_text = summary_text[:remaining - 3] + "..."
            parts.append(summary_text)
            remaining -= len(summary_text)
        
        if chat_history and remaining > 100:
            parts.append("Recent:")
            remaining -= 10
            
            for msg in reversed(chat_history[-4:]):  # Last 4 messages max
                role = msg.get('role', 'user')[0].upper()  # U or A
                content = msg.get('content', '')
                
                # Truncate long messages
                if len(content) > 200:
                    content = content[:197] + "..."
                
                msg_text = f"{role}: {content}"
                if len(msg_text) > remaining:
                    break
                
                parts.append(msg_text)
                remaining -= len(msg_text)
        
        return "\n".join(parts)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=lambda e: isinstance(e, (httpx.HTTPError, httpx.ConnectError))
    )
    async def generate_response(
        self,
        query: str,
        context_chunks: List[Tuple[DocumentChunk, float]],
        temperature: Optional[float] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        conversation_summary: Optional[str] = None
    ) -> Tuple[str, List[SourceCitation], str]:
        """
        Generate a response using Ollama LLM with prompt compression.
        Includes exponential backoff retry.
        """
        if not await self.check_availability():
            raise RuntimeError("Ollama not available")
        
        if not context_chunks:
            return (
                "This information is not present in your uploaded data.",
                [],
                "low"
            )
        
        # Compress context and conversation
        context_str = self._compress_context(context_chunks)
        conversation_str = self._compress_conversation_history(
            chat_history, conversation_summary
        )
        
        # Build compressed prompt
        system_prompt = self.COMPRESSED_SYSTEM_PROMPT
        if conversation_str:
            system_prompt += f"\n\n{conversation_str}"
        
        user_prompt = f"Context:\n{context_str}\n\nQ: {query}\nA:"
        
        temp = temperature or self.settings.LLM_TEMPERATURE
        
        try:
            client = await self._get_client()
            
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                    "options": {
                        "temperature": temp,
                        "num_predict": self.settings.LLM_MAX_TOKENS,
                        "top_p": 0.1,
                        "top_k": 40,
                    }
                },
                timeout=300.0
            )
            
            response.raise_for_status()
            data = response.json()
            
            answer = data.get('response', '').strip()
            
            sources = self._extract_sources(context_chunks)
            confidence = self._calculate_confidence(context_chunks)
            
            logger.info(
                f"Generated Ollama response for query: {query[:50]}... "
                f"Confidence: {confidence}, Model: {self.llm_model}"
            )
            
            return answer, sources, confidence
            
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=lambda e: isinstance(e, (httpx.HTTPError, httpx.ConnectError))
    )
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Ollama with exponential backoff retry.
        """
        if not await self.check_availability():
            raise RuntimeError("Ollama not available")
        
        embeddings = []
        client = await self._get_client()
        
        for text in texts:
            try:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.embedding_model,
                        "prompt": text
                    },
                    timeout=60.0
                )
                
                response.raise_for_status()
                data = response.json()
                embedding = data.get('embedding', [])
                
                if embedding:
                    embeddings.append(embedding)
                else:
                    logger.warning("Empty embedding received from Ollama")
                    embeddings.append([0.0] * 768)
                    
            except Exception as e:
                logger.error(f"Ollama embedding failed: {e}")
                raise
        
        logger.info(f"Generated {len(embeddings)} embeddings using Ollama/{self.embedding_model}")
        return embeddings
    
    async def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for a query string."""
        embeddings = await self.generate_embeddings([query])
        return embeddings[0] if embeddings else []
    
    async def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """Summarize a conversation using the local LLM."""
        if not await self.check_availability():
            return ""
        
        # Limit messages to summarize
        messages = messages[-20:]  # Last 20 messages max
        
        conversation_text = "\n".join([
            f"{msg.get('role', 'user')[0].upper()}: {msg.get('content', '')[:100]}"
            for msg in messages
        ])
        
        prompt = f"Summarize:\n{conversation_text}\nSummary:"
        
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": self.settings.MAX_SUMMARY_TOKENS,
                    }
                },
                timeout=120.0
            )
            
            response.raise_for_status()
            data = response.json()
            return data.get('response', '').strip()
            
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            return ""
    
    def _extract_sources(self, context_chunks: List[Tuple[DocumentChunk, float]]) -> List[SourceCitation]:
        """Extract source citations from chunks."""
        sources = []
        
        for chunk, score in context_chunks:
            meta = chunk.metadata
            source = SourceCitation(
                file=meta.source_file,
                page=meta.page_number,
                section=meta.section_header,
                text=chunk.text[:300] + "..." if len(chunk.text) > 300 else chunk.text,
                chunk_index=chunk.chunk_index,
                relevance_score=round(score, 3)
            )
            sources.append(source)
        
        return sources
    
    def _calculate_confidence(
        self, 
        context_chunks: List[Tuple[DocumentChunk, float]]
    ) -> str:
        """Calculate confidence level based on retrieval scores."""
        if not context_chunks:
            return "low"
        
        avg_score = sum(score for _, score in context_chunks) / len(context_chunks)
        
        if avg_score > 0.7:
            return "high"
        elif avg_score > 0.5:
            return "medium"
        
        return "low"
    
    async def close(self):
        """Close the HTTP client."""
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None
