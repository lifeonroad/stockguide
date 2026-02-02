"""
Simple time-based caching utility for expensive API calls.
Uses in-memory storage with TTL (Time To Live).
"""

import time
from functools import wraps
from typing import Callable, Any

# Global cache storage: {cache_key: (result, expiry_timestamp)}
_cache = {}

def timed_cache(ttl_seconds: int):
    """
    Decorator that caches function results for a specified time period.
    
    Args:
        ttl_seconds: Time to live in seconds (e.g., 900 for 15 minutes)
    
    Usage:
        @timed_cache(ttl_seconds=900)
        def expensive_function():
            return fetch_from_api()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            current_time = time.time()
            
            # Check if cached result exists and is still valid
            if cache_key in _cache:
                result, expiry = _cache[cache_key]
                if current_time < expiry:
                    print(f"[CACHE HIT] {func.__name__}")
                    return result
            
            # Cache miss or expired - call function
            print(f"[CACHE MISS] {func.__name__}")
            result = func(*args, **kwargs)
            
            # Store result with expiry timestamp
            _cache[cache_key] = (result, current_time + ttl_seconds)
            
            return result
        
        return wrapper
    return decorator


def clear_cache():
    """Manually clear all cached data."""
    global _cache
    _cache = {}
    print("[CACHE] Cleared all cached data")
