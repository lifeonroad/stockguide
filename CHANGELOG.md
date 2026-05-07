# Changelog

## [2026-05-07] — Dip Hunter Performance Fix

### Fixed
- **`dip_hunter.py` batch download**: Fixed MultiIndex column parsing in `_fetch_batch_history()` — was checking `data.columns.levels[0]` for symbols but yfinance puts symbols in `levels[1]`. Now correctly extracts per-ticker DataFrames from batch `yf.download()` results.
  - First run: ~293s (fundamentals via defeatbeta, 24h cache) → subsequent calls <1ms
  - Price history batch: 98 tickers in ~5.6s (was failing with 0 tickers)
  - Pre-filter by drop % reduces fundamentals calls from 98 → ~91 candidates
- **`main.py` cache warming**: Added dip hunter to background cache warming (delayed 10s after startup to not compete with other warm-up tasks). Server is immediately usable; dip scan runs in background thread.
- **`screener.py`**: Restored missing `import yfinance as yf` after Phase 4 refactor.

### Architecture
- Two-phase dip hunter scan:
  1. Batch price download (`yf.download()` in batches of 50) → ~5s for 98 tickers
  2. Pre-filter by drop %, fetch fundamentals only for candidates via `_bulk_fundamentals()` (ThreadPoolExecutor, 10 workers)
  3. Score all candidates locally (no network calls)
- `@timed_cache` with SWR on `scan_stock_dips()`: 1h hard TTL, 30m soft TTL

## [2026-05-07] — Phase 4: Data Routing & Non-Blocking Endpoints

### New
- **`data_client.get_ticker_info()`**: Unified ticker info facade
  - Merges defeatbeta fundamentals (24h cache) with live yfinance price (5m cache)
  - Returns yfinance-compatible dict — drop-in replacement for `yf.Ticker(symbol).info`
  - Respects `DEFEATBETA_ENABLED` toggle
  - Includes 52-week high/low, 52-week change, volume, dividends from history

### Changed — Retry Hygiene
- **`superinvestors_live.py`**: FMP 13F API calls now use `fetch_with_retry` (3 attempts, 2s base delay)
- **`updater.py`**: Wikipedia scraper uses `fetch_with_retry` for both S&P 500 and Nasdaq 100 fetches
- **`economic.py`**: FRED API calls use `fetch_with_retry`
- **`market_data.py`**: FRED GDP fetch uses `fetch_with_retry`

### Changed — Data Routing (10 modules routed through `data_client.py`)
- **`analyst.py`**: All `yf.Ticker().info` calls → `get_ticker_info()` (insider_transactions kept direct yfinance — no defeatbeta equivalent)
- **`forecasting.py`**: `yf.Ticker().info` → `get_ticker_info()`
- **`copycat.py`**: Per-stock `yf.Ticker().info` → `get_ticker_info()` (0.5s→0.2s delay)
- **`research.py`**: `yf.Ticker().info` → `get_ticker_info()` (removed redundant try/except wrapper)
- **`screener.py`**: Both `yf.Ticker().info` calls → `get_ticker_info()`
- **`small_caps.py`**: Post-filter `yf.Ticker().info` → `get_ticker_info()`
- **`dip_hunter.py`**: Stock scanner uses `get_price_history()` + `get_ticker_info()` (ETF scanning kept direct yfinance — defeatbeta doesn't track ETFs)

### Changed — Non-Blocking Endpoints
- 9 sync endpoints converted to `async def` with `asyncio.to_thread()`:
  - `/api/industries/top`, `/api/stocks/{industry}`, `/api/analyze/{symbol}`
  - `/api/superinvestors`, `/api/admin/update-universe`
  - `/api/copycat`, `/api/moonshots`, `/api/screeners/{strategy_id}`, `/api/quotes`
- Prevents event loop blocking during long-running API calls

### Fixes
- `main.py` `/api/admin/update-universe`: Updated to use `get_sector_stocks_cached()` instead of deprecated `get_dynamic_sector_stocks()`
- Removed stale `sector_cache.json` comment (replaced by per-sector `sector_cache/` directory)

---

## [2026-05-07] — Phase 3: Dynamic Universe Optimization

### New
- **Chunked scoring** in `dynamic_universe.py`
  - Processes ~500 tickers in batches of 100 with 5s stagger delays
  - Incremental merge — sectors become live as they're scored
  - Partial results written to disk after each chunk
- **Per-sector disk cache granularity**
  - Single `sector_cache.json` replaced by `sector_cache/<sector>.json` files
  - Individual sectors can be refreshed without invalidating others
  - 26h TTL per sector file
- **`write_sector_disk_cache()` / `_load_sector_disk_cache()`**: Per-sector disk I/O

### Changed
- **Bulk parallel fetching**: `ThreadPoolExecutor(max_workers=10)` for momentum and fundamentals per chunk
- **Static-first architecture**: `get_sector_stocks_cached()` returns instantly via in-memory → disk cache → static fallback
- **Backwards-compat shim**: `get_dynamic_sector_stocks()` kept for existing callers

### Performance Impact
| Metric | Before | After |
|---|---|---|
| First API response during scoring | Blocked until complete | < 1ms (static fallback) |
| Scoring burst load | ~500 simultaneous requests | 100/chunk, 5s stagger |
| Cache granularity | All-or-nothing single file | Per-sector independent files |

---

## [2026-05-07] — Phase 2: SWR Caching & Cache Warming

### New
- **SWR (Stale-While-Revalidate) pattern** in `cache_utils.py`
  - Three-tier cache states: fresh, stale (SWR active), expired
  - Background refresh triggered during stale period — user gets instant response
  - Default soft TTL = 75% of hard TTL
- **Request deduplication (in-flight coalescing)**
  - Concurrent identical requests share one backend fetch
  - Uses `threading.Event` for efficient wait/notify
- **Cache warming on startup** in `main.py`
  - Pre-warms 5 critical caches before first user arrives
  - Runs asynchronously — server starts immediately

### Changed
- Applied soft/hard TTL tiers to all 22 existing cache decorators
- `get_cache_stats()` now returns detailed per-entry state (fresh/stale/expired, hit counts, age)
- `clear_cache()` now also clears in-flight request slots

### Performance Impact
| Metric | Before | After |
|---|---|---|
| Startup (first user latency) | ~14s cold | ~0ms (pre-warmed) |
| Stale cache response | Blocking refresh | Instant + background refresh |
| Concurrent duplicate requests | N duplicate fetches | 1 fetch, N responses |

---

## [2026-05-07] — Phase 1: Smart Caching & Circuit Breaker

### New
- **`backend/filing_calendar.py`**: 13F SEC filing schedule intelligence
  - Detects filing windows (45 days after quarter end), deadlines, and straggler periods
  - Dynamic cache TTL: 30 days outside window, 6h inside window, 1h on deadline
  - Returns filing status with badge text and color for frontend display
- **`/api/admin/data-source`** (GET/POST): Runtime-toggleable data source switch
- **`/api/admin/cache/stats`** (GET): Cache and circuit breaker statistics
- **`/api/admin/cache/clear`** (POST): Force clear all caches and circuit breakers

### Changed
- **`backend/superinvestors_live.py`**: Filing-aware caching replaces no-cache approach
  - Manual cache with TTL driven by `filing_calendar.py`
  - Zero API calls for ~270 days/year (30-day cache outside window)
  - 4 checks/day during filing window, 24 checks/day on deadline
  - Stale fallback during API failures
- **`backend/screener.py`**: 30min cache on `analyze_sector_fundamentals()` (was: no cache)
  - First call: ~11s, cached call: ~7ms (1,700x speedup)
  - Prevents repeated yfinance API hammering on every sector click
- **`backend/cache_utils.py`**: Circuit breaker pattern added to `timed_cache`
  - 3 consecutive failures → open circuit (5min cooldown)
  - Half-open state allows test request after cooldown
  - Serves stale data during cooldown if available
  - `get_cache_stats()` and `clear_cache()` utilities
- **`backend/data_client.py`**: Runtime-toggleable `DEFEATBETA_ENABLED` flag
  - Module-level mutable state (no server restart required)
  - Clears all caches on toggle to prevent cross-source contamination
  - `is_defeatbeta_enabled()`, `set_defeatbeta_enabled()`, `get_data_source_status()`
- **`frontend/index.html`**: Footer data source toggle + filing status badge
- **`frontend/app.js`**: `toggleDataSource()` function with reload prompt
- **`frontend/js/components/thematic.js`**: Filing status badge rendering with color coding

### Performance Impact
| Metric | Before | After |
|---|---|---|
| Sector analysis (2nd click) | ~11s | ~7ms |
| 13F API calls/year | ~3,650 (4/day × 365) | ~60 (4/day × 15 filing days) |
| API failure resilience | Error propagated | Stale data served for 5min |

---

## [2026-05-07] — Data Source Toggle + Cache Fixes

### Changed
- **`backend/data_client.py`**: Added `DEFEATBETA_ENABLED` environment variable toggle (default: `1`). When set to `0`, all data functions bypass defeatbeta and use yfinance/yahooquery directly. Each function checks the flag at entry — no duplicate code paths.
- **`backend/main.py`**: Added `Cache-Control: no-cache` headers to `index.html` response to prevent stale browser caching.
- **`frontend/index.html`**: Bumped script cache-busting versions to `?v=17`.

### Fixed
- **`frontend/index.html`**: ID mismatch — `superinvestor-view` → `superinvestors-view` (matches `app.js` tab logic).
- **`frontend/index.html`**: ID mismatch — `moonshot-view` → `moonshots-view` (matches `app.js` tab logic).
- **`frontend/index.html`**: Removed duplicate `moonshot-view` div that appeared twice in the file.
- **`frontend/index.html`**: Removed orphaned `</main>` closing tag with no matching open tag.

### New Config
| Variable | Default | Description |
|---|---|---|
| `DEFEATBETA_ENABLED` | `1` | Set to `0` to disable defeatbeta and fall back to yfinance/yahooquery |

### Usage
```bash
# Defeatbeta enabled (default)
python3 run.py

# yfinance-only mode
DEFEATBETA_ENABLED=0 python3 run.py
```
