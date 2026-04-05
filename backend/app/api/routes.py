"""
API routes for Panda - Session-based custom data chatbot.
With chat memory, hybrid RAG, session persistence, and 8GB RAM optimizations.
"""

import logging
import time
import os
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Form, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from openai import RateLimitError as OpenAIRateLimitError
from openai import APIError as OpenAIAPIError

from ..core.session_manager import session_manager
from ..core.config import get_settings
from ..core.embedding_registry import embedding_registry
from ..models.session import Session, SessionConfig
from ..models.query import QueryRequest, QueryResponse
from ..models.upload import UploadResponse, DocumentSummary
from ..services.document_processor import DocumentProcessor
from ..services.embedding_service import EmbeddingService
from ..services.retrieval_service import RetrievalService
from ..services.llm_service import LLMService
from ..services.ollama_service import OllamaService
from ..utils.rate_limiter import session_creation_limiter, upload_limiter, query_limiter
from ..utils.file_validation import validate_file_content, get_safe_filename
from ..utils.memory_monitor import get_memory_usage

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared services
doc_processor = DocumentProcessor()
embedding_service = EmbeddingService()
llm_service = LLMService()
ollama_service = OllamaService()

# Global request semaphore for concurrency control
_request_semaphore = None

async def get_request_semaphore():
    """Get or create request semaphore for concurrency control."""
    global _request_semaphore
    if _request_semaphore is None:
        import asyncio
        settings = get_settings()
        _request_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)
    return _request_semaphore


def get_client_ip(request: Request) -> str:
    """Get client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_session(session_id: str) -> Session:
    """Dependency to get and validate a session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


@router.post("/session/initiate")
async def initiate_session(request: Request):
    """
    Create a new isolated session.
    Returns session_id to be used in subsequent requests.
    Rate limited: 5 per minute per IP.
    """
    client_ip = get_client_ip(request)
    
    allowed, metadata = await session_creation_limiter.is_allowed(f"session_create:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": metadata.get("retry_after", 60),
                "limit": metadata["limit"]
            }
        )
    
    try:
        session = await session_manager.create_session()
        
        logger.info(f"Created session: {session.session_id} for IP: {client_ip}")
        
        return {
            "session_id": session.session_id,
            "status": "created",
            "expires_at": session.expires_at.isoformat(),
            "time_remaining_seconds": session.get_time_remaining()
        }
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


async def _process_file_batch(
    files: List[UploadFile],
    session: Session,
    settings,
    processed_docs: List,
    errors: List
):
    """Process a batch of files."""
    for file in files:
        try:
            content = await file.read()
            file_size_mb = len(content) / (1024 * 1024)
            
            if file_size_mb > session.config.max_file_size_mb:
                errors.append({
                    "file": get_safe_filename(file.filename or "unnamed"),
                    "error": f"File too large: {file_size_mb:.2f}MB (max {session.config.max_file_size_mb}MB)"
                })
                continue
            
            current_total = session.get_total_size_mb()
            if current_total + file_size_mb > session.config.max_total_size_mb:
                errors.append({
                    "file": get_safe_filename(file.filename or "unnamed"),
                    "error": f"Would exceed total session size limit ({session.config.max_total_size_mb}MB)"
                })
                continue
            
            is_valid, error_msg, detected_type = validate_file_content(
                content,
                file.filename or "unnamed",
                settings.ALLOWED_EXTENSIONS
            )
            
            if not is_valid:
                errors.append({
                    "file": get_safe_filename(file.filename or "unnamed"),
                    "error": error_msg
                })
                continue
            
            document = doc_processor.process_file(
                content, 
                get_safe_filename(file.filename or "unnamed"),
                file_type=detected_type
            )
            
            await embedding_service.generate_embeddings(document.chunks)
            
            session.add_document(document.document_id, document)
            
            processed_docs.append(document)
            logger.info(f"Processed file: {document.filename} (type: {detected_type})")
            
        except ValueError as e:
            logger.warning(f"Validation error for {file.filename}: {e}")
            errors.append({
                "file": get_safe_filename(file.filename or "unnamed"),
                "error": str(e)
            })
        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            errors.append({
                "file": get_safe_filename(file.filename or "unnamed"),
                "error": "Internal processing error"
            })


@router.post("/session/{session_id}/upload")
async def upload_files(
    request: Request,
    session_id: str,
    files: List[UploadFile] = File(...)
):
    """
    Upload and process files for a session.
    Processes in batches of 3 for 8GB RAM optimization.
    Thread-safe FAISS index updates with per-session locking.
    """
    client_ip = get_client_ip(request)
    
    allowed, metadata = await upload_limiter.is_allowed(f"upload:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Upload rate limit exceeded",
                "retry_after": metadata.get("retry_after", 60),
                "limit": metadata["limit"]
            }
        )
    
    session = await get_session(session_id)
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    settings = get_settings()
    processed_docs = []
    errors = []
    
    # Process files in batches
    batch_size = settings.DOCUMENT_BATCH_SIZE
    
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(files) + batch_size - 1)//batch_size}")
        
        semaphore = await get_request_semaphore()
        async with semaphore:
            await _process_file_batch(batch, session, settings, processed_docs, errors)
    
    # Update FAISS index with thread-safe operations
    # The RetrievalService has its own per-instance lock
    if processed_docs:
        if session.vector_store is not None:
            for doc in processed_docs:
                await session.vector_store.add_document_chunks(doc.chunks)
            
            logger.info(f"Incrementally added {len(processed_docs)} documents to index")
        else:
            # First upload - create new index
            all_chunks = []
            for doc in session.documents.values():
                all_chunks.extend(doc.chunks)
            
            retrieval_service = RetrievalService(embedding_service)
            await retrieval_service.build_index(all_chunks)
            session.vector_store = retrieval_service
            
            logger.info(f"Created new index with {len(all_chunks)} chunks")
    
    # Build response
    doc_summaries = [
        DocumentSummary(
            document_id=doc.document_id,
            filename=doc.filename,
            file_type=doc.file_type,
            size_mb=round(doc.size_bytes / (1024 * 1024), 2),
            total_chunks=doc.get_chunk_count(),
            total_tokens=doc.get_total_tokens(),
            processing_status=doc.processing_status
        )
        for doc in processed_docs
    ]
    
    response = UploadResponse(
        session_id=session_id,
        documents_processed=len(processed_docs),
        documents=doc_summaries,
        total_size_mb=round(session.get_total_size_mb(), 2),
        total_chunks=sum(doc.get_chunk_count() for doc in session.documents.values()),
        total_tokens=sum(doc.get_total_tokens() for doc in session.documents.values()),
        message=f"Successfully processed {len(processed_docs)} document(s)"
    )
    
    if errors:
        response.message += f" ({len(errors)} error(s))"
        return JSONResponse(
            status_code=207,
            content={
                **response.model_dump(),
                "errors": errors
            }
        )
    
    return response


@router.post("/session/{session_id}/query")
async def query_session(
    request: Request,
    session_id: str,
    query_request: QueryRequest
):
    """
    Query the chatbot with a question.
    Returns answer with source citations and chat memory context.
    """
    start_time = time.time()
    client_ip = get_client_ip(request)
    
    allowed, metadata = await query_limiter.is_allowed(f"query:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Query rate limit exceeded",
                "retry_after": metadata.get("retry_after", 60),
                "limit": metadata["limit"]
            }
        )
    
    semaphore = await get_request_semaphore()
    
    async with semaphore:
        session = await get_session(session_id)
        
        if not session.documents:
            raise HTTPException(
                status_code=400, 
                detail="No documents loaded. Upload files first."
            )
        
        if session.vector_store is None:
            raise HTTPException(
                status_code=500,
                detail="Vector store not initialized"
            )
        
        try:
            # Retrieve relevant chunks with dynamic threshold
            top_k = query_request.max_chunks or session.config.max_chunks_per_query
            retrieved_chunks = await session.vector_store.search_with_threshold(
                query_request.question, 
                top_k=top_k
            )
            
            if not retrieved_chunks:
                processing_time = (time.time() - start_time) * 1000
                
                session.add_chat_message("user", query_request.question)
                session.add_chat_message(
                    "assistant", 
                    "This information is not present in your uploaded data."
                )
                
                return QueryResponse(
                    answer="This information is not present in your uploaded data.",
                    sources=[],
                    confidence="low",
                    session_id=session_id,
                    tokens_used=0,
                    processing_time_ms=round(processing_time, 2),
                    query=query_request.question
                )
            
            # Get conversation context
            chat_history = session.get_recent_chat_history(settings.MAX_CHAT_HISTORY_TURNS)
            
            # Check if we need to summarize conversation
            if session.should_summarize(settings.CONVERSATION_SUMMARY_THRESHOLD):
                logger.info(f"Summarizing conversation for session {session_id}")
                older_messages = session.chat_history[:-settings.MAX_CHAT_HISTORY_TURNS]
                if older_messages:
                    summary = await llm_service.summarize_conversation(older_messages)
                    if summary:
                        session.update_conversation_summary(summary)
            
            # Generate response with chat memory
            answer, sources, confidence = await llm_service.generate_response(
                query=query_request.question,
                context_chunks=retrieved_chunks,
                temperature=query_request.temperature or session.config.temperature,
                chat_history=chat_history,
                conversation_summary=session.conversation_summary
            )
            
            tokens_used = llm_service.get_token_count(answer) + llm_service.get_token_count(query_request.question)
            session.total_tokens_used += tokens_used
            
            session.add_chat_message("user", query_request.question)
            session.add_chat_message("assistant", answer)
            
            processing_time = (time.time() - start_time) * 1000
            
            return QueryResponse(
                answer=answer,
                sources=sources,
                confidence=confidence,
                session_id=session_id,
                tokens_used=tokens_used,
                processing_time_ms=round(processing_time, 2),
                query=query_request.question
            )
            
        except OpenAIRateLimitError as e:
            logger.error(f"OpenAI rate limit: {e}")
            raise HTTPException(status_code=429, detail="AI service rate limit exceeded. Please try again later.")
        except OpenAIAPIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise HTTPException(status_code=502, detail="AI service error. Please try again later.")
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise HTTPException(status_code=500, detail="Query processing failed")


@router.delete("/session/{session_id}/terminate")
async def terminate_session(session_id: str):
    """Terminate a session and immediately erase all data."""
    success = await session_manager.terminate_session(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "status": "terminated",
        "message": "All session data has been erased"
    }


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get session status including loaded documents and time remaining."""
    session = await session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    return session.to_status_dict()


@router.get("/session/{session_id}/documents")
async def get_session_documents(session_id: str):
    """Get list of uploaded documents for a session."""
    session = await get_session(session_id)
    
    documents = [
        {
            "document_id": doc.document_id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "size_mb": round(doc.size_bytes / (1024 * 1024), 2),
            "total_chunks": doc.get_chunk_count(),
            "total_tokens": doc.get_total_tokens(),
            "uploaded_at": doc.uploaded_at.isoformat(),
            "processing_status": doc.processing_status
        }
        for doc in session.documents.values()
    ]
    
    return {
        "session_id": session_id,
        "documents": documents,
        "total_documents": len(documents)
    }


@router.post("/session/{session_id}/export")
async def export_session(session_id: str, background_tasks: BackgroundTasks):
    """Export session data to a JSON file for persistence."""
    settings = get_settings()
    
    if not settings.ENABLE_SESSION_PERSISTENCE:
        raise HTTPException(status_code=400, detail="Session persistence is disabled")
    
    session = await get_session(session_id)
    
    try:
        backup_dir = settings.BACKUP_DIR
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{session_id}_{timestamp}.json"
        filepath = os.path.join(backup_dir, filename)
        
        export_data = session.to_export_dict()
        
        if session.vector_store:
            export_data["vector_store_stats"] = session.vector_store.get_index_stats()
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported session {session_id} to {filepath}")
        
        return {
            "session_id": session_id,
            "exported": True,
            "filename": filename,
            "filepath": filepath,
            "documents_count": len(session.documents),
            "chat_turns": len(session.chat_history) // 2
        }
        
    except Exception as e:
        logger.error(f"Failed to export session: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/session/import")
async def import_session(request: Request):
    """Import a session from a previously exported JSON file."""
    settings = get_settings()
    
    if not settings.ENABLE_SESSION_PERSISTENCE:
        raise HTTPException(status_code=400, detail="Session persistence is disabled")
    
    try:
        data = await request.json()
        filepath = data.get('filepath')
        
        if not filepath:
            raise HTTPException(status_code=400, detail="filepath is required")
        
        backup_dir = os.path.abspath(settings.BACKUP_DIR)
        requested_path = os.path.abspath(filepath)
        
        if not requested_path.startswith(backup_dir):
            raise HTTPException(status_code=403, detail="Invalid filepath")
        
        if not os.path.exists(requested_path):
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        with open(requested_path, 'r') as f:
            import_data = json.load(f)
        
        session = await session_manager.create_session()
        
        if 'config' in import_data:
            session.config = SessionConfig(**import_data['config'])
        
        if 'chat_history' in import_data:
            session.chat_history = import_data['chat_history']
        
        if 'conversation_summary' in import_data:
            session.conversation_summary = import_data['conversation_summary']
            session.summary_turns_count = import_data.get('summary_turns_count', 0)
        
        logger.info(f"Imported session {import_data.get('session_id')} as new session {session.session_id}")
        
        return {
            "session_id": session.session_id,
            "imported": True,
            "original_session_id": import_data.get('session_id'),
            "original_created_at": import_data.get('created_at'),
            "restored_chat_turns": len(session.chat_history) // 2,
            "message": "Session imported. Please re-upload documents to restore full functionality."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import session: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint with memory usage and provider status."""
    memory = get_memory_usage()
    ollama_available = await ollama_service.check_availability()
    openai_available = bool(settings.OPENAI_API_KEY)
    
    return {
        "status": "healthy",
        "active_sessions": await session_manager.get_session_count(),
        "memory": memory,
        "embedding_registry": embedding_registry.get_embedding_config(),
        "providers": {
            "openai": {
                "available": openai_available,
                "model": settings.LLM_MODEL if openai_available else None
            },
            "ollama": {
                "available": ollama_available,
                "llm_model": settings.OLLAMA_LLM_MODEL if ollama_available else None,
                "embedding_model": settings.OLLAMA_EMBEDDING_MODEL if ollama_available else None
            },
            "local_embeddings": {
                "available": True,
                "model": settings.LOCAL_EMBEDDING_MODEL
            }
        },
        "features": {
            "hybrid_search": settings.ENABLE_HYBRID_SEARCH,
            "chat_memory": True,
            "session_persistence": settings.ENABLE_SESSION_PERSISTENCE
        }
    }


settings = get_settings()
