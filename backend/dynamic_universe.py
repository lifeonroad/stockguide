"""
dynamic_universe.py
===================
Static-first, non-blocking dynamic ticker universe.

Architecture
------------
1. Every API call gets a response in < 1ms — always returns SECTOR_STOCKS
   (static) or the last scored dynamic universe from cache.
2. On startup (and on a 24h schedule), a background asyncio task kicks off
   chunked scoring. It processes tickers in batches of ~100 with staggered
   delays to reduce burst load on external APIs.
3. Once scoring finishes, results land in _LIVE_CACHE (in-memory) and
   per-sector disk cache files. All subsequent calls serve live data with
   the ⚡ Live Universe badge.

Scoring (0-100 per ticker)
--------------------------
  Market Cap  30 pts  log-normalised [1B, 3T]
  Momentum    30 pts  52-week return clamped [-50%, +100%]
  Quality     25 pts  ROE threshold tiers + positive EPS
  Liquidity   15 pts  log-normalised avg volume [100k, 100M]

Chunked Scoring
---------------
  Instead of fetching all ~500 tickers at once, we split into chunks of 100.
  Each chunk takes ~30-45s to process, with a 5s delay between chunks.
  Results are merged incrementally — sectors become live as they're scored.

Public API
----------
get_sector_stocks_cached(n=25)  → dict  (INSTANT — never blocks)
trigger_background_score(n=25)  → fire-and-forget coroutine
get_sector_meta(sector=None)    → dict  {is_dynamic, scored_at, ttl_hours, …}
write_disk_cache(data)          → persist scored universe to disk (per-sector)
"""

import asyncio
import json
import logging
import math
import os
import time
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from cache_utils import sanitize_metric

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Disk cache directory (per-sector granularity)
# ---------------------------------------------------------------------------
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "sector_cache")
Path(_CACHE_DIR).mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_LIVE_CACHE: Dict[str, dict] = {}          # populated by background task
_LIVE_CACHE_TIME: Optional[float] = None   # epoch when cache was filled
_SCORE_TASK_RUNNING: bool = False          # guard against concurrent runs
_SECTOR_SCORED_AT: Dict[str, float] = {}   # per-sector timestamps

# Chunking configuration
CHUNK_SIZE = 100          # tickers per chunk
CHUNK_DELAY = 5           # seconds between chunks

# ---------------------------------------------------------------------------
# GICS sector mapping  (our canonical key → yfinance sector string)
# ---------------------------------------------------------------------------
GICS_SECTOR_MAP: Dict[str, str] = {
    "Technology": "Technology",
    "Financials": "Financial Services",
    "Healthcare": "Healthcare",
    "Energy": "Energy",
    "Consumer Discretionary": "Consumer Cyclical",
    "Industrials": "Industrials",
    "Consumer Staples": "Consumer Defensive",
    "Materials": "Basic Materials",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Communication Services": "Communication Services",
}
_YF_TO_OURS: Dict[str, str] = {v: k for k, v in GICS_SECTOR_MAP.items()}

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _log_norm(value: Optional[float], lo: float, hi: float) -> float:
    if not value or value <= 0:
        return 0.0
    try:
        v = math.log(max(value, lo))
        return max(0.0, min(1.0, (v - math.log(lo)) / (math.log(hi) - math.log(lo))))
    except Exception:
        return 0.0


def _score(market_cap: float, momentum: float, roe: float,
           eps: float, avg_vol: float) -> float:
    cap_score = _log_norm(market_cap, 1e9, 3e12) * 30
    mom_clamped = max(-0.5, min(1.0, momentum))
    mom_score = ((mom_clamped + 0.5) / 1.5) * 30
    quality = 0
    if roe > 0.20:
        quality = 15
    elif roe > 0.12:
        quality = 10
    elif roe > 0.05:
        quality = 5
    if eps > 0:
        quality += 10
    liq_score = _log_norm(avg_vol, 1e5, 1e8) * 15
    return round(cap_score + mom_score + quality + liq_score, 2)


# ---------------------------------------------------------------------------
# FAST bulk data fetchers
# ---------------------------------------------------------------------------

def _bulk_momentum(tickers: List[str]) -> Dict[str, float]:
    """
    Download 1-year monthly prices for a batch of tickers using data_client.
    Returns { symbol: 52wk_return_decimal }. Misses default to 0.
    """
    from data_client import get_price_history

    if not tickers:
        return {}
    
    result = {}
    
    def fetch_mom(sym):
        try:
            hist = get_price_history(sym, days=252)
            if hist is not None and not hist.empty and len(hist) > 2:
                val = ((hist['close'].iloc[-1] - hist['close'].iloc[0]) / hist['close'].iloc[0]) * 100
                return sym, sanitize_metric(val, 0)
        except Exception:
            pass
        return sym, 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_mom, sym): sym for sym in tickers}
        for future in concurrent.futures.as_completed(futures):
            sym, val = future.result()
            if val != 0.0:
                result[sym] = val

    return result


def _bulk_fundamentals(tickers: List[str]) -> Dict[str, dict]:
    """
    Use data_client to fetch market_cap, avg_volume, ROE, EPS,
    and sector for a batch of tickers.
    Returns { symbol: {market_cap, avg_volume, roe, eps, sector} }
    """
    from data_client import get_fundamentals, get_price_live

    if not tickers:
        return {}

    out: Dict[str, dict] = {}
    
    def fetch_fund(sym):
        try:
            info = get_fundamentals(sym)
            live = get_price_live(sym)
            if not info: return sym, None
            
            return sym, {
                "market_cap": sanitize_metric(info.get("marketCap"), 0),
                "avg_volume": sanitize_metric(live.get("volume"), 0),
                "roe": sanitize_metric(info.get("returnOnEquity"), 0),
                "eps": sanitize_metric(info.get("trailingEps"), 0),
                "sector": info.get("sector", ""),
            }
        except Exception:
            return sym, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_fund, sym): sym for sym in tickers}
        for future in concurrent.futures.as_completed(futures):
            sym, data = future.result()
            if data:
                out[sym] = data
                
    return out


# ---------------------------------------------------------------------------
# Chunked scoring (runs in background thread)
# ---------------------------------------------------------------------------

def _run_chunked_scoring(candidates: List[str], n: int) -> None:
    """
    Score candidates in chunks, merging results incrementally.
    Each chunk writes to the disk cache so partial results are available.
    """
    from screener import SECTOR_STOCKS  # noqa: PLC0415

    t0 = time.time()
    chunks = [candidates[i:i + CHUNK_SIZE] for i in range(0, len(candidates), CHUNK_SIZE)]
    logger.info("[DynUniverse] Starting chunked scoring: %d candidates in %d chunks",
                len(candidates), len(chunks))

    all_momentum: Dict[str, float] = {}
    all_fundamentals: Dict[str, dict] = {}

    for i, chunk in enumerate(chunks):
        chunk_start = time.time()
        logger.info("[DynUniverse] Processing chunk %d/%d (%d tickers)",
                    i + 1, len(chunks), len(chunk))

        # Fetch momentum and fundamentals for this chunk
        chunk_momentum = _bulk_momentum(chunk)
        chunk_fundamentals = _bulk_fundamentals(chunk)

        all_momentum.update(chunk_momentum)
        all_fundamentals.update(chunk_fundamentals)

        logger.info("[DynUniverse] Chunk %d complete in %.1fs (momentum=%d, fundamentals=%d)",
                    i + 1, time.time() - chunk_start, len(chunk_momentum), len(chunk_fundamentals))

        # Merge and write partial results after each chunk
        _merge_and_write(all_momentum, all_fundamentals, candidates, n)

        # Stagger chunks to reduce burst load
        if i < len(chunks) - 1:
            logger.info("[DynUniverse] Waiting %ds before next chunk...", CHUNK_DELAY)
            time.sleep(CHUNK_DELAY)

    total_time = time.time() - t0
    logger.info("[DynUniverse] Chunked scoring complete in %.1fs", total_time)


def _merge_and_write(
    momentum_map: Dict[str, float],
    fund_map: Dict[str, dict],
    all_candidates: List[str],
    n: int,
) -> Dict[str, dict]:
    """
    Score all available data and write to in-memory + disk cache.
    Returns the full sector dict.
    """
    from screener import SECTOR_STOCKS  # noqa: PLC0415

    sector_buckets: Dict[str, list] = {}
    now_str = datetime.now(timezone.utc).isoformat()
    now_ts = time.time()

    # Score only candidates that have fundamentals data
    scored_candidates = [sym for sym in all_candidates if sym in fund_map]

    for sym in scored_candidates:
        fd = fund_map.get(sym, {})
        sector_raw = fd.get("sector", "")
        our_sector = _YF_TO_OURS.get(sector_raw)
        if not our_sector:
            continue

        sc = _score(
            market_cap=fd.get("market_cap", 0),
            momentum=momentum_map.get(sym, 0),
            roe=fd.get("roe", 0),
            eps=fd.get("eps", 0),
            avg_vol=fd.get("avg_volume", 0),
        )
        sector_buckets.setdefault(our_sector, []).append((sc, sym))

    result: Dict[str, dict] = {}
    for sector, static_tickers in SECTOR_STOCKS.items():
        bucket = sector_buckets.get(sector, [])
        bucket.sort(key=lambda x: x[0], reverse=True)
        top = [sym for _, sym in bucket[:n]]

        if len(top) >= 5:
            sector_data = {"tickers": top, "is_dynamic": True, "scored_at": now_str}
            result[sector] = sector_data
            _SECTOR_SCORED_AT[sector] = now_ts
            logger.info("[DynUniverse] %s → %d dynamic tickers (top=%.1f)",
                        sector, len(top), bucket[0][0] if bucket else 0)
        else:
            # If we haven't scored enough for this sector yet, check disk cache
            disk_sector = _load_sector_disk_cache(sector)
            if disk_sector and disk_sector.get("is_dynamic"):
                result[sector] = disk_sector
            else:
                result[sector] = {
                    "tickers": static_tickers,
                    "is_dynamic": False,
                    "scored_at": now_str,
                }

    # Update in-memory cache incrementally
    global _LIVE_CACHE, _LIVE_CACHE_TIME
    _LIVE_CACHE.update(result)
    _LIVE_CACHE_TIME = now_ts

    # Write per-sector disk caches
    for sector, data in result.items():
        write_sector_disk_cache(sector, data)

    return result


# ---------------------------------------------------------------------------
# Background async task
# ---------------------------------------------------------------------------

async def background_score_all(n: int = 25) -> None:
    """
    Fire-and-forget coroutine. Runs chunked scoring in a thread pool so the
    event loop never blocks.
    """
    global _SCORE_TASK_RUNNING

    if _SCORE_TASK_RUNNING:
        return
    _SCORE_TASK_RUNNING = True

    try:
        from universe import SP500_TOP  # noqa: PLC0415
        candidates = list(set(SP500_TOP))
    except Exception:
        logger.warning("[DynUniverse] Could not load SP500_TOP, using empty candidates")
        candidates = []

    try:
        await asyncio.to_thread(_run_chunked_scoring, candidates, n)
        logger.info("[DynUniverse] Background scoring complete — %d sectors in cache", len(_LIVE_CACHE))
    except Exception as exc:
        logger.error("[DynUniverse] Background scoring failed: %s", exc)
    finally:
        _SCORE_TASK_RUNNING = False


# ---------------------------------------------------------------------------
# Public: INSTANT read (never blocks)
# ---------------------------------------------------------------------------

def get_sector_stocks_cached(n: int = 25) -> Dict[str, dict]:
    """
    Returns the sector universe immediately.

    Priority order:
      1. In-memory live cache (if < 25h old)
      2. Per-sector disk cache (if < 26h old)
      3. Static SECTOR_STOCKS fallback

    Never makes network calls. Call trigger_background_score() separately.
    """
    from screener import SECTOR_STOCKS  # noqa: PLC0415

    # 1. In-memory
    if _LIVE_CACHE and _LIVE_CACHE_TIME and (time.time() - _LIVE_CACHE_TIME) < 90000:
        return _LIVE_CACHE

    # 2. Per-sector disk cache (granular fallback)
    result = {}
    all_stale = True
    for sector, static_tickers in SECTOR_STOCKS.items():
        disk = _load_sector_disk_cache(sector)
        if disk:
            result[sector] = disk
            all_stale = False
        else:
            now_str = datetime.now(timezone.utc).isoformat()
            result[sector] = {
                "tickers": static_tickers,
                "is_dynamic": False,
                "scored_at": now_str,
            }

    if not all_stale:
        return result

    # 3. Full static fallback
    now_str = datetime.now(timezone.utc).isoformat()
    return {
        sector: {"tickers": tickers, "is_dynamic": False, "scored_at": now_str}
        for sector, tickers in SECTOR_STOCKS.items()
    }


def trigger_background_score(n: int = 25) -> None:
    """
    Schedule background_score_all() on the running event loop if not already running.
    Safe to call from sync context (e.g., request handlers).
    """
    if _SCORE_TASK_RUNNING:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(background_score_all(n))
    except Exception as exc:
        logger.debug("[DynUniverse] Could not schedule background score: %s", exc)


# ---------------------------------------------------------------------------
# Metadata helper
# ---------------------------------------------------------------------------

def get_sector_meta(sector: Optional[str] = None) -> dict:
    """Return badge metadata without triggering any network calls."""
    universe = get_sector_stocks_cached()

    if sector:
        entry = universe.get(sector, {})
        return {
            "is_dynamic": entry.get("is_dynamic", False),
            "scored_at": entry.get("scored_at"),
            "ttl_hours": 24,
        }

    all_dynamic = all(v.get("is_dynamic", False) for v in universe.values())
    any_dynamic = any(v.get("is_dynamic", False) for v in universe.values())
    latest = max((v.get("scored_at") or "" for v in universe.values()), default=None)
    return {
        "is_dynamic": all_dynamic,
        "partially_dynamic": any_dynamic and not all_dynamic,
        "scored_at": latest or None,
        "ttl_hours": 24,
    }


# ---------------------------------------------------------------------------
# Disk cache helpers (per-sector granularity)
# ---------------------------------------------------------------------------

def _sector_cache_file(sector: str) -> str:
    """Returns the path to a sector's cache file."""
    safe_name = sector.replace(" ", "_").lower()
    return os.path.join(_CACHE_DIR, f"{safe_name}.json")


def write_sector_disk_cache(sector: str, data: dict) -> None:
    """Write a single sector's scored data to disk."""
    try:
        path = _sector_cache_file(sector)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as exc:
        logger.warning("[DynUniverse] Could not write sector cache for %s: %s", sector, exc)


def _load_sector_disk_cache(sector: str) -> Optional[dict]:
    """Load a single sector's cached data from disk (if < 26h old)."""
    try:
        path = _sector_cache_file(sector)
        if not os.path.exists(path):
            return None
        age_h = (time.time() - os.path.getmtime(path)) / 3600
        if age_h > 26:
            return None
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        logger.debug("[DynUniverse] Could not read sector cache for %s: %s", sector, exc)
        return None


def write_disk_cache(data: Dict[str, dict]) -> None:
    """Write all sectors to disk (legacy compat — calls per-sector writer)."""
    for sector, sector_data in data.items():
        write_sector_disk_cache(sector, sector_data)
    logger.info("[DynUniverse] Wrote disk cache for %d sectors → %s", len(data), _CACHE_DIR)


def _load_disk_cache() -> Optional[Dict[str, dict]]:
    """Load all sectors from per-sector disk cache (legacy compat)."""
    from screener import SECTOR_STOCKS  # noqa: PLC0415
    result = {}
    any_loaded = False
    for sector in SECTOR_STOCKS:
        data = _load_sector_disk_cache(sector)
        if data:
            result[sector] = data
            any_loaded = True
    return result if any_loaded else None


# ---------------------------------------------------------------------------
# Backwards-compat shim — keep old callers working during transition
# ---------------------------------------------------------------------------

def get_dynamic_sector_stocks(n: int = 25) -> Dict[str, dict]:
    """Deprecated shim — use get_sector_stocks_cached() instead."""
    return get_sector_stocks_cached(n=n)
