"""
dynamic_universe.py
====================
Static-first, non-blocking dynamic ticker universe.

Architecture
------------
1. Every API call gets a response in < 1ms — always returns SECTOR_STOCKS
   (static) or the last scored dynamic universe from cache.
2. On startup (and on a 24h schedule), a background asyncio task kicks off
   scoring. It uses:
     • yf.download()    — bulk 1-year price history in ONE request (~15s)
     • yahooquery async — bulk fundamentals (market cap, ROE, EPS, volume) (~20s)
3. Once scoring finishes, results land in _LIVE_CACHE (in-memory) and
   sector_cache.json (disk). All subsequent calls serve live data with
   the ⚡ Live Universe badge.

Scoring (0-100 per ticker)
--------------------------
  Market Cap  30 pts  log-normalised [1B, 3T]
  Momentum    30 pts  52-week return clamped [-50%, +100%]
  Quality     25 pts  ROE threshold tiers + positive EPS
  Liquidity   15 pts  log-normalised avg volume [100k, 100M]

Public API
----------
get_sector_stocks_cached(n=25)  → dict  (INSTANT — never blocks)
trigger_background_score(n=25)  → fire-and-forget coroutine
get_sector_meta(sector=None)    → dict  {is_dynamic, scored_at, ttl_hours, …}
write_disk_cache(data)          → persist scored universe to disk
"""

import asyncio
import yfinance as yf
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from cache_utils import sanitize_metric

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Disk cache path
# ---------------------------------------------------------------------------
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "sector_cache.json")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_LIVE_CACHE: Dict[str, dict] = {}          # populated by background task
_LIVE_CACHE_TIME: Optional[float] = None   # epoch when cache was filled
_SCORE_TASK_RUNNING: bool = False          # guard against concurrent runs

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
    Download 1-year monthly prices for ALL tickers using data_client.
    Returns { symbol: 52wk_return_decimal }. Misses default to 0.
    """
    from data_client import get_price_history
    import concurrent.futures

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
    and sector for all tickers in batch.
    Returns { symbol: {market_cap, avg_volume, roe, eps, sector} }
    """
    from data_client import get_fundamentals, get_price_live
    import concurrent.futures

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
# Core scoring logic (runs in background thread → called via asyncio executor)
# ---------------------------------------------------------------------------

def _run_scoring(candidates: List[str], n: int) -> Dict[str, dict]:
    """
    Synchronous scoring — runs in a thread pool via asyncio.to_thread().
    Returns the full sector dict (same shape as SECTOR_STOCKS but with scores).
    """
    from screener import SECTOR_STOCKS  # noqa: PLC0415 (avoid circular at module level)

    logger.info("[DynUniverse] Scoring %d candidates …", len(candidates))
    t0 = time.time()

    # Step 1 — bulk price/momentum in one yfinance request
    momentum_map = _bulk_momentum(candidates)
    logger.info("[DynUniverse] Momentum fetched in %.1fs (%d tickers)",
                time.time() - t0, len(momentum_map))

    # Step 2 — bulk fundamentals via yahooquery (async under the hood)
    fund_map = _bulk_fundamentals(candidates)
    logger.info("[DynUniverse] Fundamentals fetched in %.1fs (%d tickers)",
                time.time() - t0, len(fund_map))

    # Step 3 — score and bucket by sector
    sector_buckets: Dict[str, list] = {}  # sector → [(score, symbol)]
    now_str = datetime.now(timezone.utc).isoformat()

    for sym in candidates:
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
            result[sector] = {"tickers": top, "is_dynamic": True, "scored_at": now_str}
            logger.info("[DynUniverse] %s → %d dynamic tickers (top=%.1f)",
                        sector, len(top), bucket[0][0])
        else:
            # Not enough scored tickers → fall back to static for this sector
            result[sector] = {
                "tickers": static_tickers,
                "is_dynamic": False,
                "scored_at": now_str,
            }
            logger.info("[DynUniverse] %s → static fallback (%d tickers)", sector, len(static_tickers))

    logger.info("[DynUniverse] Scoring complete in %.1fs", time.time() - t0)
    return result


# ---------------------------------------------------------------------------
# Background async task
# ---------------------------------------------------------------------------

async def background_score_all(n: int = 25) -> None:
    """
    Fire-and-forget coroutine.  Runs _run_scoring in a thread pool so the
    event loop never blocks.  Writes results to _LIVE_CACHE and sector_cache.json.
    """
    global _LIVE_CACHE, _LIVE_CACHE_TIME, _SCORE_TASK_RUNNING

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
        result = await asyncio.to_thread(_run_scoring, candidates, n)
        _LIVE_CACHE = result
        _LIVE_CACHE_TIME = time.time()
        write_disk_cache(result)
        logger.info("[DynUniverse] Background scoring complete — %d sectors live", len(result))
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
      2. Disk cache (sector_cache.json, if < 26h old)
      3. Static SECTOR_STOCKS fallback

    Never makes network calls. Call trigger_background_score() separately.
    """
    from screener import SECTOR_STOCKS  # noqa: PLC0415

    # 1. In-memory
    if _LIVE_CACHE and _LIVE_CACHE_TIME and (time.time() - _LIVE_CACHE_TIME) < 90000:
        return _LIVE_CACHE

    # 2. Disk cache
    disk = _load_disk_cache()
    if disk:
        return disk

    # 3. Static fallback
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
# Disk cache helpers
# ---------------------------------------------------------------------------

def write_disk_cache(data: Dict[str, dict]) -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
        logger.info("[DynUniverse] Wrote disk cache → %s", _CACHE_FILE)
    except Exception as exc:
        logger.warning("[DynUniverse] Could not write disk cache: %s", exc)


def _load_disk_cache() -> Optional[Dict[str, dict]]:
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        age_h = (time.time() - os.path.getmtime(_CACHE_FILE)) / 3600
        if age_h > 26:
            logger.info("[DynUniverse] Disk cache stale (%.1fh), ignoring", age_h)
            return None
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        logger.info("[DynUniverse] Loaded disk cache (%.1fh old)", age_h)
        return data
    except Exception as exc:
        logger.warning("[DynUniverse] Could not read disk cache: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Backwards-compat shim — keep old callers working during transition
# ---------------------------------------------------------------------------

def get_dynamic_sector_stocks(n: int = 25) -> Dict[str, dict]:
    """Deprecated shim — use get_sector_stocks_cached() instead."""
    return get_sector_stocks_cached(n=n)
