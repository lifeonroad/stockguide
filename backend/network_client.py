"""
network_client.py — Private Network Layer
==========================================
Private implementation of all network calls. Never exposed to application.
All network egress goes through this class.

This is a PRIVATE module - only DataOrchestrator should use it.
"""

import time
import logging
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass

import yfinance as yf
from yahooquery import Ticker as YQTicker

from cache_utils import fetch_with_retry

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a network fetch operation."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    source: str = "unknown"  # 'yfinance', 'yahooquery', 'requests'
    response_time_ms: Optional[float] = None


class _NetworkClient:
    """
    Private network layer for all external data fetching.
    
    This class is private (indicated by underscore prefix).
    All data access should go through DataOrchestrator, not this class directly.
    
    Features:
    - Automatic retry with exponential backoff
    - Circuit breaker for failed endpoints
    - Fallback from yfinance to yahooquery
    - Request timing and logging
    """
    
    # Retry configuration
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 2.0  # seconds
    REQUEST_TIMEOUT = 15  # seconds
    
    def __init__(self):
        self._circuit_breakers = {
            "yfinance": CircuitBreaker("yfinance"),
            "yahooquery": CircuitBreaker("yahooquery"),
            "fred": CircuitBreaker("fred"),
        }
        self._yq_cache = {}  # Cache yahooquery sessions
    
    # ── yfinance Methods ────────────────────────────────────────────────────
    
    def get_yf_info(self, symbol: str) -> Optional[Dict]:
        """
        Fetch ticker info from yfinance.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with ticker info, or None if failed
        """
        circuit = self._circuit_breakers["yfinance"]
        
        def fetch():
            ticker = yf.Ticker(symbol)
            return ticker.info
        
        try:
            return circuit.call(lambda: fetch_with_retry(fetch, max_attempts=self.MAX_RETRIES))
        except CircuitOpenError as e:
            logger.warning("yfinance circuit open for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.error("yfinance failed for %s: %s", symbol, e)
            return None
    
    def get_yf_history(self, symbol: str, period: str = "1y", 
                      interval: str = "1d") -> Optional[pd.DataFrame]:
        """
        Fetch price history from yfinance.
        
        Args:
            symbol: Ticker symbol
            period: Time period (e.g., "1y", "6mo", "5d")
            interval: Data interval (e.g., "1d", "1h", "5m")
            
        Returns:
            DataFrame with OHLCV data, or None if failed
        """
        circuit = self._circuit_breakers["yfinance"]
        start = time.time()
        
        def fetch():
            return yf.download(symbol, period=period, interval=interval, progress=False, threads=False)
        
        try:
            result = circuit.call(lambda: fetch_with_retry(fetch, max_attempts=self.MAX_RETRIES))
            
            if result is not None and not result.empty:
                elapsed = (time.time() - start) * 1000
                logger.info("yfinance history for %s: %d rows in %.0fms", 
                           symbol, len(result), elapsed)
            
            return result
        except CircuitOpenError as e:
            logger.warning("yfinance circuit open for history %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.error("yfinance history failed for %s: %s", symbol, e)
            return None
    
    def get_yf_price(self, symbol: str) -> Optional[float]:
        """
        Get current/recent price from yfinance.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Current price as float, or None if failed
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception as e:
            logger.debug("yfinance price failed for %s: %s", symbol, e)
            return None
    
    def get_yf_fast_info(self, symbol: str) -> Optional[Dict]:
        """
        Get minimal info for a ticker (faster than full info).
        Useful for price-only lookups.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with basic info (price, change, volume), or None if failed
        """
        try:
            ticker = yf.Ticker(symbol)
            # Use fast_info which is lighter than full info
            fast = ticker.fast_info
            return {
                "price": fast.get("regular_price") or fast.get("last_price"),
                "market_cap": fast.get("market_cap"),
                "shares": fast.get("shares"),
                "currency": fast.get("currency"),
            }
        except Exception as e:
            logger.debug("yfinance fast_info failed for %s: %s", symbol, e)
            return None
    
    # ── yahooquery Methods ──────────────────────────────────────────────────
    
    def get_yq_info(self, symbol: str) -> Optional[Dict]:
        """
        Fetch deep info from yahooquery (different API, different rate limits).
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with comprehensive ticker info, or None if failed
        """
        circuit = self._circuit_breakers["yahooquery"]
        
        def fetch():
            # yahooquery is more comprehensive but slower
            tq = YQ_Ticker(symbol)
            info = {}
            for d in [tq.price, tq.financial_data, tq.key_stats, 
                      tq.summary_detail, tq.asset_profile]:
                if isinstance(d, dict) and isinstance(d.get(symbol), dict):
                    info.update(d[symbol])
            return info if info else None
        
        try:
            return circuit.call(lambda: fetch_with_retry(fetch, max_attempts=self.MAX_RETRIES))
        except CircuitOpenError as e:
            logger.warning("yahooquery circuit open for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.error("yahooquery failed for %s: %s", symbol, e)
            return None
    
    def get_yq_price(self, symbol: str) -> Optional[Dict]:
        """
        Get price quote from yahooquery.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with price info, or None if failed
        """
        try:
            tq = YQ_Ticker(symbol)
            price_data = tq.price.get(symbol, {})
            return price_data if price_data else None
        except Exception as e:
            logger.debug("yahooquery price failed for %s: %s", symbol, e)
            return None
    
    def get_yq_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        Get fundamental data from yahooquery.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dict with fundamentals, or None if failed
        """
        try:
            tq = YQ_Ticker(symbol)
            return {
                "financial_data": tq.financial_data.get(symbol),
                "key_stats": tq.key_stats.get(symbol),
                "earnings": tq.earnings.get(symbol),
                "valuation": tq.valuation_measures.get(symbol),
            }
        except Exception as e:
            logger.debug("yahooquery fundamentals failed for %s: %s", symbol, e)
            return None
    
    # ── requests Methods (FRED, etc.) ───────────────────────────────────────
    
    def get_fred_data(self, series_id: str, api_key: str = None) -> Optional[Dict]:
        """
        Fetch economic data from FRED API.
        
        Args:
            series_id: FRED series ID (e.g., "GDP", "CPI")
            api_key: FRED API key (uses env var FRED_API_KEY if not provided)
            
        Returns:
            Dict with observations, or None if failed
        """
        import requests
        
        circuit = self._circuit_breakers["fred"]
        
        if not api_key:
            import os
            api_key = os.getenv("FRED_API_KEY")
        
        if not api_key:
            logger.warning("FRED API key not configured")
            return None
        
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        
        def fetch():
            return requests.get(url, params=params, timeout=10)
        
        try:
            response = circuit.call(lambda: fetch_with_retry(fetch, max_attempts=self.MAX_RETRIES))
            if response and response.ok:
                return response.json()
            return None
        except CircuitOpenError as e:
            logger.warning("FRED circuit open for %s: %s", series_id, e)
            return None
        except Exception as e:
            logger.error("FRED request failed for %s: %s", series_id, e)
            return None
    
    # ── Bulk Operations ─────────────────────────────────────────────────────
    
    def get_bulk_yf_history(self, symbols: list, period: str = "1y") -> Dict[str, pd.DataFrame]:
        """
        Fetch history for multiple tickers in one request (efficient).
        
        Args:
            symbols: List of ticker symbols
            period: Time period
            
        Returns:
            Dict mapping symbol to DataFrame
        """
        if not symbols:
            return {}
        
        # yfinance supports comma-separated tickers for bulk download
        result = {}
        start = time.time()
        
        try:
            data = yf.download(symbols, period=period, progress=False, threads=True)
            
            if data.empty:
                return {}
            
            # Handle both single and multi-index columns
            if isinstance(data.columns, pd.MultiIndex):
                close = data['Close']
                for symbol in symbols:
                    if symbol in close.columns:
                        result[symbol] = close[symbol].dropna()
            else:
                # Single ticker case
                result[symbols[0]] = data['Close'].dropna()
            
            elapsed = (time.time() - start) * 1000
            logger.info("Bulk history fetch: %d symbols in %.0fms", len(symbols), elapsed)
            
        except Exception as e:
            logger.error("Bulk history fetch failed: %s", e)
        
        return result
    
    def get_bulk_yf_info(self, symbols: list) -> Dict[str, Dict]:
        """
        Fetch info for multiple tickers (with batching).
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            Dict mapping symbol to info dict
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        result = {}
        batch_size = 10  # Process in batches to avoid rate limits
        
        def fetch_one(symbol):
            try:
                info = self.get_yf_info(symbol)
                return symbol, info
            except Exception:
                return symbol, None
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(fetch_one, s): s for s in batch}
                for future in as_completed(futures):
                    symbol, info = future.result()
                    if info:
                        result[symbol] = info
            
            # Brief pause between batches
            if i + batch_size < len(symbols):
                time.sleep(0.5)
        
        return result
    
    # ── Circuit Breaker ─────────────────────────────────────────────────────
    
    def reset_circuit(self, source: str):
        """Reset circuit breaker for a source."""
        if source in self._circuit_breakers:
            self._circuit_breakers[source].reset()
            logger.info("Reset circuit breaker for %s", source)
    
    def get_circuit_status(self) -> Dict:
        """Get status of all circuit breakers."""
        return {
            name: cb.get_status() 
            for name, cb in self._circuit_breakers.items()
        }


class CircuitBreaker:
    """
    Circuit breaker to prevent repeated failed calls.
    
    States:
    - closed: Normal operation, requests pass through
    - open: Too many failures, requests are blocked
    - half-open: Testing if service has recovered
    """
    
    FAILURE_THRESHOLD = 5      # Open circuit after 5 failures
    RESET_TIMEOUT = 300        # Try again after 5 minutes
    SUCCESS_THRESHOLD = 2      # Need 2 successes to close circuit
    
    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.successes = 0
        self.last_failure = 0
        self.state = "closed"
    
    def call(self, func: Callable) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == "open":
            if time.time() - self.last_failure > self.RESET_TIMEOUT:
                self.state = "half-open"
                logger.info("Circuit %s entering half-open state", self.name)
            else:
                raise CircuitOpenError(f"Circuit {self.name} is open")
        
        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        self.failures = 0
        if self.state == "half-open":
            self.successes += 1
            if self.successes >= self.SUCCESS_THRESHOLD:
                self.state = "closed"
                self.successes = 0
                logger.info("Circuit %s closed", self.name)
        elif self.state == "closed":
            self.successes = 0
    
    def _on_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.FAILURE_THRESHOLD:
            self.state = "open"
            logger.warning("Circuit %s opened after %d failures", self.name, self.failures)
    
    def reset(self):
        """Manually reset circuit breaker."""
        self.failures = 0
        self.successes = 0
        self.state = "closed"
    
    def get_status(self) -> Dict:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "last_failure": self.last_failure,
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


# Import pandas for type hints
import pandas as pd


# Global singleton instance
_network_client: Optional[_NetworkClient] = None


def get_network_client() -> _NetworkClient:
    """Get the global _NetworkClient instance (lazy initialization)."""
    global _network_client
    if _network_client is None:
        _network_client = _NetworkClient()
    return _network_client