# Performance Test Plan: DB Integration

## Goal
Verify DB-first architecture improves response times and reduces API calls without breaking existing functionality.

## Metrics

| Metric | Target | Measure |
|--------|--------|---------|
| Cache hit response time | < 50ms | get_ticker_info cached |
| Cache miss response time | < 5s | get_ticker_info first fetch |
| Background refresh trigger | Fires on stale | needs_refresh() returns True |
| DB write persistence | All 40 columns saved | Verify DB read after write |
| API call reduction | 100% for cached | No yfinance calls on cache hit |

## Tests

### 1. Cache Hit Performance
**Test:** Call `get_ticker_info('AAPL')` multiple times on already-cached ticker
**Expected:** First call DB read (~10ms), subsequent calls from in-memory cache (<1ms)
**Script:** `time curl localhost:8000/api/ticker/AAPL` (repeat 3x)

### 2. Cache Miss Performance
**Test:** Call `get_ticker_info('ZZZZ_TEST_TICKER_999')` - new symbol not in DB
**Expected:** Live fetch triggers (~2-5s), then persists to DB
**Acceptance:** Response returns within 10s, DB has entry afterward

### 3. Background Refresh Trigger
**Test:** Call `get_ticker_info()` on stale data (price_fetched_at > 5min old)
**Expected:** Returns cached data immediately, background thread fires refresh
**Check:** Server logs show "Background refresh complete" message

### 4. Column Persistence
**Test:** Fetch AAPL, read new columns (profit_margin, peg_ratio, etc.)
**Expected:** Values returned (not 0 or None)
**Acceptance:** At least peg_ratio has a value (AAPL typically has ~2.5-3.0)

### 5. Dip Hunter Performance
**Test:** `scan_stock_dips()` on cached data
**Expected:** Uses DB price history, no/yfinance calls for cached tickers
**Measure:** Response time < 10s (vs previous ~30s)

### 6. Sector Metrics Performance
**Test:** `get_sector_metrics_from_constituents('Technology')`
**Expected:** DB bulk read for cached tickers
**Measure:** Response time < 100ms (vs previous ~3s)

## Commands to Run

```bash
# 1. Check DB stats
cd backend && python3 -c "from persistent_cache import get_db_stats; print(get_db_stats())"

# 2. Cache hit test (should be fast)
curl -w "\nTime: %{time_total}s\n" localhost:8000/api/ticker/AAPL

# 3. Check staleness
cd backend && python3 -c "from persistent_cache import needs_refresh; print(needs_refresh('AAPL', 'price'))"

# 4. Test new columns
cd backend && python3 -c "from data_client import get_ticker_info; i=get_ticker_info('AAPL'); print(f'pegRatio: {i.get(\"pegRatio\")}, profitMargin: {i.get(\"profitMargin\")}')"
```

## Acceptance Criteria
- [ ] Cache hit < 50ms
- [ ] Cache miss < 10s (includes DB persist)
- [ ] Background refresh fires for stale data
- [ ] New columns (peg_ratio, profit_margin, etc.) have values for AAPL
- [ ] All imports still work
- [ ] No regression in existing functionality