"""
Caching and retry utilities for yfinance API calls.

Key features:
- timed_cache: TTL-based in-memory cache with stale-while-revalidate.
  On a hard failure, the last known good value is returned instead of
  propagating the error, which prevents cold-start floods from crashing
  every endpoint simultaneously.
- fetch_with_retry: wraps any callable with exponential back-off +
  jitter so individual yfinance requests survive transient rate-limits.
"""

import time
import random
import math

def sanitize_metric(v, default=None):
    """Ensures a value is JSON-serializable (no NaN/Inf)."""
    if v is None: return default
    try:
        # Force to float to check for NaN/Inf, handles numpy scalars too
        f_val = float(v)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        # If it was an int, return as int if it didn't change
        if isinstance(v, int):
            return v
        return f_val
    except (ValueError, TypeError):
        return default
    except:
        return default
import logging
import yfinance as yf
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Global cache storage:
#   cache_key -> {"result": ..., "expiry": float, "last_good": ...}
_cache: dict = {}

# Circuit breaker state:
#   func_key -> {"failures": int, "state": "closed"|"open"|"half_open", "opened_at": float}
_circuit_breakers: dict = {}

FAILURE_THRESHOLD = 3       # consecutive failures before opening
COOLDOWN_SECONDS = 300      # 5 min cooldown after circuit opens


def timed_cache(ttl_seconds: int):
    """
    Decorator that caches function results for *ttl_seconds*.

    Stale-while-revalidate behaviour:
    - If the cached value is still fresh → return it immediately.
    - If the cache is expired or empty → call the function.
      • Success → store new result and return it.
      • Exception → if a previous good result exists, log a warning and
        return *that* instead of raising, so callers never get a hard
        error just because Yahoo Finance is temporarily rate-limiting us.

    Usage::

        @timed_cache(ttl_seconds=900)
        def expensive_function():
            return fetch_from_api()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            breaker_key = func.__name__
            current_time = time.time()

            entry = _cache.get(cache_key)

            # --- Cache hit (fresh) ---
            if entry and current_time < entry["expiry"]:
                logger.debug("[CACHE HIT] %s", func.__name__)
                return entry["result"]

            # --- Circuit breaker check ---
            breaker = _circuit_breakers.get(breaker_key)
            if breaker and breaker["state"] == "open":
                # Check if cooldown has elapsed
                if current_time - breaker["opened_at"] >= COOLDOWN_SECONDS:
                    breaker["state"] = "half_open"
                    logger.info("[CIRCUIT HALF-OPEN] %s — allowing one test request", func.__name__)
                else:
                    # Still in cooldown — serve stale or raise
                    if entry and entry.get("last_good") is not None:
                        logger.warning(
                            "[CIRCUIT OPEN] %s — serving stale data (cooldown active)",
                            func.__name__,
                        )
                        return entry["last_good"]
                    logger.error(
                        "[CIRCUIT OPEN] %s — no cached data available, failing",
                        func.__name__,
                    )
                    # Re-raise the last known error
                    raise RuntimeError(
                        f"Circuit breaker open for {func.__name__}: API unavailable, no cached data"
                    )

            # --- Cache miss / expired ---
            logger.debug("[CACHE MISS] %s", func.__name__)
            try:
                result = func(*args, **kwargs)

                # Success — reset circuit breaker
                if breaker:
                    breaker["failures"] = 0
                    breaker["state"] = "closed"
                    logger.info("[CIRCUIT CLOSED] %s — request succeeded, reset breaker", func.__name__)

                _cache[cache_key] = {
                    "result": result,
                    "expiry": current_time + ttl_seconds,
                    "last_good": result,          # snapshot of last successful value
                }
                return result
            except Exception as exc:
                # Track failure for circuit breaker
                if breaker is None:
                    _circuit_breakers[breaker_key] = {
                        "failures": 1,
                        "state": "closed",
                        "opened_at": 0,
                    }
                    breaker = _circuit_breakers[breaker_key]
                else:
                    breaker["failures"] += 1

                # Check if we should open the circuit
                if breaker["failures"] >= FAILURE_THRESHOLD and breaker["state"] != "open":
                    breaker["state"] = "open"
                    breaker["opened_at"] = current_time
                    logger.warning(
                        "[CIRCUIT OPEN] %s — %d consecutive failures. "
                        "Entering %ds cooldown.",
                        func.__name__, breaker["failures"], COOLDOWN_SECONDS,
                    )

                # Stale fallback
                if entry and entry.get("last_good") is not None:
                    logger.warning(
                        "[CACHE STALE] %s failed (%s). Returning last known good value.",
                        func.__name__, exc,
                    )
                    # Extend expiry briefly so we don't hammer the API on every request
                    entry["expiry"] = current_time + min(ttl_seconds, 300)
                    return entry["last_good"]
                # No previous value → re-raise so the caller can handle it
                raise

        return wrapper
    return decorator


def fetch_with_retry(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    **kwargs,
) -> Any:
    """
    Call *func(*args, **kwargs)* up to *max_attempts* times with
    exponential back-off and random jitter between attempts.

    Raises the last exception if all attempts fail.

    Example::

        info = fetch_with_retry(lambda: yf.Ticker(symbol).info)
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            # Add up to 1 s of jitter to spread concurrent retries
            delay += random.uniform(0, 1.0)
            logger.warning(
                "[RETRY %d/%d] %s failed: %s. Retrying in %.1fs …",
                attempt, max_attempts, getattr(func, "__name__", "func"), exc, delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def clear_cache():
    """Manually clear all cached data and circuit breakers (useful for testing)."""
    global _cache, _circuit_breakers
    _cache = {}
    _circuit_breakers = {}
    logger.info("[CACHE] Cleared all cached data and circuit breakers.")


def get_cache_stats() -> dict:
    """
    Returns current cache and circuit breaker statistics.
    Useful for monitoring and debugging.
    """
    current_time = time.time()
    cache_entries = {}
    for key, entry in _cache.items():
        is_fresh = current_time < entry["expiry"]
        age = current_time - (entry["expiry"] - ttl_seconds) if "ttl_seconds" in entry else 0
        cache_entries[key] = {
            "fresh": is_fresh,
            "has_last_good": entry.get("last_good") is not None,
        }

    breaker_stats = {}
    for key, breaker in _circuit_breakers.items():
        breaker_stats[key] = {
            "state": breaker["state"],
            "failures": breaker["failures"],
            "cooldown_remaining": max(0, COOLDOWN_SECONDS - (current_time - breaker["opened_at"])) if breaker["state"] == "open" else 0,
        }

    return {
        "cache_entries": len(_cache),
        "circuit_breakers": breaker_stats,
    }
