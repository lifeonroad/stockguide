# Project Context & Onboarding for AI Agents

## What Is This?

**Rational Equity Dashboard** — a self-hosted stock analysis SPA (single HTML page + vanilla JS frontend, FastAPI backend). It aggregates market data from Yahoo Finance (with optional defeatbeta proxy), runs analysis strategies (Buffett/Burry/Lynch), tracks superinvestor 13F filings, scans for dips/opportunities, manages portfolios, and more.

Target user: retail investor who wants institutional-grade data without paying for Bloomberg.

---

## Quick Start

```bash
cd stockguide
./start.sh              # auto: venv + deps + launch
# or: python3 run.py
# or: cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — the dashboard loads immediately; cache warming runs in background (~30s).

---

## Latest State (as of most recent session)

**Uncommitted changes**: See "Progress" section below for latest work.

**Recent work stream (in order)**:
1. DB-first architecture (SQLite persistent cache + data orchestrator)
2. SWR caching + circuit breaker + cache warming
3. Dynamic universe optimization (per-sector disk cache, chunked scoring)
4. Data routing through `data_client.py` facade (10 modules migrated)
5. Opportunity engine (market regime detection + context-aware dip classification)
6. Dip hunter dynamic sector expansion + performance fix (293s → 18.5s)
7. SEC EDGAR 13F filing pipeline (free API, CUSIP→ticker, QoQ changes)
8. Inflation busters screener, superinvestor detail modal, yahooquery migration
9. Dataroma scraper (holdings, activity, history, grand portfolio, all managers, all activity)
10. Guru Consensus panel — Grand Portfolio integrated into superinvestor tab
11. 6-month comparison column on quarter views — Qtr Buys/Sells now show `in_6mo` badge by cross-referencing 6-month grand portfolio data
12. Consensus Picks view — composite scoring (0-100) across sustained buying, ownership breadth, net manager activity, 52w low proximity, and portfolio weight

---

## Project Layout

```
stockguide/                     # Git root
├── AGENTS.md                   # ← YOU ARE HERE
├── CHANGELOG.md                # Chronological feature log
├── DEPLOYMENT.md               # Render.com deploy guide
├── GIT_COMMIT_GUIDE.md         # Commit workflow reference
├── backend/
│   ├── main.py                 # FastAPI app (897 lines, all routes inline)
│   ├── data_client.py          # Facade over yfinance/defeatbeta
│   ├── cache_utils.py          # timed_cache decorator (SWR + circuit breaker)
│   ├── persistent_cache.py     # SQLite persistent cache (WAL mode)
│   ├── data_orchestrator.py    # DB-first fetch orchestration
│   ├── rate_limiter.py         # Per-ticker fetch rate limiting
│   ├── intelligent_ttl.py      # Adaptive TTL by beta/earnings/sector
│   ├── network_client.py       # yfinance/yahooquery with retry
│   ├── dip_hunter.py           # Dip scanning engine
│   ├── opportunity_engine.py   # Market regime + context-aware dips
│   ├── screener.py             # Legacy screener (~still used)
│   ├── screeners.py            # New screener engine
│   ├── universe.py             # Hardcoded ticker lists
│   ├── dynamic_universe.py     # Dynamic universe scoring
│   ├── updater.py              # SP500/Nasdaq fetcher
│   ├── superinvestors_live.py  # Live 13F data (SEC EDGAR API)
│   ├── sec_13f.py / sec_13f_db.py / cusip_utils.py  # EDGAR pipeline
│   ├── portfolio.py            # Portfolio CRUD (SQLite)
│   ├── momentum.py             # 8-factor momentum scoring
│   ├── filing_calendar.py      # 13F filing window intelligence
│   ├── analyst.py              # Analysis strategies (Buffett/Burry/Lynch)
│   ├── research.py             # Research endpoint logic
│   ├── economic.py             # FRED economic data
│   ├── money_flow.py           # Money flow analysis
│   ├── market_data.py          # Buffett indicator, macro
│   ├── indicators.py           # Technical indicators
│   ├── macro.py                # Macro trends
│   ├── news.py                 # News fetching
│   ├── forecasting.py          # Forecasting models
│   ├── cycle_analytics.py      # Market cycle analytics
│   ├── technical_zones.py      # Support/resistance zones
│   ├── contrarian.py           # Contrarian opportunities
│   ├── international.py        # International stock picks
│   ├── small_caps.py           # Small cap screeners
│   ├── moonshots.py            # Moonshot screener
│   ├── filing_calendar.py      # Filing schedule
│   ├── portfolio_signals.py    # Portfolio signal generation
│   ├── portfolio_parser.py     # PDF import
│   ├── memory_watch.py         # Memory monitoring
│   ├── status_check.py         # Status check utilities
│   ├── sector_cache/           # Per-sector JSON cache files
│   └── tests/
│       ├── functional_test.py       # 8 endpoint integration tests
│       └── comprehensive_test.py    # 176 lines, broader coverage
├── frontend/
│   ├── index.html              # Single-page app (all views)
│   ├── app.js                  # Main orchestrator (tab switching, init)
│   ├── portfolio.js            # Portfolio CRUD UI
│   ├── auto_categorize.js      # Auto-categorization
│   └── js/
│       ├── api.js              # API base config
│       ├── utils.js            # Shared formatting utilities
│       └── components/
│           ├── marketStatus.js
│           ├── researchUi.js
│           ├── thematic.js      # Superinvestors, moonshots
│           ├── screenerUi.js
│           ├── economics.js     # Economic indicators, money flow, news
│           ├── dipHunter.js
│           ├── alpha.js
│           ├── smallCaps.js
│           ├── international.js
│           └── momentum.js
├── docs/                       # Additional docs
├── run.py                      # Dev entry point
├── start.sh                    # Smart launcher
├── requirements.txt            # Python deps
├── render.yaml                 # Render.com config
└── README.md                   # User-facing README
```

---

## Architecture — Caching Layers (5 tiers)

All data flows through this pipeline:

```
Business Logic → DataOrchestrator → SQLite → RateLimiter → NetworkClient
```

1. **timed_cache** (`cache_utils.py`) — in-memory SWR decorator with soft/hard TTL, request dedup, circuit breaker (3 fails → 5min open)
2. **SQLite** (`persistent_cache.py`) — WAL mode, 3 tables (ticker_info, price_history, scan_cache), per-type staleness rules
3. **RateLimiter** (`rate_limiter.py`) — 30min between fetches, 48/day per ticker
4. **IntelligentTTL** (`intelligent_ttl.py`) — adaptive by beta, earnings proximity, market hours, sector risk
5. **DataOrchestrator** (`data_orchestrator.py`) — DB-first → check freshness → rate limit → fetch → persist

**Critical**: The server starts fast (instant 200) but internal caches are cold. Background warming runs staggered over ~60s. If you restart the server and immediately hit rate-limited endpoints, Yahoo may rate-limit you, causing circuit breakers to open = blank pages.

---

## API Endpoints (~35)

### Fast (<5s)
| Endpoint | Description |
|---|---|
| `GET /` | Serve index.html |
| `GET /api/market-status` | Buffett indicator, market ratio, rating |
| `GET /api/macro` | Macro trends |
| `GET /api/economic-indicators` | FRED economic data |
| `GET /api/money-flow` | 13-symbol money flow |
| `GET /api/news` | Market news |
| `GET /api/industries/top` | Industry rankings |
| `GET /api/admin/data-source` | Get/set data source toggle |
| `GET /api/admin/cache/stats` | Cache + circuit breaker stats |
| `POST /api/admin/cache/clear` | Clear all caches |
| `GET /api/filing/status` | 13F filing window status |

### Slow (10-120s, especially on cold cache)
| Endpoint | Description |
|---|---|
| `GET /api/stocks/{industry}` | Top stocks in sector |
| `GET /api/analyze/{symbol}` | Stock analysis (strategy param) |
| `GET /api/dip-hunter/summary` | Dip hunter overview |
| `GET /api/dip-hunter/etfs` | ETF dip scan |
| `GET /api/dip-hunter/stocks` | Stock dip scan (deprecated, use opportunities) |
| `GET /api/opportunities` | Context-enriched dip opportunities |
| `GET /api/screeners/{strategy_id}` | Pro screeners |
| `GET /api/moonshots` | Moonshot analysis |
| `GET /api/small-caps` | Small cap picks |
| `GET /api/contrarian/opportunities` | Contrarian picks |
| `GET /api/international/picks` | International picks |
| `GET /api/superinvestors` | Superinvestor list |
| `GET /api/copycat` | Copycat portfolio |
| `GET /api/alpha/cycle` | Cycle analytics |

### Portfolio (CRUD)
| Endpoint | Method | Description |
|---|---|---|
| `/api/portfolios` | GET/POST | List/create portfolios |
| `/api/portfolios/{id}` | GET/PUT/DELETE | Single portfolio CRUD |
| `/api/portfolios/{id}/positions` | GET | Positions in portfolio |
| `/api/positions` | POST | Add position |
| `/api/positions/{id}` | PUT/DELETE | Update/delete position |
| `/api/import-pdf` | POST | Import PDF trade confirmation |
| `/api/alphavantage/key` | GET | Check Alpha Vantage key |

### Admin
| Endpoint | Description |
|---|---|
| `GET /api/admin/update-universe` | Trigger universe re-score |
| `GET /api/admin/scan-progress` | Scan progress status |

---

## Frontend Architecture

- **SPA** with tab-based navigation (`app.js:switchTab()`)
- All state in `localStorage` + DOM manipulation (no framework)
- 9 feature modules in `js/components/`, loaded as ES6 modules
- Theme system: dark/light/solaris/contrast via `data-theme` attribute + CSS variables
- **Cache-busting**: `index.html` has `Cache-Control: no-cache`, JS imports use `?v=N` (currently `v=17`). Bump on frontend changes.

---

## Known Issues & Pain Points

### Active Bugs
1. **TradingView link** shows AAPL for all stocks (DOM update timing issue in modal)
2. **Circuit breaker cascading** — Yahoo rate limits can cascade across endpoints, causing blank pages. Server restart + 60s wait is the fix.
3. **`_bulk_fundamentals` hang** — Fixed in HEAD but worth watching for recurrence

### Architectural Debt
1. **`screener.py` vs `screeners.py`** — Two screener engines coexist; `main.py` imports from both. Should consolidate into `screeners.py`.
2. **`superinvestors.py` vs `superinvestors_live.py`** — Same pattern; legacy mock data file still present.
3. **Hardcoded ticker lists** in `universe.py` and `screener.py` — `updater.py` can fetch SP500/Nasdaq but isn't fully integrated.
4. **No pytest framework** — Tests are standalone scripts. No `pytest.ini` or config.
5. **No lint/typecheck** configured at all.
6. **Monolithic `main.py`** (897 lines) — all routes defined inline. No router separation.
7. **Global `DATA_CACHE`** in `screeners.py` — not worker-safe for multi-process gunicorn.
8. **Portfolio DB schema** managed via `CREATE TABLE IF NOT EXISTS` strings — no Alembic migrations.

---

## Development Workflow

### Before Committing
The commit quality gate in the bottom half of this file **must pass**. Run the smoke tests:

```bash
# Fast endpoints
for ep in "/" "/api/market-status" "/api/macro" "/api/news" "/api/money-flow" \
          "/api/economic-indicators" "/api/industries/top" "/api/admin/data-source" \
          "/api/admin/cache/stats"; do
  code=$(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "http://0.0.0.0:8000$ep")
  echo "$ep -> $code"
done

# Slow endpoints
for ep in "/api/stocks/Technology" "/api/analyze/AAPL" "/api/dip-hunter/summary" \
          "/api/dip-hunter/etfs" "/api/screeners/deep_value"; do
  code=$(curl -s --max-time 120 -o /dev/null -w "%{http_code}" "http://0.0.0.0:8000$ep")
  echo "$ep -> $code"
done
```

### Running Tests
```bash
# With server running on :8000:
python backend/tests/comprehensive_test.py
python backend/tests/functional_test.py
python test_screeners.py
```

### Commit Message Style
Follow the existing pattern from `git log`:
```
<action> <component>: <description>

- bullet points for details
```

Examples from recent commits:
- `Add inflation busters screener, superinvestor detail modal, yahooquery migration`
- `Fix SEC EDGAR pipeline, SQLite lock contention, Yahoo rate limiting`
- `Add momentum investing tab: 8-factor scoring engine, UI component`

---

## Config & Environment

`.env` file (local only, not deployed):
```
DEFEATBETA_ENABLED=0
```

Toggle at runtime via `GET /api/admin/data-source` or the footer toggle in the UI. Cache is auto-cleared on toggle.

---

## Deploy

Render.com free tier, auto-deploys from git push. See `DEPLOYMENT.md`.
- 1 worker, 4 threads, 120s timeout
- Python 3.13, Oregon region
- Cold start: 30-60s
- Keep-alive via cron-job.org recommended

---

## Common Pitfalls for AI Agents

1. **Yahoo rate limits** — After server restart, wait 60s before hammering endpoints. The staggered warming handles this, but if you hit endpoints too fast, circuits open.
2. **`asyncio.to_thread`** — Many sync functions are wrapped in `asyncio.to_thread()`. If the underlying function has a bug, it silently hangs instead of erroring (the timeout in `_to_thread_with_timeout` catches this after 60-300s).
3. **Cache masking bugs** — `@timed_cache` decorators make bugs hard to reproduce. Always clear caches (`POST /api/admin/cache/clear`) when testing changes to data-fetching logic.
4. **Frontend cache** — After changing JS, bump `?v=N` in `index.html`. Otherwise the browser serves stale code.
5. **Two screener files** — `screener.py` (old) and `screeners.py` (new). Check which one `main.py` imports before modifying.
6. **`data_client.py` is the facade** — All new data-fetching code should go through `data_client.py`, not directly call yfinance.
7. **Portfolio manager is a singleton** — Don't re-instantiate; use the module-level instance.
