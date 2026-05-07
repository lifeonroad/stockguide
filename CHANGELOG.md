# Changelog

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
