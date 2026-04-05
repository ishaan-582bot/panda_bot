"""
Memory monitoring utilities for 8GB RAM optimization.
"""

import logging
import psutil
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_memory_usage() -> Dict[str, Any]:
    """
    Get current memory usage statistics.
    
    Returns:
        Dict with memory usage information
    """
    try:
        # System memory
        system_memory = psutil.virtual_memory()
        
        # Process memory
        process = psutil.Process()
        process_memory = process.memory_info()
        
        return {
            "system": {
                "total_gb": round(system_memory.total / (1024**3), 2),
                "available_gb": round(system_memory.available / (1024**3), 2),
                "used_gb": round(system_memory.used / (1024**3), 2),
                "percent": system_memory.percent,
                "status": _get_memory_status(system_memory.percent)
            },
            "process": {
                "rss_mb": round(process_memory.rss / (1024**2), 2),
                "vms_mb": round(process_memory.vms / (1024**2), 2),
            }
        }
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        return {
            "system": {"error": str(e)},
            "process": {"error": str(e)}
        }


def _get_memory_status(percent: float) -> str:
    """Get memory status based on usage percentage."""
    if percent < 50:
        return "healthy"
    elif percent < 75:
        return "moderate"
    elif percent < 90:
        return "high"
    else:
        return "critical"


def format_memory(memory_dict: Dict[str, Any]) -> str:
    """Format memory usage for display."""
    system = memory_dict.get("system", {})
    process = memory_dict.get("process", {})
    
    return (
        f"System: {system.get('used_gb', 'N/A')}GB / {system.get('total_gb', 'N/A')}GB "
        f"({system.get('percent', 'N/A')}%) - {system.get('status', 'unknown')} | "
        f"Process: {process.get('rss_mb', 'N/A')}MB RSS"
    )


def check_memory_available(required_mb: float = 500) -> bool:
    """
    Check if enough memory is available.
    
    Args:
        required_mb: Required memory in MB
        
    Returns:
        True if enough memory is available
    """
    try:
        memory = psutil.virtual_memory()
        available_mb = memory.available / (1024**2)
        return available_mb >= required_mb
    except Exception:
        return True  # Assume OK if we can't check


def get_memory_pressure() -> float:
    """
    Get memory pressure as a percentage (0-100).
    Higher values indicate more memory pressure.
    """
    try:
        memory = psutil.virtual_memory()
        return memory.percent
    except Exception:
        return 0.0
