# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Error handling utilities

import os
import shutil
from typing import Tuple, Optional
from pathlib import Path


# Disk Space Utilities
def get_disk_space(path: str = "/downloads") -> Tuple[int, int, int]:
    """
    Get disk space info for a path.
    
    Returns:
        Tuple of (total, used, free) in bytes
    """
    try:
        usage = shutil.disk_usage(path)
        return usage.total, usage.used, usage.free
    except Exception:
        return 0, 0, 0


def check_disk_space(required_bytes: int, path: str = "/downloads") -> Tuple[bool, str]:
    """
    Check if there's enough disk space.
    
    Args:
        required_bytes: Space needed in bytes
        path: Path to check
        
    Returns:
        Tuple of (has_space, message)
    """
    total, used, free = get_disk_space(path)
    
    if free == 0:
        return False, "Unable to check disk space"
    
    # Add 10% buffer
    required_with_buffer = int(required_bytes * 1.1)
    
    if free >= required_with_buffer:
        return True, f"Sufficient space: {format_bytes(free)} free"
    else:
        return False, f"Insufficient space: need {format_bytes(required_with_buffer)}, have {format_bytes(free)}"


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable string."""
    if bytes_val == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    val = float(bytes_val)
    
    while val >= 1024 and i < len(units) - 1:
        val /= 1024
        i += 1
    
    return f"{val:.1f} {units[i]}"


# Retry Decorator
import asyncio
from functools import wraps


def async_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for async functions with retry logic.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        print(f"Warning: {func.__name__} attempt {attempt + 1} failed: {e}, retrying in {current_delay}s...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"Error: {func.__name__} failed after {max_attempts} attempts: {e}")
            
            raise last_exception
        return wrapper
    return decorator


def sync_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for sync functions with retry logic.
    """
    import time
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        print(f"Warning: {func.__name__} attempt {attempt + 1} failed: {e}, retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"Error: {func.__name__} failed after {max_attempts} attempts: {e}")
            
            raise last_exception
        return wrapper
    return decorator
