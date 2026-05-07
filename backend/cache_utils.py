"""
Caching and retry utilities for external API calls.

Key features:
- timed_cache: TTL-based in-memory cache with SWR (stale-while-revalidate),
  soft/hard TTL tiers, request deduplication, and circuit breaker.
- fetch_with_retry: exponential back-off + jitter for transient failures.

SWR behaviour:
  fresh (< soft_ttl)       → return cached immediately
  stale (soft_ttl–hard_ttl) → return cached + trigger background refresh
  expired (> hard_ttl)      → force refresh (blocking, serves stale on failure)

Request deduplication:
  Concurrent calls for the same key share one backend request.
  First caller fetches, others wait and receive the same result.

Circuit breaker:
  3 consecutive failures → open circuit (5min cooldown).
  During cooldown, serves stale data if available.
"""

import time
import random
import math
import threading
import logging
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Global state
# ──────────────────────────────────────────────────────────

# cache_key -> {"result": ..., "expiry": float, "soft_expiry": float,
#               "last_good": ..., "ttl": int, "soft_ttl": int, "hits": int}
_cache: dict = {}

# Circuit breaker state:
#   func_key -> {"failures": int, "state": "closed"|"open"|"half_open", "opened_at": float}
_circuit_breakers: dict = {}

# In-flight request coalescing:
#   cache_key -> {"event": threading.Event, "result": Any, "error": Exception}
_in_flight: dict = {}
_in_flight_lock = threading.Lock()

FAILURE_THRESHOLD = 3       # consecutive failures before opening
COOLDOWN_SECONDS = 300      # 5 min cooldown after circuit opens


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def sanitize_metric(v, default=None):
    """Ensures a value is JSON-serializable (no NaN/Inf)."""
    if v is None: return default
    try:
        f_val = float(v)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        if isinstance(v, int):
            return v
        return f_val
    except (ValueError, TypeError):
        return default
    except:
        return default


def timed_cache(
    ttl_seconds: int,
    soft_ttl_seconds: Optional[int] = None,
    swr: bool = True,
    deduplicate: bool = True,
):
    """
    Decorator that caches function results with SWR support.

    Parameters
    ----------
    ttl_seconds : int
        Hard TTL — after this, cache is expired and must refresh.
    soft_ttl_seconds : int, optional
        Soft TTL — between soft and hard TTL, cached data is returned
        immediately but a background refresh is triggered (SWR).
        Defaults to ttl_seconds * 0.75 if not specified.
    swr : bool
        Enable stale-while-revalidate. When True, returns stale data
        while refreshing in the background. Default True.
    deduplicate : bool
        Enable request coalescing. When True, concurrent calls for the
        same key share one backend fetch. Default True.

    Usage::

        @timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)
        def get_market_data():
            return expensive_api_call()
    """
    if soft_ttl_seconds is None:
        soft_ttl_seconds = int(ttl_seconds * 0.75)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            breaker_key = func.__name__
            current_time = time.time()

            entry = _cache.get(cache_key)

            # --- Cache hit (fresh) ---
            if entry and current_time < entry["soft_expiry"]:
                entry["hits"] = entry.get("hits", 0) + 1
                logger.debug("[CACHE HIT fresh] %s", func.__name__)
                return entry["result"]

            # --- Cache hit (stale, SWR eligible) ---
            if entry and swr and current_time < entry["expiry"]:
                entry["hits"] = entry.get("hits", 0) + 1
                logger.debug("[CACHE HIT stale/SWR] %s — returning stale, refreshing in background", func.__name__)
                # Trigger background refresh (fire-and-forget thread)
                _swr_refresh(func, args, kwargs, cache_key, ttl_seconds, soft_ttl_seconds, breaker_key)
                return entry["result"]

            # --- Request deduplication (in-flight coalescing) ---
            if deduplicate:
                with _in_flight_lock:
                    pending = _in_flight.get(cache_key)
                    if pending:
                        # Another thread is already fetching — wait for it
                        logger.debug("[DEDUPE WAIT] %s — waiting for in-flight request", func.__name__)
                        pending["event"].wait(timeout=ttl_seconds)
                        if pending["error"]:
                            if entry and entry.get("last_good") is not None:
                                return entry["last_good"]
                            raise pending["error"]
                        return pending["result"]
                    else:
                        # We are the first — create the pending slot
                        _in_flight[cache_key] = {
                            "event": threading.Event(),
                            "result": None,
                            "error": None,
                        }

            # --- Circuit breaker check ---
            breaker = _circuit_breakers.get(breaker_key)
            if breaker and breaker["state"] == "open":
                if current_time - breaker["opened_at"] >= COOLDOWN_SECONDS:
                    breaker["state"] = "half_open"
                    logger.info("[CIRCUIT HALF-OPEN] %s — allowing one test request", func.__name__)
                else:
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
                    raise RuntimeError(
                        f"Circuit breaker open for {func.__name__}: API unavailable, no cached data"
                    )

            # --- Cache miss / expired — fetch ---
            logger.debug("[CACHE MISS] %s", func.__name__)
            try:
                result = func(*args, **kwargs)

                # Success — reset circuit breaker
                if breaker:
                    breaker["failures"] = 0
                    breaker["state"] = "closed"
                    logger.debug("[CIRCUIT CLOSED] %s — reset breaker", func.__name__)

                _cache[cache_key] = {
                    "result": result,
                    "expiry": current_time + ttl_seconds,
                    "soft_expiry": current_time + soft_ttl_seconds,
                    "last_good": result,
                    "ttl": ttl_seconds,
                    "soft_ttl": soft_ttl_seconds,
                    "hits": 1,
                    "last_refresh": current_time,
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

                if breaker["failures"] >= FAILURE_THRESHOLD and breaker["state"] != "open":
                    breaker["state"] = "open"
                    breaker["opened_at"] = current_time
                    logger.warning(
                        "[CIRCUIT OPEN] %s — %d consecutive failures. Entering %ds cooldown.",
                        func.__name__, breaker["failures"], COOLDOWN_SECONDS,
                    )

                # Stale fallback
                if entry and entry.get("last_good") is not None:
                    logger.warning(
                        "[CACHE STALE] %s failed (%s). Returning last known good value.",
                        func.__name__, exc,
                    )
                    entry["expiry"] = current_time + min(ttl_seconds, 300)
                    return entry["last_good"]
                raise

            finally:
                # Resolve in-flight waiters
                if deduplicate:
                    with _in_flight_lock:
                        pending = _in_flight.pop(cache_key, None)
                        if pending:
                            pending["event"].set()

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
            delay += random.uniform(0, 1.0)
            logger.warning(
                "[RETRY %d/%d] %s failed: %s. Retrying in %.1fs …",
                attempt, max_attempts, getattr(func, "__name__", "func"), exc, delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def clear_cache():
    """Manually clear all cached data, circuit breakers, and in-flight slots."""
    global _cache, _circuit_breakers, _in_flight
    _cache = {}
    _circuit_breakers = {}
    with _in_flight_lock:
        _in_flight = {}
    logger.info("[CACHE] Cleared all cached data, circuit breakers, and in-flight requests.")


def get_cache_stats() -> dict:
    """Returns current cache and circuit breaker statistics."""
    current_time = time.time()
    cache_entries = {}
    for key, entry in _cache.items():
        is_fresh = current_time < entry["soft_expiry"]
        is_stale = not is_fresh and current_time < entry["expiry"]
        cache_entries[key] = {
            "fresh": is_fresh,
            "stale": is_stale,
            "expired": not is_fresh and not is_stale,
            "hits": entry.get("hits", 0),
            "has_last_good": entry.get("last_good") is not None,
            "age_seconds": round(current_time - entry.get("last_refresh", current_time), 1),
        }

    breaker_stats = {}
    for key, breaker in _circuit_breakers.items():
        breaker_stats[key] = {
            "state": breaker["state"],
            "failures": breaker["failures"],
            "cooldown_remaining": max(0, round(COOLDOWN_SECONDS - (current_time - breaker["opened_at"]), 1)) if breaker["state"] == "open" else 0,
        }

    with _in_flight_lock:
        in_flight_count = len(_in_flight)

    return {
        "cache_entries": len(_cache),
        "cache_details": cache_entries,
        "circuit_breakers": breaker_stats,
        "in_flight_requests": in_flight_count,
    }


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _swr_refresh(func, args, kwargs, cache_key, ttl, soft_ttl, breaker_key):
    """
    Fire-and-forget background refresh for SWR.
    Runs in a daemon thread so it doesn't block the caller.
    """
    def _refresh():
        current_time = time.time()
        entry = _cache.get(cache_key)
        try:
            result = func(*args, **kwargs)

            # Reset circuit breaker on success
            breaker = _circuit_breakers.get(breaker_key)
            if breaker:
                breaker["failures"] = 0
                breaker["state"] = "closed"

            # Update cache in place (don't invalidate what other callers are reading)
            if entry:
                entry["result"] = result
                entry["expiry"] = current_time + ttl
                entry["soft_expiry"] = current_time + soft_ttl
                entry["last_good"] = result
                entry["last_refresh"] = current_time
            else:
                _cache[cache_key] = {
                    "result": result,
                    "expiry": current_time + ttl,
                    "soft_expiry": current_time + soft_ttl,
                    "last_good": result,
                    "ttl": ttl,
                    "soft_ttl": soft_ttl,
                    "hits": 1,
                    "last_refresh": current_time,
                }
            logger.debug("[SWR REFRESH OK] %s — cache updated in background", func.__name__)
        except Exception as exc:
            logger.warning("[SWR REFRESH FAIL] %s — %s. Keeping stale data.", func.__name__, exc)
            # Track failure for circuit breaker even in SWR
            breaker = _circuit_breakers.get(breaker_key)
            if breaker is None:
                _circuit_breakers[breaker_key] = {
                    "failures": 1,
                    "state": "closed",
                    "opened_at": 0,
                }
                breaker = _circuit_breakers[breaker_key]
            else:
                breaker["failures"] += 1

    thread = threading.Thread(target=_refresh, daemon=True, name=f"swr-{func.__name__}")
    thread.start()
