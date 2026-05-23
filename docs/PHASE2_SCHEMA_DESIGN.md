# Phase 2: Enhanced Schema Design

> **Status:** In Progress  
> **Objective:** Transition from flat storage to multi-tenant, intent-aware schema with TTL metadata

---

## 1. Current Schema (Legacy)

```
ticker_info (40 columns flat)
├── Static: symbol, name, sector, industry, summary
├── Dynamic: price, market_cap, PE ratios, etc.
└── Timestamps: fetched_at, price_fetched_at

price_history
├── symbol, date, OHLCV
└── No freshness metadata

scan_cache
├── scan_name, params, results, fetched_at
└── Generic, no data-type awareness
```

**Issues:**
- No per-attribute TTL tracking
- No immutability flags for static data
- No data-source tagging
- No bulk query optimization for calculated indicators

---

## 2. New Schema Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATABASE SCHEMA                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  GLOBAL LAYER: Core ticker metadata (immutable once set)             │  │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │  │
│  │  │ tickers          │ │ sectors          │ │ market_context      │   │  │
│  │  │ ─────────────    │ │ ─────────────    │ │ ────────────────     │   │  │
│  │  │ symbol (PK)      │ │ sector_id (PK)   │ │ macro_indicators     │   │  │
│  │  │ name             │ │ sector_name      │ │ last_updated        │   │  │
│  │  │ sector           │ │ etf_ticker       │ │ vix, treasuries, etc │   │  │
│  │  │ industry         │ │ created_at       │ │ is_market_open      │   │  │
│  │  │ business_summary │ │ updated_at       │ │ trading_day         │   │  │
│  │  │ exchange         │ └──────────────────┘ └──────────────────────┘   │  │
│  │  │ created_at       │                                              │  │
│  │  │ is_immutable     │                                              │  │
│  │  └──────────────────┘                                              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  TIME-SERIES LAYER: Price data with source tagging                  │  │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │  │
│  │  │ price_bars       │ │ tickers_indicators│ │ fundamentals_cache  │   │  │
│  │  │ ─────────────    │ │ ──────────────── │ │ ────────────────     │   │
│  │  │ symbol (FK)      │ │ symbol (FK)       │ │ symbol (FK)          │   │
│  │  │ date (PK)        │ │ indicator_name(PK)│ │ fiscal_period (PK)  │   │
│  │  │ open, high, low  │ │ value             │ │ quarter_end_date    │   │
│  │  │ close, volume    │ │ source            │ │ earnings, revenue    │   │
│  │  │ adjusted_close   │ │ last_updated      │ │ eps_actual, eps_est  │   │
│  │  │ source           │ │ is_immutable      │ │ pe_ratio             │   │
│  │  │ is_immutable     │ │ formula           │ │ fetched_at           │   │
│  │  └──────────────────┘ └──────────────────┘ └──────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  METADATA LAYER: Contextual attributes with TTL tracking            │  │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐   │  │
│  │  │ ticker_metadata  │ │ refresh_queue     │ │ calculated_indicators│   │  │
│  │  │ ─────────────    │ │ ─────────────    │ │ ────────────────    │   │
│  │  │ symbol (FK)      │ │ symbol (FK)       │ │ symbol (FK)         │   │
│  │  │ attribute (PK)   │ │ data_type (PK)    │ │ indicator (PK)      │   │
│  │  │ value            │ │ priority          │ │ value (JSONB)       │   │
│  │  │ data_type        │ │ enqueued_at       │ │ params (JSONB)      │   │
│  │  │ update_ttl       │ │ retry_count       │ │ formula             │   │
│  │  │ stale_after      │ │ status            │ │ computed_at         │   │
│  │  │ source           │ │ last_error       │ └──────────────────────┘   │
│  │  │ is_immutable     │ └──────────────────┘                            │  │
│  │  └──────────────────┘                                                  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Table Definitions

### 3.1 `tickers` - Global Identity Table

```sql
CREATE TABLE tickers (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    business_summary TEXT,
    exchange TEXT,
    is_immutable BOOLEAN DEFAULT FALSE,  -- TRUE: never re-fetch core data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Index for bulk sector lookups
CREATE INDEX idx_tickers_sector ON tickers(sector);
```

### 3.2 `price_bars` - Time-Series OHLCV

```sql
CREATE TABLE price_bars (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,  -- YYYY-MM-DD format
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adjusted_close REAL,
    volume REAL,
    source TEXT DEFAULT 'yfinance',  -- For data provenance
    is_immutable BOOLEAN DEFAULT TRUE,  -- Historical data never changes
    PRIMARY KEY (symbol, date)
);
-- Indexes for efficient time-range queries
CREATE INDEX idx_price_bars_date ON price_bars(date);
CREATE INDEX idx_price_bars_symbol ON price_bars(symbol);
CREATE INDEX idx_price_bars_immutable ON price_bars(is_immutable);
```

### 3.3 `ticker_metadata` - Attribute TTL Tracking

```sql
CREATE TABLE ticker_metadata (
    symbol TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value REAL,
    value_text TEXT,  -- For non-numeric data
    data_type TEXT,  -- 'static', 'semi_dynamic', 'highly_dynamic'
    update_ttl_seconds INTEGER,  -- NULL = is_immutable
    stale_after REAL,  -- Unix timestamp
    source TEXT,
    is_immutable BOOLEAN DEFAULT FALSE,
    fetched_at REAL,  -- Unix timestamp
    PRIMARY KEY (symbol, attribute)
);
CREATE INDEX idx_metadata_symbol ON ticker_metadata(symbol);
CREATE INDEX idx_metadata_stale ON ticker_metadata(stale_after) WHERE stale_after IS NOT NULL;
```

### 3.4 `refresh_queue` - Background Worker Queue

```sql
CREATE TABLE refresh_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    data_type TEXT NOT NULL,
    priority INTEGER DEFAULT 1,  -- 1=high, 2=medium, 3=low
    enqueued_at REAL DEFAULT (julianday('now')),
    retry_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    last_error TEXT,
    UNIQUE(symbol, data_type)
);
CREATE INDEX idx_queue_priority ON refresh_queue(priority, enqueued_at);
CREATE INDEX idx_queue_status ON refresh_queue(status) WHERE status = 'pending';
```

### 3.5 `calculated_indicators` - JSONB for Formulas

```sql
CREATE TABLE calculated_indicators (
    symbol TEXT NOT NULL,
    indicator TEXT NOT NULL,
    params JSONB,  -- Store calculation parameters
    value JSONB,    -- Store result and metadata
    computed_at REAL,
    PRIMARY KEY (symbol, indicator)
);
CREATE INDEX idx_indicators_symbol ON calculated_indicators(symbol);
-- GIN index for JSONB queries
CREATE INDEX idx_indicators_params ON calculated_indicators USING GIN(params);
```

### 3.6 `sectors` - Macro Context

```sql
CREATE TABLE sectors (
    sector_name TEXT PRIMARY KEY,
    etf_ticker TEXT,
    macro_impact TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.7 `market_context` - Global Market State

```sql
CREATE TABLE market_context (
    key TEXT PRIMARY KEY,
    value TEXT,
    value_numeric REAL,
    last_updated REAL,
    is_immutable BOOLEAN DEFAULT FALSE
);
-- Pre-populated keys: 'vix', 'treasury_10y', 'sp500_pe', 'market_status', etc.
```

---

## 7. Rate Limiting Guardrails

### Fetch Cooldown Logic

```python
def can_refresh(symbol: str, data_type: str) -> Tuple[bool, str]:
    """
    Determine if a ticker can be refreshed based on rate limiting rules.
    Returns (can_fetch, reason) tuple.
    """
    now = time.time()
    
    # Check last fetch time
    last_fetch = get_last_fetch_time(symbol, data_type)
    if last_fetch and (now - last_fetch) < MIN_REFRESH_INTERVAL:
        return False, f"Cooldown active: {MIN_REFRESH_INTERVAL}s minimum interval"
    
    # Check daily limit
    today_fetches = get_fetch_count_today(symbol, data_type)
    if today_fetches >= DAILY_FETCH_LIMIT:
        return False, f"Daily limit reached: {DAILY_FETCH_LIMIT} fetches/day"
    
    return True, "OK"


def should_return_stale(symbol: str, data_type: str) -> bool:
    """
    When refresh is blocked by rate limiting, return stale data with warning.
    """
    cached = get_cached_data(symbol, data_type)
    if cached:
        age = time.time() - cached.get("fetched_at", 0)
        return {
            "data": cached["value"],
            "warning": f"Returning stale data ({age//3600}h old) due to rate limit",
            "stale": True
        }
    return None  # No data available at all
```

### Queue Priority Adjustment

```python
def enqueue_refresh(symbol: str, data_type: str, priority: int = 2):
    """Enqueue for background refresh with cooldown check."""
    if can_refresh(symbol, data_type)[0]:
        priority = 1  # High priority if we can fetch now
    else:
        priority = 3  # Low priority - wait for cooldown
    
    conn.execute("""
        INSERT OR REPLACE INTO refresh_queue (symbol, data_type, priority, enqueued_at)
        VALUES (?, ?, ?, julianday('now'))
    """, (symbol, data_type, priority))
```

---

## 4. Data Type Enum

```python
class DataFreshnessTier:
    IMMUTABLE = "immutable"        # Never refresh (historical prices, quarterly earnings)
    SEMI_DYNAMIC = "semi_dynamic"  # Refresh every 1-7 days (SMA, dividends, fundamentals)
    HIGHLY_DYNAMIC = "highly_dynamic"  # Refresh every 30-60 min (price check, not real-time)
```

### Default TTLs by Tier (Conservative - DOS Prevention)

| Tier | TTL | Use Cases | Min Refresh Floor |
|------|-----|-----------|-------------------|
| `immutable` | Never | Historical prices, past quarterly earnings, business summary | N/A |
| `semi_dynamic` | 1-7 days (86400-604800s) | PE ratios, fundamentals, sector allocation, dividends | 24h |
| `highly_dynamic` | 30-60 min (1800-3600s) | Price check (not true real-time) | 30min |

### Rate Limiting Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MIN_REFRESH_INTERVAL` | 1800s (30 min) | Never fetch same ticker more than 48x/day |
| `DAILY_FETCH_LIMIT` | 48 | Max fetches per ticker per day |
| `BULK_FETCH_BATCH` | 10 | Max tickers per bulk request |

---

## 5. Access Width Optimization

### Bulk Lookup Pattern

```python
def get_bulk_metadata(symbols: List[str], attribute: str) -> Dict[str, float]:
    """Fetch same attribute for multiple tickers in one query."""
    placeholders = ",".join(["?"] * len(symbols))
    rows = conn.execute(f"""
        SELECT symbol, value 
        FROM ticker_metadata 
        WHERE symbol IN ({placeholders}) AND attribute = ?
    """, symbols + [attribute])
    return {r["symbol"]: r["value"] for r in rows}

# Usage: Get 50 tickers' PE ratio in 1 query instead of 50 queries
pe_ratios = get_bulk_metadata(["AAPL", "MSFT", "GOOGL", ...], "trailing_pe")
```

### JSONB Indicator Storage

```python
# Store SMA calculation with parameters
conn.execute("""
    INSERT INTO calculated_indicators (symbol, indicator, params, value, computed_at)
    VALUES (?, ?, ?, ?, ?)
""", (
    "AAPL",
    "sma_50",
    json.dumps({"period": 50, "source": "close", "data_range": "1y"}),
    json.dumps({"value": 178.45, "trend": "bullish", "crossed_above": "sma_200"}),
    time.time()
))

# No schema migration needed when adding new indicators
```

---

## 6. Immutability Flag Logic

### Auto-Set Rules

```python
def classify_immutable(symbol: str, attribute: str, value: Any) -> bool:
    """Determine if data is immutable based on rules."""
    
    # Historical price data - always immutable
    if attribute in ("open", "high", "low", "close", "adjusted_close", "volume"):
        return True
    
    # Past quarterly earnings - immutable after quarter closes
    if attribute.startswith(("eps_actual_", "revenue_actual_", "earnings_actual_")):
        return True
    
    # Business summary - rarely changes
    if attribute in ("business_summary", "sector", "industry"):
        return True
    
    # Dynamic data - never immutable
    if attribute in ("current_price", "intraday_volume", "rsi"):
        return False
    
    # Fundamentals based on historical quarters - immutable
    if attribute.startswith("pe_ratio_q"):
        return True
    
    return False  # Default to mutable
```

---

## 7. Migration Path

### Phase 2.1: Add New Tables (Non-Breaking)

```sql
-- Add new tables alongside existing ones
CREATE TABLE IF NOT EXISTS ticker_metadata (
    symbol TEXT NOT NULL,
    attribute TEXT NOT NULL,
    ...
    PRIMARY KEY (symbol, attribute)
);

CREATE TABLE IF NOT EXISTS refresh_queue (
    ...
);
```

### Phase 2.2: Backfill Metadata

```python
def backfill_metadata():
    """Transfer existing ticker_info columns to ticker_metadata with TTLs."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM ticker_info").fetchall()
    
    for row in rows:
        symbol = row["symbol"]
        for col in MAPPED_COLUMNS:
            value = row.get(col)
            if value is not None:
                data_type = get_data_type(col)
                is_immutable = classify_immutable(symbol, col, value)
                insert_metadata(symbol, col, value, data_type, is_immutable)
```

### Phase 2.3: Deprecate Flat Tables (Future)

- Keep `ticker_info` as view over `tickers` + `ticker_metadata`
- Migrate APIs to use new tables
- Drop legacy columns after verification

---

## 8. Phase 2 Completion Checklist

- [x] Design Global/Time-Series/Metadata hierarchy
- [ ] Create SQL migration script
- [ ] Define TTL constants
- [ ] Implement immutability classification
- [ ] Add bulk query helpers
- [ ] Add JSONB indicator support
- [ ] Write backfill script
- [ ] Test migration

---

*Next Action: Proceed to Phase 3 - DataOrchestrator Implementation*

---

## Appendix A: Attribute to DataType Mapping (Conservative)

| Attribute | DataType | TTL (seconds) | Immutable | Min Refresh Floor |
|-----------|----------|---------------|-----------|-------------------|
| `open`, `high`, `low`, `close`, `adjusted_close`, `volume` | immutable | Never | YES | N/A |
| `trailing_pe`, `forward_pe`, `price_to_book` | semi_dynamic | 86400 (24h) | NO | 24h |
| `sma_50`, `sma_200` | semi_dynamic | 86400 (24h) | NO | 24h |
| `rsi_14` | highly_dynamic | 3600 (60m) | NO | 30min |
| `current_price` | highly_dynamic | 3600 (60m) | NO | 30min |
| `dividend_yield` | semi_dynamic | 604800 (7d) | NO | 24h |
| `eps_actual_q1_2025` | immutable | Never | YES | N/A |
| `business_summary` | immutable | Never | YES | N/A |
| `sector`, `industry` | immutable | Never | YES | N/A |

**Rate Limiting Constants:**
- `MIN_REFRESH_INTERVAL`: 1800s (30 min) - never fetch same ticker more than 48x/day
- `DAILY_FETCH_LIMIT`: 48 max fetches per ticker per day
- `BULK_FETCH_BATCH`: 10 tickers per bulk request

---

## Appendix B: Bulk Query Patterns

```sql
-- Get all stale indicators for batch refresh
SELECT symbol, attribute, stale_after 
FROM ticker_metadata 
WHERE stale_after < ? AND is_immutable = FALSE
ORDER BY stale_after ASC
LIMIT 100;

-- Get all data for a ticker in single query
SELECT * FROM ticker_metadata WHERE symbol = ?;

-- Get calculated indicators with specific parameters
SELECT * FROM calculated_indicators 
WHERE symbol = ? AND params->>'period' = '50';
```