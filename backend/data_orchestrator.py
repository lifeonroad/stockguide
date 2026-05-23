"""
data_orchestrator.py — Unified Data Access Layer
=================================================
DB-first data access with rate limiting and background refresh.
This is the PUBLIC interface - all business logic should use this.

Usage:
    from data_orchestrator import DataOrchestrator
    orchestrator = DataOrchestrator()
    
    # Get price (checks DB first, rate-limited fetch if stale)
    price = orchestrator.get_price("AAPL")
    
    # Get fundamentals
    fundamentals = orchestrator.get_fundamentals("AAPL")
    
    # Bulk fetch (batched, rate-limited)
    prices = orchestrator.get_bulk_prices(["AAPL", "MSFT", "GOOGL"])
"""

import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import pandas as pd

from rate_limiter import RateLimiter, get_rate_limiter, MIN_REFRESH_INTERVAL
from network_client import _NetworkClient, get_network_client, CircuitOpenError
from persistent_cache import (
    init_db, get_ticker_info_cached, save_ticker_info,
    get_price_history_cached, save_price_history,
    needs_refresh, get_bulk_ticker_info,
    PRICE_TTL, FUNDAMENTALS_TTL,
)
from cache_utils import timed_cache

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a data fetch with freshness info."""
    data: Any
    source: str  # 'db', 'network', 'stale'
    age_seconds: Optional[float] = None
    warning: Optional[str] = None
    rate_limited: bool = False


class DataOrchestrator:
    """
    Unified data access layer. DB-first with conservative rate limiting.
    
    Architecture:
    1. Check DB for data
    2. Evaluate freshness against TTL
    3. If stale: check rate limiter
       - If allowed: fetch from network, persist, return
       - If rate limited: return stale data with warning
    4. Background worker processes refresh queue
    
    All network calls go through NetworkClient (private).
    Business logic only talks to this orchestrator.
    """
    
    def __init__(self):
        self._db_initialized = False
        self._rate_limiter = get_rate_limiter()
        self._network = get_network_client()
        self._refresh_queue = []
        self._queue_lock = threading.Lock()
        self._background_running = False
        self._background_thread = None
        
    def init(self):
        """Initialize database and start background worker."""
        if not self._db_initialized:
            init_db()
            self._db_initialized = True
            self._start_background_worker()
    
    # ── Public API: Price ───────────────────────────────────────────────────
    
    def get_price(self, symbol: str, force_refresh: bool = False) -> FetchResult:
        """
        Get current price for a ticker. DB-first, rate-limited.
        
        Args:
            symbol: Ticker symbol
            force_refresh: Override rate limiting (use sparingly)
            
        Returns:
            FetchResult with price data and metadata
        """
        self.init()
        symbol = symbol.upper()
        
        # Step 1: Check DB
        cached = get_ticker_info_cached(symbol)
        
        if cached and not force_refresh:
            # Step 2: Evaluate freshness
            fetched_at = cached.get("price_fetched_at") or cached.get("fetched_at", 0)
            age = time.time() - fetched_at
            
            if age < PRICE_TTL:
                # Fresh data - return immediately
                return FetchResult(
                    data=cached.get("price"),
                    source="db",
                    age_seconds=age,
                )
            
            # Stale data - check rate limiter
            can_fetch, reason = self._rate_limiter.can_fetch(symbol, "price")
            
            if can_fetch or force_refresh:
                # Fetch from network
                fresh = self._fetch_price_from_network(symbol)
                if fresh:
                    return FetchResult(
                        data=fresh,
                        source="network",
                        age_seconds=0,
                    )
            
            # Rate limited - return stale with warning
            return FetchResult(
                data=cached.get("price"),
                source="stale",
                age_seconds=age,
                warning=f"Rate limited. Data is {age//60:.0f}m old. {reason}",
                rate_limited=True,
            )
        
        # No cached data - fetch from network
        fresh = self._fetch_price_from_network(symbol)
        if fresh:
            return FetchResult(
                data=fresh,
                source="network",
                age_seconds=0,
            )
        
        return FetchResult(data=None, source="error", warning="Failed to fetch price")
    
    def get_bulk_prices(self, symbols: List[str]) -> Dict[str, FetchResult]:
        """
        Get prices for multiple tickers. Batched, rate-limited.
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            Dict mapping symbol to FetchResult
        """
        self.init()
        symbols = [s.upper() for s in symbols]
        results = {}
        
        # Step 1: Bulk DB lookup
        cached = get_bulk_ticker_info(symbols)
        
        for symbol in symbols:
            if symbol in cached:
                fetched_at = cached[symbol].get("price_fetched_at") or cached[symbol].get("fetched_at", 0)
                age = time.time() - fetched_at
                
                if age < PRICE_TTL:
                    results[symbol] = FetchResult(
                        data=cached[symbol].get("price"),
                        source="db",
                        age_seconds=age,
                    )
                else:
                    # Stale - check rate limit
                    can_fetch, reason = self._rate_limiter.can_fetch(symbol, "price")
                    if can_fetch:
                        fresh = self._fetch_price_from_network(symbol)
                        if fresh:
                            results[symbol] = FetchResult(
                                data=fresh,
                                source="network",
                                age_seconds=0,
                            )
                            continue
                    
                    # Rate limited or failed
                    results[symbol] = FetchResult(
                        data=cached[symbol].get("price"),
                        source="stale",
                        age_seconds=age,
                        warning=reason if not can_fetch else None,
                        rate_limited=not can_fetch,
                    )
            else:
                # No cached data
                fresh = self._fetch_price_from_network(symbol)
                if fresh:
                    results[symbol] = FetchResult(
                        data=fresh,
                        source="network",
                        age_seconds=0,
                    )
                else:
                    results[symbol] = FetchResult(
                        data=None,
                        source="error",
                        warning=f"No data available for {symbol}",
                    )
        
        return results
    
    # ── Public API: Fundamentals ───────────────────────────────────────────
    
    def get_fundamentals(self, symbol: str, fields: List[str] = None,
                         force_refresh: bool = False) -> FetchResult:
        """
        Get fundamentals for a ticker. DB-first, rate-limited.
        
        Args:
            symbol: Ticker symbol
            fields: Specific fields to fetch (None = all)
            force_refresh: Override rate limiting
            
        Returns:
            FetchResult with fundamentals dict
        """
        self.init()
        symbol = symbol.upper()
        
        # Step 1: Check DB
        cached = get_ticker_info_cached(symbol)
        
        if cached and not force_refresh:
            fetched_at = cached.get("fetched_at", 0)
            age = time.time() - fetched_at
            
            if age < FUNDAMENTALS_TTL:
                data = cached if fields is None else {k: cached.get(k) for k in fields if k in cached}
                return FetchResult(data=data, source="db", age_seconds=age)
            
            # Stale - check rate limit
            can_fetch, reason = self._rate_limiter.can_fetch(symbol, "fundamentals")
            
            if can_fetch or force_refresh:
                fresh = self._fetch_fundamentals_from_network(symbol)
                if fresh:
                    return FetchResult(data=fresh, source="network", age_seconds=0)
            
            return FetchResult(
                data=cached if fields is None else {k: cached.get(k) for k in fields if k in cached},
                source="stale",
                age_seconds=age,
                warning=f"Rate limited. Data is {age//3600:.1f}h old.",
                rate_limited=True,
            )
        
        # No cached data
        fresh = self._fetch_fundamentals_from_network(symbol)
        if fresh:
            return FetchResult(data=fresh, source="network", age_seconds=0)
        
        return FetchResult(data=None, source="error", warning="Failed to fetch fundamentals")
    
    def get_bulk_fundamentals(self, symbols: List[str]) -> Dict[str, FetchResult]:
        """
        Get fundamentals for multiple tickers. Batched, rate-limited.
        """
        self.init()
        symbols = [s.upper() for s in symbols]
        results = {}
        
        cached = get_bulk_ticker_info(symbols)
        
        for symbol in symbols:
            if symbol in cached:
                fetched_at = cached[symbol].get("fetched_at", 0)
                age = time.time() - fetched_at
                
                if age < FUNDAMENTALS_TTL:
                    results[symbol] = FetchResult(
                        data=cached[symbol],
                        source="db",
                        age_seconds=age,
                    )
                else:
                    can_fetch, _ = self._rate_limiter.can_fetch(symbol, "fundamentals")
                    if can_fetch:
                        fresh = self._fetch_fundamentals_from_network(symbol)
                        if fresh:
                            results[symbol] = FetchResult(
                                data=fresh,
                                source="network",
                                age_seconds=0,
                            )
                            continue
                    
                    results[symbol] = FetchResult(
                        data=cached[symbol],
                        source="stale",
                        age_seconds=age,
                        rate_limited=True,
                    )
            else:
                fresh = self._fetch_fundamentals_from_network(symbol)
                if fresh:
                    results[symbol] = FetchResult(
                        data=fresh,
                        source="network",
                        age_seconds=0,
                    )
                else:
                    results[symbol] = FetchResult(
                        data=None,
                        source="error",
                    )
        
        return results
    
    # ── Public API: Price History ──────────────────────────────────────────
    
    def get_price_history(self, symbol: str, days: int = 252) -> FetchResult:
        """
        Get historical price data. Immutable once stored.
        """
        self.init()
        symbol = symbol.upper()
        
        # Check DB first (historical data is immutable)
        cached = get_price_history_cached(symbol, days)
        
        if cached:
            # Check if we have enough data
            if len(cached) >= days * 0.8:  # 80% coverage is acceptable
                df = pd.DataFrame(cached)
                return FetchResult(data=df, source="db")
            
            # Missing data - trigger background refresh
            self._enqueue_background_refresh(symbol, "history", priority=2)
        
        # Fetch from network and persist
        fresh = self._fetch_history_from_network(symbol, days)
        if fresh is not None and not fresh.empty:
            return FetchResult(data=fresh, source="network", age_seconds=0)
        
        # Return stale if available
        if cached:
            df = pd.DataFrame(cached)
            return FetchResult(data=df, source="stale")
        
        return FetchResult(data=None, source="error", warning="No price history available")
    
    # ── Public API: Indicators ────────────────────────────────────────────
    
    def calculate_indicator(self, symbol: str, indicator: str, 
                           period: int = 14, **params) -> FetchResult:
        """
        Calculate technical indicator from stored price data.
        No network call - purely local calculation.
        
        Supported indicators: SMA, EMA, RSI, MACD, BBANDS, etc.
        """
        self.init()
        
        # Get price history from DB
        history = get_price_history_cached(symbol, 500)  # Need extra for indicator calculation
        if not history:
            return FetchResult(data=None, source="error", warning="No price history for calculation")
        
        df = pd.DataFrame(history)
        if 'date' in df.columns:
            df = df.set_index('date')
        
        result = {}
        
        if indicator.upper() == "SMA":
            window = params.get("window", period)
            result["value"] = df['close'].rolling(window).mean().iloc[-1]
            result["period"] = window
            
        elif indicator.upper() == "RSI":
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            rs = gain / loss
            result["value"] = 100 - (100 / (1 + rs)).iloc[-1]
            result["period"] = period
            
        elif indicator.upper() == "EMA":
            window = params.get("window", period)
            result["value"] = df['close'].ewm(span=window).mean().iloc[-1]
            
        else:
            return FetchResult(
                data=None,
                source="error",
                warning=f"Unknown indicator: {indicator}"
            )
        
        result["symbol"] = symbol
        result["indicator"] = indicator
        
        return FetchResult(data=result, source="local", age_seconds=0)
    
    # ── Public API: Market Context ─────────────────────────────────────────
    
    def get_market_context(self, key: str) -> FetchResult:
        """
        Get macro market indicators (VIX, Treasury, etc.).
        """
        self.init()
        
        # Check DB first
        from persistent_cache import _get_conn
        
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT value_numeric, last_updated FROM market_context WHERE key = ?",
                (key,)
            ).fetchone()
            
            if row:
                age = time.time() - (row[1] or 0)
                if age < 3600:  # 1 hour TTL for market context
                    return FetchResult(
                        data=row[0],
                        source="db",
                        age_seconds=age,
                    )
        finally:
            conn.close()
        
        # Fetch from macro module
        data = self._fetch_market_context_from_network(key)
        if data is not None:
            return FetchResult(data=data, source="network", age_seconds=0)
        
        return FetchResult(data=None, source="error")
    
    # ── Internal Methods ───────────────────────────────────────────────────
    
    def _fetch_price_from_network(self, symbol: str) -> Optional[float]:
        """Fetch price from network with rate limiting."""
        self._rate_limiter.record_fetch(symbol, "price")
        
        # Try yfinance first
        price = self._network.get_yf_price(symbol)
        if price:
            # Persist to DB
            cached = get_ticker_info_cached(symbol)
            if cached:
                cached["price"] = price
                save_ticker_info(cached)
            return price
        
        # Try yahooquery fallback
        yq_price = self._network.get_yq_price(symbol)
        if yq_price and yq_price.get("regularMarketPrice"):
            price = yq_price["regularMarketPrice"]
            cached = get_ticker_info_cached(symbol)
            if cached:
                cached["price"] = price
                save_ticker_info(cached)
            return price
        
        return None
    
    def _fetch_fundamentals_from_network(self, symbol: str) -> Optional[Dict]:
        """Fetch fundamentals from network with rate limiting."""
        self._rate_limiter.record_fetch(symbol, "fundamentals")
        
        # Try yfinance
        info = self._network.get_yf_info(symbol)
        if info:
            info["symbol"] = symbol
            save_ticker_info(info)
            return info
        
        # Try yahooquery fallback
        yq_info = self._network.get_yq_info(symbol)
        if yq_info:
            yq_info["symbol"] = symbol
            save_ticker_info(yq_info)
            return yq_info
        
        return None
    
    def _fetch_history_from_network(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """Fetch price history from network."""
        self._rate_limiter.record_fetch(symbol, "history")
        
        df = self._network.get_yf_history(symbol, period=f"{days}d")
        if df is not None and not df.empty:
            # Convert and save to DB
            rows = []
            for date, row in df.iterrows():
                date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
                rows.append({
                    "date": date_str,
                    "open": row.get("Open", row.get("open", 0)),
                    "high": row.get("High", row.get("high", 0)),
                    "low": row.get("Low", row.get("low", 0)),
                    "close": row.get("Close", row.get("close", 0)),
                    "volume": row.get("Volume", row.get("volume", 0)),
                })
            
            if rows:
                save_price_history(symbol, rows)
            
            return df
        
        return None
    
    def _fetch_market_context_from_network(self, key: str) -> Optional[float]:
        """Fetch macro indicators."""
        # This would integrate with macro.py logic
        # For now, return None to use cached/estimated values
        return None
    
    def _enqueue_background_refresh(self, symbol: str, data_type: str, priority: int = 2):
        """Add to background refresh queue."""
        with self._queue_lock:
            # Avoid duplicates
            existing = [i for i, item in enumerate(self._refresh_queue) 
                       if item["symbol"] == symbol and item["data_type"] == data_type]
            if existing:
                # Update priority if lower (higher priority number = lower priority)
                if priority < self._refresh_queue[existing[0]]["priority"]:
                    self._refresh_queue[existing[0]]["priority"] = priority
                return
            
            self._refresh_queue.append({
                "symbol": symbol,
                "data_type": data_type,
                "priority": priority,
                "enqueued_at": time.time(),
            })
            # Sort by priority (lower = higher priority)
            self._refresh_queue.sort(key=lambda x: x["priority"])
    
    def _start_background_worker(self):
        """Start background refresh worker thread."""
        if self._background_running:
            return
        
        self._background_running = True
        self._background_thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
            name="DataOrchestrator-Background"
        )
        self._background_thread.start()
        logger.info("Background refresh worker started")
    
    def _background_loop(self):
        """Background worker: process refresh queue with cooldowns."""
        while self._background_running:
            try:
                with self._queue_lock:
                    if not self._refresh_queue:
                        time.sleep(60)  # No pending items
                        continue
                    
                    item = self._refresh_queue.pop(0)
                
                symbol = item["symbol"]
                data_type = item["data_type"]
                
                # Check rate limiter
                can_fetch, reason = self._rate_limiter.can_fetch(symbol, data_type)
                
                if not can_fetch:
                    # Re-queue with delay
                    time.sleep(300)  # 5 min delay before retry
                    with self._queue_lock:
                        self._refresh_queue.append(item)
                    continue
                
                # Execute refresh
                if data_type == "price":
                    self._fetch_price_from_network(symbol)
                elif data_type == "fundamentals":
                    self._fetch_fundamentals_from_network(symbol)
                elif data_type == "history":
                    self._fetch_history_from_network(symbol, 252)
                
            except Exception as e:
                logger.error("Background refresh error: %s", e)
                time.sleep(10)
    
    def stop_background_worker(self):
        """Stop background refresh worker."""
        self._background_running = False
        if self._background_thread:
            self._background_thread.join(timeout=5)
    
    # ── Status / Debug ─────────────────────────────────────────────────────
    
    def get_status(self) -> Dict:
        """Get orchestrator status."""
        with self._queue_lock:
            queue_size = len(self._refresh_queue)
        
        return {
            "rate_limiter": {
                "can_fetch_AAPL_price": self._rate_limiter.can_fetch("AAPL", "price")[0],
                "daily_remaining_AAPL": self._rate_limiter.get_daily_remaining("AAPL", "price"),
            },
            "background_worker": {
                "running": self._background_running,
                "queue_size": queue_size,
            },
            "network_circuits": self._network.get_circuit_status(),
        }


# Global singleton instance
_orchestrator: Optional[DataOrchestrator] = None


def get_orchestrator() -> DataOrchestrator:
    """Get the global DataOrchestrator instance (lazy initialization)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DataOrchestrator()
    return _orchestrator


# Convenience functions for backward compatibility
def get_price(symbol: str, force_refresh: bool = False) -> Optional[float]:
    """Get price for a symbol. Convenience wrapper."""
    result = get_orchestrator().get_price(symbol, force_refresh)
    return result.data


def get_fundamentals(symbol: str, fields: List[str] = None) -> Dict:
    """Get fundamentals for a symbol. Convenience wrapper."""
    result = get_orchestrator().get_fundamentals(symbol, fields)
    return result.data or {}


def get_bulk_prices(symbols: List[str]) -> Dict[str, float]:
    """Get prices for multiple symbols. Convenience wrapper."""
    results = get_orchestrator().get_bulk_prices(symbols)
    return {s: r.data for s, r in results.items() if r.data is not None}