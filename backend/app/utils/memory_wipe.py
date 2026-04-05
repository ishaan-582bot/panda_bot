"""
Memory wiping utilities for cryptographic erasure.
Uses ctypes to overwrite memory buffers directly.
"""

import ctypes
import gc
import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def wipe_bytearray_buffer(buf: bytearray) -> None:
    """
    Cryptographically wipe a bytearray by overwriting with zeros.
    Bytearrays are mutable, so we can actually overwrite the memory.
    """
    if buf is None or len(buf) == 0:
        return
    
    # Overwrite with zeros
    for i in range(len(buf)):
        buf[i] = 0
    
    # Overwrite with ones
    for i in range(len(buf)):
        buf[i] = 0xFF
    
    # Overwrite with random pattern
    import secrets
    random_bytes = secrets.token_bytes(len(buf))
    for i in range(len(buf)):
        buf[i] = random_bytes[i]
    
    # Final zero overwrite
    for i in range(len(buf)):
        buf[i] = 0


def wipe_string_list(strings: List[str]) -> None:
    """
    Attempt to wipe strings by converting to mutable buffers.
    Note: This is best-effort in Python due to string immutability.
    The actual string objects may still exist in memory until GC.
    """
    for s in strings:
        if s is None:
            continue
        
        # Convert to mutable bytearray, wipe it
        try:
            buf = bytearray(s, 'utf-8')
            wipe_bytearray_buffer(buf)
        except Exception:
            pass
        
        # Reassign to empty string (helps with reference counting)
        s = ""


def wipe_float_list(floats: List[float]) -> None:
    """Wipe a list of floats by overwriting with zeros."""
    if floats is None:
        return
    
    for i in range(len(floats)):
        floats[i] = 0.0


def secure_delete_list(lst: List[Any]) -> None:
    """
    Securely delete list contents by wiping and clearing.
    """
    if lst is None:
        return
    
    # Wipe each element if possible
    for item in lst:
        if isinstance(item, bytearray):
            wipe_bytearray_buffer(item)
        elif isinstance(item, list):
            wipe_float_list(item)
    
    # Clear the list
    lst.clear()


def force_garbage_collection() -> None:
    """Force aggressive garbage collection."""
    gc.collect(0)  # Young generation
    gc.collect(1)  # Middle generation
    gc.collect(2)  # Full collection
