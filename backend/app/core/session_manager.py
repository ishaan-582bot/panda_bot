"""
Session Manager - Manages isolated chatbot sessions with strict memory-only storage.
No persistence - all data is wiped on session end or timeout.
"""

import asyncio
import gc
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from ..models.session import Session, SessionStatus
from ..models.document import Document, DocumentChunk
from ..utils.memory_wipe import wipe_float_list, secure_delete_list

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages isolated chatbot sessions with strict memory-only storage.
    No persistence - all data is wiped on session end or timeout.
    """
    
    _instance: Optional['SessionManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()
    _initialized: bool = False
    
    def __new__(cls) -> 'SessionManager':
        """Singleton with proper thread safety."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialize storage immediately to avoid AttributeError
            cls._instance.sessions: Dict[str, Session] = {}
            cls._instance._cleanup_task: Optional[asyncio.Task] = None
        return cls._instance
    
    async def _async_init(self) -> None:
        """Async initialization - call this before using the manager."""
        async with SessionManager._lock:
            if not SessionManager._initialized:
                SessionManager._initialized = True
                self._start_cleanup_task()
                logger.info("SessionManager initialized")
    
    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session cleanup task started")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions and cryptographically erase data."""
        expired_sessions: list[str] = []
        
        async with SessionManager._lock:
            for session_id, session in self.sessions.items():
                if session.is_expired():
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.terminate_session(session_id)
            logger.info(f"Auto-terminated expired session: {session_id}")
    
    async def create_session(self) -> Session:
        """
        Create a new isolated session.
        Returns the session object.
        """
        await self._async_init()
        
        async with SessionManager._lock:
            session = Session()
            self.sessions[session.session_id] = session
            logger.info(f"Created new session: {session.session_id}")
            return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID if it exists and is active.
        Updates activity timestamp on successful retrieval.
        """
        await self._async_init()
        
        async with SessionManager._lock:
            session = self.sessions.get(session_id)
            
            if session is None:
                return None
            
            if session.status != SessionStatus.ACTIVE:
                return None
            
            if session.is_expired():
                return None
            
            # Update activity
            session.update_activity()
            return session
    
    async def session_exists(self, session_id: str) -> bool:
        """Check if a session exists and is active."""
        session = await self.get_session(session_id)
        return session is not None
    
    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a session and cryptographically erase all data.
        Returns True if session was found and terminated.
        """
        await self._async_init()
        
        async with SessionManager._lock:
            session = self.sessions.get(session_id)
            
            if session is None:
                return False
            
            # Mark as terminated
            session.status = SessionStatus.TERMINATED
            
            # Cryptographic erasure of sensitive data
            await self._erase_session_data(session)
            
            # Remove from sessions dict
            del self.sessions[session_id]
        
        # Force garbage collection outside the lock
        gc.collect(0)
        gc.collect(1)
        gc.collect(2)
        
        logger.info(f"Terminated and erased session: {session_id}")
        return True
    
    async def _erase_session_data(self, session: Session) -> None:
        """
        Cryptographically erase session data.
        
        IMPORTANT: Python strings are immutable, so we cannot truly overwrite
        the original memory. This is a best-effort implementation that:
        1. Overwrites mutable bytearray content
        2. Overwrites embedding vectors (list of floats)
        3. Clears references to help GC
        
        For true cryptographic erasure, use a language with manual memory management.
        """
        try:
            # Erase document content and embeddings
            for doc_id in list(session.documents.keys()):
                doc = session.documents[doc_id]
                if isinstance(doc, Document):
                    # Erase chunk embeddings (these are mutable lists)
                    for chunk in doc.chunks:
                        if isinstance(chunk, DocumentChunk):
                            # Wipe embedding vectors
                            if chunk.embedding is not None:
                                wipe_float_list(chunk.embedding)
                                chunk.embedding = None
                            
                            # Clear text reference (string - immutable, best effort)
                            chunk.text = ""
                    
                    # Clear content reference
                    doc.content = None
                    
                    # Clear chunks list
                    secure_delete_list(doc.chunks)
            
            # Clear vector store
            if session.vector_store is not None:
                try:
                    # FAISS doesn't have a clear method, but we can delete the index
                    if hasattr(session.vector_store, 'index') and session.vector_store.index is not None:
                        # Delete the index to free C++ memory
                        del session.vector_store.index
                        session.vector_store.index = None
                except Exception as e:
                    logger.warning(f"Error clearing FAISS index: {e}")
                
                session.vector_store = None
            
            # Clear chat history
            for msg in session.chat_history:
                if isinstance(msg, dict):
                    for key in list(msg.keys()):
                        if isinstance(msg[key], str):
                            msg[key] = ""
                        elif isinstance(msg[key], list):
                            secure_delete_list(msg[key])
            
            session.chat_history.clear()
            
            # Clear documents dict
            session.documents.clear()
            
        except Exception as e:
            logger.error(f"Error during data erasure: {e}")
    
    async def get_all_sessions(self) -> Dict[str, Session]:
        """Get all active sessions (for admin/debugging)."""
        await self._async_init()
        
        async with SessionManager._lock:
            return {
                sid: session 
                for sid, session in self.sessions.items() 
                if session.status == SessionStatus.ACTIVE and not session.is_expired()
            }
    
    async def get_session_count(self) -> int:
        """Get count of active sessions."""
        sessions = await self.get_all_sessions()
        return len(sessions)
    
    async def shutdown(self) -> None:
        """Shutdown the session manager and terminate all sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Terminate all sessions
        async with SessionManager._lock:
            session_ids = list(self.sessions.keys())
        
        for session_id in session_ids:
            await self.terminate_session(session_id)
        
        logger.info("Session manager shutdown complete")


# Global session manager instance - must call _async_init() before use
session_manager = SessionManager()
