# Phase 3: DataOrchestrator Implementation

> **Status:** In Progress  
> **Objective:** Single public interface wrapping all network logic with DB-first pattern

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Application Layer                                │
│                    (Business Logic - ONLY uses this API)                     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DatabaseProvider (PUBLIC)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        DataOrchestrator                              │   │
│  │                                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────────────┐ │   │
│  │  │ DB Check │→ │ Freshness│→ │ Return / Enqueue for Background     │ │   │
│  │  │ (READ)   │  │  Check   │  │ (Background refresh worker)          │ │   │
│  │  └──────────┘  └──────────┘  └──────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NetworkClient (PRIVATE)                              │
│                    (yfinance, yahooquery, requests)                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Components

### 2.1 DataOrchestrator Class

```python
class DataOrchestrator:
    """
    Unified data access layer. DB-first with rate limiting.
    
    Usage:
        from data_orchestrator import DataOrchestrator
        orchestrator = DataOrchestrator()
        
        # Get price (checks DB first, fetches if stale with rate limiting)
        price = orchestrator.get_price("AAPL")
        
        # Get fundamentals (DB-first, background refresh)
        fundamentals = orchestrator.get_fundamentals("AAPL")
        
        # Bulk fetch (rate-limited, batched)
        data = orchestrator.get_bulk_prices(["AAPL", "MSFT", "GOOGL"])
    """
    
    def __init__(self):
        self._db = persistent_cache
        self._rate_limiter = RateLimiter()
        self._refresh_queue = []
        self._background_worker = None
        
    # ── Public API ──────────────────────────────────────────────────────────
    
    def get_price(self, symbol: str, force_refresh: bool = False) -> Optional[float]:
        """Get current price. DB-first, rate-limited fetch."""
        
    def get_fundamentals(self, symbol: str, fields: List[str] = None) -> Dict:
        """Get fundamentals. DB-first, returns stale with warning if rate-limited."""
        
    def get_price_history(self, symbol: str, days: int = 252) -> pd.DataFrame:
        """Get historical OHLCV. Immutable once stored."""
        
    def get_bulk_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get prices for multiple tickers. Batched, rate-limited."""
        
    def get_indicator(self, symbol: str, indicator: str, **params) -> Dict:
        """Calculate indicator from DB price data."""
        
    # ── Internal Methods ────────────────────────────────────────────────────
    
    def _can_fetch(self, symbol: str, data_type: str) -> Tuple[bool, str]:
        """Check rate limiting rules. Returns (can_fetch, reason)."""
        
    def _fetch_from_network(self, symbol: str, data_type: str) -> Optional[Dict]:
        """Private: actual network call through NetworkClient."""
        
    def _enqueue_refresh(self, symbol: str, data_type: str, priority: int = 2):
        """Add to background refresh queue."""
        
    def _background_loop(self):
        """Background worker: process refresh queue with cooldowns."""
```

### 2.2 RateLimiter Class

```python
class RateLimiter:
    """
    Enforces conservative fetch limits to prevent yfinance rate limiting.
    
    Rules:
    - MIN_REFRESH_INTERVAL: 1800s (30 min) between same ticker fetches
    - DAILY_FETCH_LIMIT: 48 fetches per ticker per day
    - BULK_FETCH_BATCH: 10 tickers per bulk request
    """
    
    def __init__(self):
        self._last_fetch = {}      # (symbol, data_type) -> timestamp
        self._daily_counts = {}    # (symbol, data_type, date) -> count
        self._lock = threading.Lock()
        
    def can_fetch(self, symbol: str, data_type: str) -> Tuple[bool, str]:
        """Check if fetch is allowed. Thread-safe."""
        
    def record_fetch(self, symbol: str, data_type: str):
        """Record successful fetch for rate tracking. Thread-safe."""
        
    def get_cooldown_remaining(self, symbol: str, data_type: str) -> float:
        """Seconds until next fetch allowed."""
        
    def reset_cooldown(self, symbol: str, data_type: str = None):
        """Manually reset cooldown (for testing/override)."""
```

### 2.3 NetworkClient (Private)

```python
class _NetworkClient:
    """
    Private implementation of network calls. Never exposed to application.
    All network egress goes through here.
    """
    
    # yfinance wrapper
    def get_yf_info(self, symbol: str) -> Dict:
        """Fetch ticker info from yfinance."""
        
    def get_yf_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Fetch price history from yfinance."""
        
    def get_yf_price(self, symbol: str) -> Optional[float]:
        """Get current price from yfinance."""
    
    # yahooquery wrapper
    def get_yq_info(self, symbol: str) -> Dict:
        """Fetch deep info from yahooquery."""
        
    # requests wrapper (for FRED, etc.)
    def get_fred_data(self, series_id: str) -> Optional[Dict]:
        """Fetch economic data from FRED API."""
        
    # Retry logic
    def fetch_with_retry(self, fetch_func, max_attempts: int = 3) -> Any:
        """Execute fetch with exponential backoff."""
```

---

## 3. DataFlow Examples

### 3.1 Get Price Flow

```
User Request: get_price("AAPL")
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ DataOrchestrator.get_price()                           │
│                                                         │
│ 1. Check DB                                             │
│    → SELECT price, price_fetched_at FROM ticker_info    │
│      WHERE symbol = "AAPL"                              │
│                                                         │
│ 2. Evaluate Freshness                                    │
│    → Now: 1000000                                       │
│    → Fetched: 999800 (200s ago)                         │
│    → TTL: 1800s (30 min)                                │
│    → Status: FRESH → Return cached price                │
└─────────────────────────────────────────────────────────┘
    │
    ▼ (if stale)
┌─────────────────────────────────────────────────────────┐
│ Check RateLimiter.can_fetch()                           │
│                                                         │
│ 3. Rate Limit Check                                      │
│    → Last fetch: 999500 (500s ago)                       │
│    → MIN_REFRESH_INTERVAL: 1800s                        │
│    → Result: CANNOT FETCH (cooldown active)             │
│                                                         │
│ 4. Return Stale with Warning                            │
│    → {                                                  │
│        "price": 178.50,                                 │
│        "stale": true,                                   │
│        "age_seconds": 500,                              │
│        "warning": "Rate limited. Data is 8m old."       │
│      }                                                  │
└─────────────────────────────────────────────────────────┘
    │
    ▼ (if allowed)
┌─────────────────────────────────────────────────────────┐
│ NetworkClient.fetch_with_retry()                         │
│                                                         │
│ 5. Fetch from yfinance                                   │
│    → yf.Ticker("AAPL").info["currentPrice"]             │
│                                                         │
│ 6. Record in RateLimiter                                 │
│    → last_fetch["AAPL", "price"] = now                   │
│    → daily_counts["AAPL", "price", "2026-05-10"] += 1   │
│                                                         │
│ 7. Persist to DB                                         │
│    → UPDATE ticker_info SET price = 179.25,             │
│        price_fetched_at = now WHERE symbol = "AAPL"      │
│                                                         │
│ 8. Return Fresh Data                                     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Bulk Fetch Flow

```
User Request: get_bulk_prices(["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", 
                                "META", "TSLA", "AMD", "NFLX", "CRM"])
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ DataOrchestrator.get_bulk_prices()                       │
│                                                         │
│ 1. DB Lookup (single query)                             │
│    → SELECT symbol, price, price_fetched_at             │
│      FROM ticker_info                                   │
│      WHERE symbol IN (AAPL, MSFT, ... )                 │
│                                                         │
│ 2. Classify by Freshness                                 │
│    ┌─────────────────────────────────────────────────┐  │
│    │ FRESH (TTL not expired)                        │  │
│    │   → AAPL, MSFT, GOOGL                          │  │
│    │   → Return cached immediately                   │  │
│    ├─────────────────────────────────────────────────┤  │
│    │ STALE + CAN_FETCH (under rate limit)           │  │
│    │   → AMZN, NVDA, META                            │  │
│    │   → Enqueue for fetch                           │  │
│    ├─────────────────────────────────────────────────┤  │
│    │ STALE + RATE_LIMITED (cooldown active)          │  │
│    │   → TSLA, AMD, NFLX, CRM                        │  │
│    │   → Return stale with warning                   │  │
│    └─────────────────────────────────────────────────┘  │
│                                                         │
│ 3. Batch Fetch (BULK_FETCH_BATCH = 10)                  │
│    → yf.download(AMZN, NVDA, META, ...)                │
│                                                         │
│ 4. Persist & Record                                     │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Error Handling

### 4.1 Network Failure Strategy

```python
def _fetch_with_fallback(self, symbol: str, data_type: str) -> Optional[Dict]:
    """
    Fetch with graceful degradation:
    1. Try yfinance
    2. If fails, try yahooquery (different endpoint)
    3. If all fail, return stale data if available
    """
    
    # Attempt 1: yfinance
    try:
        return self._network.get_yf_info(symbol)
    except Exception as e1:
        logger.warning("yfinance failed for %s: %s", symbol, e1)
    
    # Attempt 2: yahooquery (different API, different rate limits)
    try:
        return self._network.get_yq_info(symbol)
    except Exception as e2:
        logger.warning("yahooquery failed for %s: %s", symbol, e2)
    
    # Attempt 3: Return stale data if available
    stale = self._get_stale_data(symbol, data_type)
    if stale:
        logger.info("Returning stale data for %s after network failure", symbol)
        return {"data": stale, "stale": True, "error": str(e2)}
    
    # Nothing available
    return None
```

### 4.2 Circuit Breaker Pattern

```python
class CircuitBreaker:
    """
    Prevent repeated failed calls to a data source.
    """
    
    FAILURE_THRESHOLD = 5      # Open circuit after 5 failures
    RESET_TIMEOUT = 300        # Try again after 5 minutes
    
    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.last_failure = 0
        self.state = "closed"  # closed, open, half-open
        
    def call(self, func):
        if self.state == "open":
            if time.time() - self.last_failure > self.RESET_TIMEOUT:
                self.state = "half-open"
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
        self.state = "closed"
        
    def _on_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.FAILURE_THRESHOLD:
            self.state = "open"
            logger.warning("Circuit %s opened after %d failures", self.name, self.failures)
```

---

## 5. Background Refresh Worker

### 5.1 Queue Processing

```python
def background_refresh_loop(self):
    """
    Background worker that processes refresh queue with rate limiting.
    """
    while self._running:
        try:
            # Get next item from queue (priority order)
            item = self._get_next_from_queue()
            
            if item is None:
                time.sleep(60)  # No pending items, sleep 1 min
                continue
            
            symbol, data_type, priority = item
            
            # Check rate limiter
            can_fetch, reason = self._rate_limiter.can_fetch(symbol, data_type)
            
            if not can_fetch:
                # Re-queue with delay
                self._requeue_with_delay(symbol, data_type, delay=300)  # 5 min
                continue
            
            # Execute fetch
            result = self._fetch_with_fallback(symbol, data_type)
            
            if result:
                self._persist_result(symbol, data_type, result)
                self._rate_limiter.record_fetch(symbol, data_type)
                self._remove_from_queue(symbol, data_type)
                
            else:
                # Network failed, re-queue with lower priority
                self._update_priority(symbol, data_type, priority + 1)
                
        except Exception as e:
            logger.error("Background refresh error: %s", e)
            time.sleep(10)
```

### 5.2 Queue Priority Levels

| Priority | Trigger | Processing |
|----------|---------|------------|
| 1 (High) | User request for missing data | Process immediately if rate limit allows |
| 2 (Medium) | Background refresh of stale data | Process in batch every 5 min |
| 3 (Low) | Maintenance sweep | Process nightly during off-hours |

---

## 6. API Reference

### DataOrchestrator Public Methods

| Method | Description | Return Type | Rate Limited |
|--------|-------------|-------------|--------------|
| `get_price(symbol)` | Current price | `Optional[float]` | Yes (30min floor) |
| `get_fundamentals(symbol, fields)` | Fundamentals dict | `Dict` | Yes (24h floor) |
| `get_price_history(symbol, days)` | Historical OHLCV | `pd.DataFrame` | No (immutable) |
| `get_bulk_prices(symbols)` | Multiple prices | `Dict[str, float]` | Yes (batched) |
| `get_indicator(symbol, name, **params)` | Calculate indicator | `Dict` | No (local calc) |
| `get_market_context(key)` | Macro indicators | `Optional[float]` | Yes (1h floor) |

### RateLimiter Public Methods

| Method | Description | Return Type |
|--------|-------------|-------------|
| `can_fetch(symbol, data_type)` | Check if fetch allowed | `Tuple[bool, str]` |
| `record_fetch(symbol, data_type)` | Record successful fetch | None |
| `get_cooldown_remaining(symbol, data_type)` | Seconds until next fetch | `float` |

---

## 7. Migration Path

### Phase 3.1: Create New Files

```
backend/
├── data_orchestrator.py      # NEW: Main orchestrator class
├── network_client.py         # NEW: Private network layer
├── rate_limiter.py          # NEW: Rate limiting logic
├── refresh_worker.py        # NEW: Background queue processor
└── data_client.py           # MODIFIED: Wrap with orchestrator
```

### Phase 3.2: Wrap Existing Code

```python
# data_client.py - wrap existing functions with orchestrator
from data_orchestrator import DataOrchestrator

_orchestrator = DataOrchestrator()

def get_ticker_info(symbol: str) -> Dict:
    return _orchestrator.get_fundamentals(symbol)

def get_price(symbol: str) -> Optional[float]:
    return _orchestrator.get_price(symbol)
```

### Phase 3.3: Update All Imports

```python
# Before
from data_client import get_ticker_info

# After (same import, different implementation)
from data_client import get_ticker_info  # Now uses DataOrchestrator internally
```

---

## 8. Phase 3 Completion Checklist

- [ ] Create `network_client.py` - private network layer
- [ ] Create `rate_limiter.py` - rate limiting with cooldown
- [ ] Create `refresh_worker.py` - background queue processor
- [ ] Create `data_orchestrator.py` - main orchestrator
- [ ] Update `data_client.py` to wrap orchestrator
- [ ] Add circuit breaker for yfinance
- [ ] Test rate limiting behavior
- [ ] Verify no breaking changes to existing endpoints

---

*Next Action: Start Phase 3.1 - Create NetworkClient private implementation*