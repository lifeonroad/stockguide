"""
rate_limiter.py — Conservative Fetch Rate Limiting
===================================================
Prevents yfinance rate limiting by enforcing:
- MIN_REFRESH_INTERVAL: 1800s (30 min) between same ticker fetches
- DAILY_FETCH_LIMIT: 48 fetches per ticker per day
- BULK_FETCH_BATCH: 10 tickers per bulk request

All timestamps in Unix epoch seconds.
"""

import time
import threading
from datetime import datetime, date
from typing import Tuple, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Conservative limits to prevent DOS
MIN_REFRESH_INTERVAL = 1800   # 30 min - never fetch same ticker more than 48x/day
DAILY_FETCH_LIMIT = 48         # Max fetches per ticker per day
BULK_FETCH_BATCH = 10          # Max tickers per bulk request


@dataclass
class FetchRecord:
    """Record of a fetch attempt for a symbol/data_type combo."""
    symbol: str
    data_type: str
    timestamp: float
    success: bool


class RateLimiter:
    """
    Thread-safe rate limiter with cooldown enforcement.
    
    Usage:
        limiter = RateLimiter()
        
        # Check if fetch is allowed
        can_fetch, reason = limiter.can_fetch("AAPL", "price")
        if can_fetch:
            # ... perform fetch ...
            limiter.record_fetch("AAPL", "price")
        else:
            # ... handle rate limited case ...
            remaining = limiter.get_cooldown_remaining("AAPL", "price")
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        # (symbol, data_type) -> last fetch timestamp
        self._last_fetch: Dict[Tuple[str, str], float] = {}
        # (symbol, data_type, date_str) -> count
        self._daily_counts: Dict[Tuple[str, str, str], int] = {}
        # Circular buffer of recent fetches for debugging
        self._recent_fetches: list = []
        self._max_recent = 100  # Keep last 100 fetch records
    
    def can_fetch(self, symbol: str, data_type: str) -> Tuple[bool, str]:
        """
        Check if a fetch is allowed under rate limiting rules.
        
        Returns:
            (True, "OK") if fetch is allowed
            (False, reason) if fetch is blocked
        """
        symbol = symbol.upper()
        key = (symbol, data_type)
        today = date.today().isoformat()
        now = time.time()
        
        with self._lock:
            # Rule 1: Minimum interval check
            if key in self._last_fetch:
                elapsed = now - self._last_fetch[key]
                if elapsed < MIN_REFRESH_INTERVAL:
                    return False, f"Cooldown active: {MIN_REFRESH_INTERVAL - elapsed:.0f}s remaining"
            
            # Rule 2: Daily limit check
            daily_key = (symbol, data_type, today)
            if daily_key in self._daily_counts:
                if self._daily_counts[daily_key] >= DAILY_FETCH_LIMIT:
                    # Calculate reset time (midnight UTC)
                    tomorrow = datetime.fromisoformat(today).timestamp() + 86400
                    reset_in = max(0, tomorrow - now)
                    return False, f"Daily limit reached ({DAILY_FETCH_LIMIT}). Resets in {reset_in/3600:.1f}h"
            
            return True, "OK"
    
    def record_fetch(self, symbol: str, data_type: str, success: bool = True):
        """
        Record a successful fetch for rate tracking.
        
        Args:
            symbol: Ticker symbol
            data_type: Type of data fetched (e.g., "price", "fundamentals")
            success: Whether the fetch was successful (affects nothing currently, for future use)
        """
        symbol = symbol.upper()
        key = (symbol, data_type)
        today = date.today().isoformat()
        daily_key = (symbol, data_type, today)
        now = time.time()
        
        with self._lock:
            # Update last fetch timestamp
            self._last_fetch[key] = now
            
            # Increment daily count
            self._daily_counts[daily_key] = self._daily_counts.get(daily_key, 0) + 1
            
            # Track recent fetches for debugging
            record = FetchRecord(symbol, data_type, now, success)
            self._recent_fetches.append(record)
            if len(self._recent_fetches) > self._max_recent:
                self._recent_fetches = self._recent_fetches[-self._max_recent:]
            
            logger.debug(
                "Recorded fetch: %s/%s (daily: %d/%d, interval: %.0fs ago)",
                symbol, data_type,
                self._daily_counts[daily_key],
                DAILY_FETCH_LIMIT,
                0
            )
    
    def get_cooldown_remaining(self, symbol: str, data_type: str) -> float:
        """
        Get seconds until next fetch is allowed for a symbol/data_type.
        
        Returns:
            0.0 if fetch is allowed, otherwise seconds remaining
        """
        symbol = symbol.upper()
        key = (symbol, data_type)
        now = time.time()
        
        with self._lock:
            if key not in self._last_fetch:
                return 0.0
            
            elapsed = now - self._last_fetch[key]
            remaining = MIN_REFRESH_INTERVAL - elapsed
            return max(0.0, remaining)
    
    def get_daily_remaining(self, symbol: str, data_type: str) -> int:
        """
        Get remaining fetches allowed today for a symbol/data_type.
        
        Returns:
            Number of fetches remaining today
        """
        symbol = symbol.upper()
        today = date.today().isoformat()
        daily_key = (symbol, data_type, today)
        
        with self._lock:
            used = self._daily_counts.get(daily_key, 0)
            return max(0, DAILY_FETCH_LIMIT - used)
    
    def get_status(self, symbol: str, data_type: str) -> Dict:
        """
        Get full rate limit status for a symbol/data_type.
        
        Returns:
            Dict with cooldown_remaining, daily_remaining, last_fetch time
        """
        symbol = symbol.upper()
        key = (symbol, data_type)
        now = time.time()
        
        with self._lock:
            last_fetch = self._last_fetch.get(key)
            
            return {
                "symbol": symbol,
                "data_type": data_type,
                "cooldown_remaining": self.get_cooldown_remaining(symbol, data_type),
                "daily_remaining": self.get_daily_remaining(symbol, data_type),
                "daily_limit": DAILY_FETCH_LIMIT,
                "min_interval": MIN_REFRESH_INTERVAL,
                "last_fetch": datetime.fromtimestamp(last_fetch).isoformat() if last_fetch else None,
                "last_fetch_age_seconds": now - last_fetch if last_fetch else None,
            }
    
    def reset_cooldown(self, symbol: str, data_type: str = None):
        """
        Manually reset cooldown for a symbol/data_type.
        Use for testing or override in special circumstances.
        
        Args:
            symbol: Ticker symbol (or None to reset all)
            data_type: Data type (or None to reset all for symbol)
        """
        with self._lock:
            if symbol is None:
                self._last_fetch.clear()
                self._daily_counts.clear()
                logger.info("Reset all rate limit cooldowns")
            elif data_type is None:
                # Reset all data_types for this symbol
                keys_to_remove = [k for k in self._last_fetch if k[0] == symbol.upper()]
                for key in keys_to_remove:
                    del self._last_fetch[key]
                logger.info("Reset rate limit for symbol %s", symbol)
            else:
                key = (symbol.upper(), data_type)
                if key in self._last_fetch:
                    del self._last_fetch[key]
                logger.info("Reset rate limit for %s/%s", symbol, data_type)
    
    def get_recent_fetches(self, limit: int = 20) -> list:
        """
        Get recent fetch records for debugging.
        
        Returns:
            List of recent FetchRecord objects, most recent first
        """
        with self._lock:
            return list(reversed(self._recent_fetches[-limit:]))
    
    def cleanup_old_records(self):
        """
        Remove records older than 48 hours to prevent memory bloat.
        Called periodically by background worker.
        """
        cutoff = time.time() - (48 * 3600)
        
        with self._lock:
            # Clean up last_fetch entries older than 48h
            keys_to_remove = [
                k for k, ts in self._last_fetch.items() if ts < cutoff
            ]
            for key in keys_to_remove:
                del self._last_fetch[key]
            
            # Clean up daily_counts entries older than 48h
            old_dates = set()
            for (_, _, date_str) in self._daily_counts:
                try:
                    record_date = datetime.fromisoformat(date_str).date()
                    if (date.today() - record_date).days > 1:
                        old_dates.add(date_str)
                except ValueError:
                    old_dates.add(date_str)
            
            for old_date in old_dates:
                keys_to_remove = [
                    k for k in self._daily_counts if k[2] == old_date
                ]
                for key in keys_to_remove:
                    del self._daily_counts[key]
            
            if keys_to_remove:
                logger.info("Cleaned up %d old rate limit records", len(keys_to_remove))


# Global singleton instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global RateLimiter instance (lazy initialization)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter