"""
LLM service for Panda.
Generates responses using OpenAI, Ollama, or mock with chat memory support.
Includes prompt compression for 3B models.
"""

import logging
import re
from typing import List, Optional, Tuple, Dict, Any

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type
from openai import RateLimitError as OpenAIRateLimitError

from ..core.config import get_settings
from ..core.embedding_registry import embedding_registry
from ..core.model_cache import get_tiktoken_encoder
from ..models.document import DocumentChunk
from ..models.query import SourceCitation

logger = logging.getLogger(__name__)


class LLMService:
    """
    Service for generating responses using LLM with chat memory support.
    Auto-detects available providers: OpenAI > Ollama > Mock
    Includes prompt compression for small models.
    """
    
    # Compressed system prompt (under 200 tokens)
    COMPRESSED_SYSTEM_PROMPT = """Answer ONLY using the provided context. If the answer is not in the context, say "This information is not present in your uploaded data." Cite sources as [Source: filename, Page X]. Be concise."""
    
    # Context limits
    MAX_CONTEXT_CHARS = 6000
    MAX_CONVERSATION_CHARS = 1500
    MAX_CHUNK_CHARS = 800
    
    # External knowledge indicators
    EXTERNAL_KNOWLEDGE_PATTERNS = [
        r"\bwikipedia\b",
        r"\bgoogle\b",
        r"\baccording to (?!your|the (?:uploaded|provided|document))",
        r"\bresearch (?:shows|suggests|indicates) (?!in your|from your)",
        r"\bstudies (?:show|suggest|indicate) (?!in your|from your)",
    ]
    
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self._ollama_service = None
        self._provider: Optional[str] = None
        
        if self.settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.settings.OPENAI_API_KEY)
            self._provider = "openai"
            logger.info(f"LLMService initialized with OpenAI model: {self.settings.LLM_MODEL}")
        else:
            logger.info("No OpenAI API key. Will use Ollama or mock responses.")
    
    def _get_ollama_service(self):
        """Lazy-load Ollama service."""
        if self._ollama_service is None:
            from .ollama_service import OllamaService
            self._ollama_service = OllamaService()
        return self._ollama_service
    
    async def _get_provider(self) -> str:
        """Determine which provider to use."""
        if self._provider:
            return self._provider
        
        if await self._get_ollama_service().check_availability():
            self._provider = "ollama"
            return "ollama"
        
        self._provider = "mock"
        return "mock"
    
    def _compress_context(self, context_chunks: List[Tuple[DocumentChunk, float]]) -> str:
        """Compress context to fit within model limits."""
        if not context_chunks:
            return ""
        
        compressed_parts = []
        remaining_chars = self.MAX_CONTEXT_CHARS
        
        for i, (chunk, score) in enumerate(context_chunks, 1):
            meta = chunk.metadata
            source_info = f"[{i}] {meta.source_file}"
            if meta.page_number:
                source_info += f", P{meta.page_number}"
            
            header_len = len(source_info) + 20
            available = min(self.MAX_CHUNK_CHARS, remaining_chars - header_len)
            
            if available <= 0:
                break
            
            chunk_text = chunk.text
            if len(chunk_text) > available:
                truncated = chunk_text[:available]
                last_period = truncated.rfind('.')
                if last_period > available * 0.7:
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
        """Compress conversation history."""
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
            
            for msg in reversed(chat_history[-4:]):
                role = msg.get('role', 'user')[0].upper()
                content = msg.get('content', '')
                
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
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(OpenAIRateLimitError)
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
        Generate a response with prompt compression.
        """
        provider = await self._get_provider()
        
        if provider == "ollama":
            return await self._get_ollama_service().generate_response(
                query=query,
                context_chunks=context_chunks,
                temperature=temperature,
                chat_history=chat_history,
                conversation_summary=conversation_summary
            )
        elif provider == "mock":
            return self._generate_mock_response(query, context_chunks)
        
        # OpenAI provider
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
            response = await self.client.chat.completions.create(
                model=self.settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temp,
                max_tokens=self.settings.LLM_MAX_TOKENS,
                top_p=0.1,
            )
            
            answer = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            is_valid, issues = self._validate_response(answer)
            if not is_valid:
                logger.warning(f"Response validation issues: {issues}")
            
            sources = self._extract_sources(context_chunks)
            confidence = self._calculate_confidence(context_chunks, is_valid)
            
            logger.info(
                f"Generated OpenAI response for query: {query[:50]}... "
                f"Tokens: {tokens_used}, Confidence: {confidence}"
            )
            
            return answer, sources, confidence
            
        except OpenAIRateLimitError:
            raise
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
    
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
    
    def _validate_response(self, answer: str) -> Tuple[bool, List[str]]:
        """Validate response for external knowledge markers."""
        issues = []
        answer_lower = answer.lower()
        
        for pattern in self.EXTERNAL_KNOWLEDGE_PATTERNS:
            if re.search(pattern, answer_lower):
                issues.append(f"Possible external knowledge: {pattern}")
        
        return len(issues) == 0, issues
    
    def _calculate_confidence(
        self, 
        context_chunks: List[Tuple[DocumentChunk, float]], 
        is_valid: bool
    ) -> str:
        """Calculate confidence level based on retrieval scores."""
        if not context_chunks:
            return "low"
        
        avg_score = sum(score for _, score in context_chunks) / len(context_chunks)
        
        if avg_score > 0.7 and is_valid:
            return "high"
        elif avg_score > 0.5:
            return "medium"
        
        return "low"
    
    def _generate_mock_response(
        self, 
        query: str, 
        context_chunks: List[Tuple[DocumentChunk, float]]
    ) -> Tuple[str, List[SourceCitation], str]:
        """Generate a mock response when LLM is not available."""
        if not context_chunks:
            return (
                "This information is not present in your uploaded data.",
                [],
                "low"
            )
        
        context_text = "\n\n".join([chunk.text for chunk, _ in context_chunks[:2]])
        
        answer = f"""Based on your uploaded documents:

{context_text[:500]}...

[Note: This is a mock response. Configure OPENAI_API_KEY or install Ollama for full LLM functionality.]"""
        
        sources = self._extract_sources(context_chunks)
        confidence = "medium"
        
        return answer, sources, confidence
    
    def get_token_count(self, text: str) -> int:
        """Get accurate token count using cached tiktoken encoder."""
        if not text:
            return 0
        encoder = get_tiktoken_encoder("cl100k_base")
        return len(encoder.encode(text))
    
    async def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """Summarize a conversation."""
        provider = await self._get_provider()
        
        if provider == "ollama":
            return await self._get_ollama_service().summarize_conversation(messages)
        
        if provider == "mock":
            return ""
        
        # OpenAI
        messages = messages[-20:]
        conversation_text = "\n".join([
            f"{msg.get('role', 'user')[0].upper()}: {msg.get('content', '')[:100]}"
            for msg in messages
        ])
        
        prompt = f"Summarize:\n{conversation_text}\nSummary:"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "Summarize conversations concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=self.settings.MAX_SUMMARY_TOKENS,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            return ""
