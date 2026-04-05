"""
Rate limiting utilities for API endpoints.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateLimitEntry:
    """Tracks request count and window start for a client."""
    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    Automatically cleans up expired entries.
    """
    
    def __init__(self, requests_per_minute: int = 60, cleanup_interval_seconds: int = 300):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self.cleanup_interval = cleanup_interval_seconds
        self._storage: Dict[str, RateLimitEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        try:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running, skip cleanup task
            pass
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
    
    async def is_allowed(self, key: str) -> Tuple[bool, Dict]:
        """
        Check if a request is allowed for the given key.
        
        Args:
            key: Unique identifier (e.g., IP + endpoint)
            
        Returns:
            Tuple of (allowed, metadata)
            metadata contains: limit, remaining, reset_time
        """
        async with self._lock:
            now = time.time()
            entry = self._storage.get(key)
            
            # If no entry or window expired, create new
            if entry is None or (now - entry.window_start) > self.window_seconds:
                self._storage[key] = RateLimitEntry(count=1, window_start=now)
                return True, {
                    "limit": self.requests_per_minute,
                    "remaining": self.requests_per_minute - 1,
                    "reset_time": int(now + self.window_seconds)
                }
            
            # Check if under limit
            if entry.count < self.requests_per_minute:
                entry.count += 1
                return True, {
                    "limit": self.requests_per_minute,
                    "remaining": self.requests_per_minute - entry.count,
                    "reset_time": int(entry.window_start + self.window_seconds)
                }
            
            # Rate limit exceeded
            reset_time = int(entry.window_start + self.window_seconds)
            return False, {
                "limit": self.requests_per_minute,
                "remaining": 0,
                "reset_time": reset_time,
                "retry_after": max(0, reset_time - int(now))
            }
    
    async def cleanup(self) -> None:
        """Remove expired entries."""
        async with self._lock:
            now = time.time()
            expired_keys = [
                key for key, entry in self._storage.items()
                if (now - entry.window_start) > self.window_seconds
            ]
            for key in expired_keys:
                del self._storage[key]
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")
    
    def get_stats(self) -> Dict:
        """Get statistics about the rate limiter."""
        return {
            "total_entries": len(self._storage),
            "requests_per_minute": self.requests_per_minute,
            "window_seconds": self.window_seconds
        }


# Global rate limiters
session_creation_limiter = RateLimiter(requests_per_minute=5)
upload_limiter = RateLimiter(requests_per_minute=10)
query_limiter = RateLimiter(requests_per_minute=60)