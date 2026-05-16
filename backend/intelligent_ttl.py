"""
intelligent_ttl.py — Adaptive TTL Based on Volatility & Context
================================================================
Adjusts refresh intervals based on:
- Beta (stock volatility)
- Earnings calendar
- Market hours
- Sector risk

Formula: effective_ttl = base_ttl / sqrt(beta) * earnings_adjustment * market_hours_adjustment
"""

import time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Base TTLs (in seconds)
BASE_PRICE_TTL = 1800       # 30 min (floor)
BASE_FUNDAMENTALS_TTL = 86400  # 24 hours
BASE_HISTORY_TTL = 43200   # 12 hours

# Beta adjustment constants
HIGH_BETA_THRESHOLD = 1.5
LOW_BETA_THRESHOLD = 0.8
MAX_BETA_SCALING = 2.0  # Max multiplier (prevents extreme values)

# Earnings adjustment
EARNINGS_WINDOW_DAYS = 7  # 1 week before/after earnings
EARNINGS_TTL_DIVISOR = 2  # Halve TTL during earnings window

# Market hours adjustment
MARKET_HOURS_TTL_DIVISOR = 0.5  # Shorter TTL during market hours
OFF_HOURS_TTL_MULTIPLIER = 2.0  # Longer TTL off-hours

# Cache for earnings dates
_earnings_cache: Dict[str, float] = {}  # symbol -> unix timestamp of next earnings
_earnings_cache_time: float = 0
EARNINGS_CACHE_TTL = 86400  # Refresh earnings cache once per day


@dataclass
class TTLConfig:
    """Configuration for effective TTL based on context."""
    base_ttl: int
    effective_ttl: int
    adjustments: Dict[str, float]  # What adjustments were applied
    reason: str  # Human-readable explanation


def get_adjusted_ttl(
    symbol: str,
    data_type: str,
    beta: Optional[float] = None,
    sector: Optional[str] = None,
    price: Optional[float] = None
) -> TTLConfig:
    """
    Calculate effective TTL for a symbol/data_type combination.
    
    Args:
        symbol: Ticker symbol
        data_type: Type of data ('price', 'fundamentals', 'history')
        beta: Stock beta (volatility measure)
        sector: Stock sector (for sector-specific adjustments)
        price: Current price (for high-price stock adjustment)
    
    Returns:
        TTLConfig with effective TTL and adjustment details
    """
    # Select base TTL
    if data_type == "price":
        base_ttl = BASE_PRICE_TTL
    elif data_type == "fundamentals":
        base_ttl = BASE_FUNDAMENTALS_TTL
    elif data_type == "history":
        base_ttl = BASE_HISTORY_TTL
    else:
        base_ttl = BASE_PRICE_TTL
    
    effective_ttl = float(base_ttl)
    adjustments = {}
    reasons = []
    
    # 1. Beta adjustment (volatility-based)
    if beta is not None and beta > 0:
        beta_scaling = _get_beta_scaling(beta)
        if beta_scaling != 1.0:
            effective_ttl /= beta_scaling
            adjustments["beta_scaling"] = beta_scaling
            reasons.append(f"Beta={beta:.2f} → scaling={beta_scaling:.2f}")
    
    # 2. Earnings week adjustment
    earnings_adjustment = get_earnings_adjustment(symbol)
    if earnings_adjustment != 1.0:
        effective_ttl /= earnings_adjustment
        adjustments["earnings_adjustment"] = earnings_adjustment
        reasons.append(f"Earnings window: {earnings_adjustment:.1f}x")
    
    # 3. Market hours adjustment
    if _is_market_hours():
        effective_ttl *= MARKET_HOURS_TTL_DIVISOR
        adjustments["market_hours"] = MARKET_HOURS_TTL_DIVISOR
        reasons.append("Market hours (shorter TTL)")
    else:
        effective_ttl *= OFF_HOURS_TTL_MULTIPLIER
        adjustments["off_hours"] = OFF_HOURS_TTL_MULTIPLIER
        reasons.append("Off-hours (longer TTL)")
    
    # 4. Sector-specific adjustments
    sector_adjustment = get_sector_adjustment(sector)
    if sector_adjustment != 1.0:
        effective_ttl *= sector_adjustment
        adjustments["sector_adjustment"] = sector_adjustment
        reasons.append(f"Sector={sector}: {sector_adjustment:.1f}x")
    
    # 5. High-price stock (less critical for intraday moves)
    if price is not None and price > 500:
        effective_ttl *= 1.5  # Higher-priced stocks less volatile intraday
        adjustments["high_price"] = 1.5
        reasons.append(f"High price=${price:.0f} (1.5x)")
    
    # 6. Per-ticker jitter: spread refreshes across the day so tickers
    # fetched at the same time don't all expire simultaneously.
    # Uses a deterministic hash of the symbol so each ticker's offset
    # is consistent across restarts (0.7x – 1.3x of the current TTL).
    jitter = 0.7 + (hash(symbol + "_" + data_type) % 6001) / 10000.0
    effective_ttl *= jitter
    adjustments["jitter"] = jitter
    reasons.append(f"Jitter: {jitter:.2f}x")
    
    # Enforce minimum TTL (never shorter than 15 min for price)
    min_ttl = 900 if data_type == "price" else 3600
    effective_ttl = max(effective_ttl, min_ttl)
    
    # Enforce maximum TTL (never longer than 48 hours)
    effective_ttl = min(effective_ttl, 172800)
    
    return TTLConfig(
        base_ttl=base_ttl,
        effective_ttl=int(effective_ttl),
        adjustments=adjustments,
        reason="; ".join(reasons) if reasons else "Base TTL"
    )


def _get_beta_scaling(beta: float) -> float:
    """
    Calculate TTL scaling factor based on beta.
    
    Formula: scaling = sqrt(beta)
    - Beta 1.0 → scaling 1.0 (no change)
    - Beta 2.0 → scaling 1.41 (40% shorter TTL)
    - Beta 0.5 → scaling 0.71 (30% longer TTL)
    
    Clamped between 0.5 and MAX_BETA_SCALING.
    """
    if beta <= 0:
        return 1.0
    
    scaling = (beta ** 0.5)  # Square root
    
    # Clamp to reasonable bounds
    scaling = max(0.5, min(scaling, MAX_BETA_SCALING))
    
    return scaling


def get_earnings_adjustment(symbol: str) -> float:
    """
    Check if symbol is in earnings window and adjust TTL accordingly.
    
    Returns:
        1.0 if not in earnings window
        0.5 (or EARNINGS_TTL_DIVISOR) if within 7 days of earnings
    """
    global _earnings_cache, _earnings_cache_time
    
    # Refresh cache daily
    if time.time() - _earnings_cache_time > EARNINGS_CACHE_TTL:
        _earnings_cache.clear()
        _earnings_cache_time = time.time()
    
    # Check cache
    if symbol in _earnings_cache:
        earnings_time = _earnings_cache[symbol]
        if _is_within_earnings_window(earnings_time):
            return 1.0 / EARNINGS_TTL_DIVISOR  # Halve TTL
        return 1.0
    
    # For unknown symbols, assume not in earnings window
    # (Could integrate with earnings calendar API for production)
    return 1.0


def set_next_earnings(symbol: str, timestamp: float):
    """
    Set the next earnings date for a symbol.
    Called by data ingestion when earnings date is found.
    """
    global _earnings_cache
    _earnings_cache[symbol] = timestamp
    _earnings_cache_time = time.time()


def _is_within_earnings_window(earnings_timestamp: float) -> bool:
    """Check if current time is within earnings window."""
    now = time.time()
    window_start = earnings_timestamp - (EARNINGS_WINDOW_DAYS * 86400)
    window_end = earnings_timestamp + (EARNINGS_WINDOW_DAYS * 86400)
    return window_start <= now <= window_end


def get_sector_adjustment(sector: Optional[str]) -> float:
    """
    Apply sector-specific TTL adjustments.
    
    Higher-risk/cyclical sectors get shorter TTLs:
    - Technology: 0.9 (fast-moving)
    - Financials: 0.9 (rate-sensitive)
    - Energy: 0.8 (commodity-sensitive)
    - Healthcare: 1.1 (stable)
    - Consumer Staples: 1.2 (defensive)
    """
    if not sector:
        return 1.0
    
    sector_adjustments = {
        "Technology": 0.9,
        "Information Technology": 0.9,
        "Financials": 0.9,
        "Financial": 0.9,
        "Energy": 0.8,
        "Materials": 0.85,
        "Industrials": 0.95,
        "Healthcare": 1.1,
        "Consumer Staples": 1.2,
        "Consumer Discretionary": 0.95,
        "Utilities": 1.3,  # Very stable
        "Real Estate": 1.2,  # Stable dividends
        "Communication Services": 0.95,
    }
    
    return sector_adjustments.get(sector, 1.0)


def _is_market_hours() -> bool:
    """Check if US market is open (Mon-Fri, 9:30 AM - 4:00 PM ET)."""
    now = datetime.now(timezone.utc)
    hour_et = (now.hour - 4) % 24  # DST offset approximation
    return now.weekday() < 5 and 13 <= hour_et < 21


def is_fresh(symbol: str, data_type: str, fetched_at: float, 
             beta: Optional[float] = None, sector: Optional[str] = None) -> Tuple[bool, str]:
    """
    Check if data is fresh using intelligent TTL.
    
    Returns:
        (is_fresh, reason)
    """
    ttl_config = get_adjusted_ttl(symbol, data_type, beta, sector)
    age = time.time() - fetched_at
    
    is_fresh = age < ttl_config.effective_ttl
    reason = f"Age: {age:.0f}s, TTL: {ttl_config.effective_ttl}s ({ttl_config.reason})"
    
    return is_fresh, reason


def get_effective_ttl_for_symbol(
    symbol: str,
    data_type: str,
    beta: Optional[float] = None,
    sector: Optional[str] = None,
    price: Optional[float] = None
) -> int:
    """
    Simple interface: get effective TTL for a symbol.
    
    Usage:
        ttl = get_effective_ttl_for_symbol("AAPL", "price", beta=1.2, sector="Technology")
        if age > ttl:
            # Data is stale, consider refresh
    """
    config = get_adjusted_ttl(symbol, data_type, beta, sector, price)
    return config.effective_ttl


def calculate_refresh_priority(symbol: str, data_type: str,
                               beta: Optional[float] = None,
                               sector: Optional[str] = None) -> int:
    """
    Calculate refresh priority (1=high, 2=medium, 3=low).
    
    Higher priority for:
    - High beta (volatile stocks)
    - In earnings window
    - During market hours
    """
    priority = 2  # Default medium
    
    # Earnings window = high priority
    if get_earnings_adjustment(symbol) < 1.0:
        priority = 1
    
    # High beta = higher priority
    if beta and beta > 1.5:
        priority = min(priority, 1)
    elif beta and beta < 0.7:
        priority = max(priority, 3)
    
    # During market hours = higher priority for price data
    if data_type == "price" and _is_market_hours():
        priority = min(priority, 1)
    
    return priority


# Pre-computed TTL for common scenarios (cache for performance)
_TTL_CACHE: Dict[str, int] = {}
_TTL_CACHE_TIME: float = 0
_TTL_CACHE_MAX_AGE = 300  # 5 minutes


def get_cached_ttl(symbol: str, data_type: str) -> int:
    """
    Get effective TTL with caching for performance.
    Cache invalidated every 5 minutes or when earnings data changes.
    """
    global _TTL_CACHE, _TTL_CACHE_TIME
    
    cache_key = f"{symbol}:{data_type}"
    
    # Check if cache is valid
    if time.time() - _TTL_CACHE_TIME > _TTL_CACHE_MAX_AGE:
        _TTL_CACHE.clear()
        _TTL_CACHE_TIME = time.time()
    
    if cache_key in _TTL_CACHE:
        return _TTL_CACHE[cache_key]
    
    # Calculate and cache
    ttl = get_effective_ttl_for_symbol(symbol, data_type)
    _TTL_CACHE[cache_key] = ttl
    
    return ttl


def invalidate_ttl_cache():
    """Invalidate the TTL cache (call after updating earnings data)."""
    global _TTL_CACHE, _TTL_CACHE_TIME
    _TTL_CACHE.clear()
    _TTL_CACHE_TIME = time.time()
    logger.debug("TTL cache invalidated")