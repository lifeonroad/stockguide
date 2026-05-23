"""
memory_watch.py — Lightweight memory leak detection using Python's tracemalloc
================================================================================

Non-intrusive memory monitoring that:
- Uses only stdlib (tracemalloc, gc) — no extra dependencies
- Takes periodic snapshots and compares for unexpected growth
- Logs warnings when potential leaks are detected
- Provides stats via API endpoint

Designed to be seamless: low overhead, no fundamental changes needed.
"""

import tracemalloc
import gc
import threading
import time
import logging
import os
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_watcher_running = False
_watcher_thread: Optional[threading.Thread] = None
_watcher_lock = threading.Lock()

_baseline_snapshot: Optional[tracemalloc.Snapshot] = None
_previous_snapshot: Optional[tracemalloc.Snapshot] = None
_baseline_bytes: int = 0
_memory_log: List[Dict[str, Any]] = []
_max_log_entries = 100

GROWTH_WARNING_THRESHOLD_PERCENT = 50
GROWTH_WARNING_THRESHOLD_MB = 50
CHECK_INTERVAL_MINUTES = 30
MAX_TRACED_BACKUPS = 25


@dataclass
class MemoryStats:
    current_allocated_mb: float
    peak_allocated_mb: float
    baseline_allocated_mb: Optional[float]
    growth_since_baseline_percent: Optional[float]
    growth_since_baseline_mb: Optional[float]
    top_growers: List[Dict[str, Any]]
    gc_counts: Tuple[int, int, int]
    process_rss_mb: Optional[float]


def _get_process_rss_mb() -> Optional[float]:
    """Get process RSS memory in MB (cross-platform)."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
    try:
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        if hasattr(rusage, 'ru_maxrss'):
            return rusage.ru_maxrss / 1024
    except Exception:
        pass
    return None


def start_memory_watcher(check_interval_minutes: int = CHECK_INTERVAL_MINUTES,
                          n_frames: int = 5) -> Optional[threading.Thread]:
    """
    Start the memory watcher in a daemon background thread.
    
    Args:
        check_interval_minutes: How often to check memory (default 30 min)
        n_frames: Number of stack frames to trace for allocation tracking
    
    Returns:
        The daemon thread, or None if already running.
    """
    global _watcher_running, _watcher_thread, _baseline_snapshot, _previous_snapshot

    with _watcher_lock:
        if _watcher_running:
            logger.warning("[MEMORY WATCHER] Already running, not starting another")
            return _watcher_thread

        if not tracemalloc.is_tracing():
            tracemalloc.start(n_frames)
            logger.info("[MEMORY WATCHER] tracemalloc started with %d frames", n_frames)

        gc.set_debug(gc.DEBUG_UNCOLLECTABLE if hasattr(gc, 'DEBUG_UNCOLLECTABLE') else 0)

        _baseline_snapshot = tracemalloc.take_snapshot()
        _previous_snapshot = _baseline_snapshot
        _watcher_running = True

        _baseline_bytes, peak = tracemalloc.get_traced_memory()
        logger.info(
            "[MEMORY WATCHER] Baseline: current=%.1f MB, peak=%.1f MB",
            _baseline_bytes / (1024 * 1024),
            peak / (1024 * 1024)
        )

        def _watcher_loop():
            global _watcher_running, _previous_snapshot

            while _watcher_running:
                try:
                    time.sleep(check_interval_minutes * 60)
                    if not _watcher_running:
                        break

                    gc.collect()

                    current_snapshot = tracemalloc.take_snapshot()
                    current, peak = tracemalloc.get_traced_memory()
                    current_mb = current / (1024 * 1024)

                    stats = _get_stats_internal(current_snapshot, current, peak)

                    _memory_log.append({
                        "timestamp": time.time(),
                        "current_mb": round(current_mb, 2),
                        "growth_since_baseline_percent": stats.growth_since_baseline_percent,
                    })
                    if len(_memory_log) > _max_log_entries:
                        _memory_log.pop(0)

                    should_warn = False
                    warn_msg = ""

                    if stats.growth_since_baseline_percent is not None:
                        if (stats.growth_since_baseline_percent > GROWTH_WARNING_THRESHOLD_PERCENT and
                            stats.growth_since_baseline_mb and stats.growth_since_baseline_mb > GROWTH_WARNING_THRESHOLD_MB):
                            should_warn = True
                            warn_msg = f"+{stats.growth_since_baseline_percent:.1f}% (+{stats.growth_since_baseline_mb or 0:.1f} MB) from baseline"
                    elif stats.growth_since_baseline_mb and stats.growth_since_baseline_mb > 100:
                        should_warn = True
                        warn_msg = f"+{stats.growth_since_baseline_mb:.1f} MB since watcher started"

                    if should_warn:
                        logger.warning(
                            "[MEMORY WATCHER] Significant growth detected: %s. "
                            "Current: %.1f MB, Peak: %.1f MB",
                            warn_msg,
                            current_mb,
                            peak / (1024 * 1024)
                        )
                        if stats.top_growers:
                            for i, grower in enumerate(stats.top_growers[:5]):
                                logger.warning(
                                    "[MEMORY WATCHER] Top grower #%d: +%.1f KB in %s",
                                    i + 1,
                                    grower.get("size_diff_kb", 0),
                                    grower.get("location", "unknown")
                                )

                    _previous_snapshot = current_snapshot

                except Exception as e:
                    logger.error("[MEMORY WATCHER] Loop error: %s", e)

        _watcher_thread = threading.Thread(
            target=_watcher_loop,
            daemon=True,
            name="Memory-Watcher",
        )
        _watcher_thread.start()
        logger.info("[MEMORY WATCHER] Background thread started (interval=%d min)", check_interval_minutes)
        return _watcher_thread


def stop_memory_watcher():
    """Stop the memory watcher and tracemalloc."""
    global _watcher_running
    with _watcher_lock:
        _watcher_running = False
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    logger.info("[MEMORY WATCHER] Stopped")


def _get_stats_internal(
    snapshot: tracemalloc.Snapshot,
    current: int,
    peak: int
) -> MemoryStats:
    """Internal helper to compute memory stats."""
    global _baseline_snapshot, _baseline_bytes, _watcher_running

    current_mb = current / (1024 * 1024)
    peak_mb = peak / (1024 * 1024)

    baseline_mb = None
    growth_pct = None
    growth_mb = None
    top_growers = []

    if _watcher_running:
        baseline_mb = _baseline_bytes / (1024 * 1024)
        growth_mb = current_mb - baseline_mb
        if _baseline_bytes > 0:
            growth_pct = (growth_mb / baseline_mb) * 100
        else:
            growth_pct = None

    if _baseline_snapshot and _previous_snapshot:
        try:
            diff = snapshot.compare_to(_previous_snapshot, 'lineno')
            for stat in diff[:10]:
                if stat.size_diff > 0:
                    top_growers.append({
                        "size_diff_kb": round(stat.size_diff / 1024, 2),
                        "size_diff_sign": "+",
                        "count_diff": stat.count_diff,
                        "location": str(stat.traceback),
                    })
        except Exception:
            pass

    return MemoryStats(
        current_allocated_mb=round(current_mb, 2),
        peak_allocated_mb=round(peak_mb, 2),
        baseline_allocated_mb=round(baseline_mb, 2) if baseline_mb is not None else None,
        growth_since_baseline_percent=round(growth_pct, 1) if growth_pct is not None else None,
        growth_since_baseline_mb=round(growth_mb, 2) if growth_mb is not None else None,
        top_growers=top_growers,
        gc_counts=gc.get_count(),
        process_rss_mb=round(_get_process_rss_mb(), 2) if _get_process_rss_mb() else None,
    )


def get_memory_stats() -> Dict[str, Any]:
    """
    Get current memory statistics.
    
    Returns:
        Dictionary with current allocation, growth, and top allocators.
    """
    if not tracemalloc.is_tracing():
        return {
            "error": "tracemalloc not running",
            "hint": "Call start_memory_watcher() first",
        }

    snapshot = tracemalloc.take_snapshot()
    current, peak = tracemalloc.get_traced_memory()
    stats = _get_stats_internal(snapshot, current, peak)

    return {
        "current_allocated_mb": stats.current_allocated_mb,
        "peak_allocated_mb": stats.peak_allocated_mb,
        "baseline_allocated_mb": stats.baseline_allocated_mb,
        "growth_since_baseline_percent": stats.growth_since_baseline_percent,
        "growth_since_baseline_mb": stats.growth_since_baseline_mb,
        "gc_counts": stats.gc_counts,
        "process_rss_mb": stats.process_rss_mb,
        "top_growers_since_last_check": stats.top_growers[:5],
        "history": _memory_log[-10:],
    }


def is_tracing() -> bool:
    """Return True if tracemalloc is currently tracing."""
    return tracemalloc.is_tracing()
