# Rational Equity Dashboard — Project Context

## Overview
Stock analysis dashboard with dip hunting, superinvestor tracking, economic indicators, screeners, and portfolio management. FastAPI backend + vanilla JS SPA frontend.

## Entry Points
- `run.py` — launches uvicorn from `backend/` on port 8000
- `start.sh` — handles venv, deps (MD5 checksum), and launch
- `backend/main.py` — FastAPI app with all routes defined inline

## API Endpoints (~35)
- Market: `/api/market-status`, `/api/macro`, `/api/economic-indicators`, `/api/money-flow`, `/api/news`
- Sectors: `/api/industries/top`, `/api/stocks/{industry}`
- Analysis: `/api/analyze/{symbol}`, `/api/research/{symbol}`, `/api/research/trends/{symbol}`, `/api/quotes`
- Screeners: `/api/screeners/{strategy_id}`, `/api/moonshots`, `/api/small-caps`, `/api/contrarian/opportunities`, `/api/international/picks`
- Superinvestors: `/api/superinvestors`, `/api/copycat`
- Dip Hunter: `/api/dip-hunter/etfs`, `/api/dip-hunter/stocks`, `/api/dip-hunter/summary`, `/api/opportunities`
- Alpha: `/api/alpha/cycle`
- Portfolios: full CRUD + trade/import PDF at `/api/portfolios/*`, `/api/positions/*`
- Admin: cache stats/clear, universe update, data-source toggle, scan progress
- Slow endpoints (300s timeout): screeners, moonshots, small-caps, contrarian, international, dip-hunter, copycat, superinvestors

## Tech Stack
- Backend: Python 3.10+, FastAPI 0.111, uvicorn, gunicorn
- Frontend: Vanilla JS, TailwindCSS (CDN), Chart.js (CDN), Google Fonts
- Data: yfinance (primary), yahooquery (fallback), defeatbeta (toggleable, `DEFEATBETA_ENABLED=0`)
- Deploy: Render.com free tier, 1 worker/4 threads, 120s timeout

## Architecture — Caching (5 layers)
1. **In-memory SWR cache** (`cache_utils.py`): `timed_cache` decorator with soft/hard TTL, stale-while-revalidate, request dedup, circuit breaker (3 failures → 5min open)
2. **SQLite persistent cache** (`persistent_cache.py`): WAL mode, 3 tables (ticker_info, price_history, scan_cache), staleness rules per data type
3. **Rate limiter** (`rate_limiter.py`): 30min between fetches, 48/day per ticker, bulk batch size 10
4. **Intelligent TTL** (`intelligent_ttl.py`): adaptive by beta, earnings proximity, market hours, sector risk
5. **Data orchestrator** (`data_orchestrator.py`): DB-first → check freshness → rate limiter → network → persist

Flow: Business Logic → DataOrchestrator → SQLite → RateLimiter → NetworkClient (yfinance/yahooquery with retry + circuit breaker)

## Frontend Components (9 modules in `js/components/`)
`marketStatus.js`, `researchUi.js`, `thematic.js`, `screenerUi.js`, `economics.js`, `dipHunter.js`, `alpha.js`, `smallCaps.js`, `international.js`

## Testing
- `backend/tests/functional_test.py` (70 lines) — 8 endpoint integration tests
- `backend/tests/comprehensive_test.py` (176 lines) — more extensive endpoint tests
- Both assume server running on `http://0.0.0.0:8000`
- `test_screeners.py` — standalone screener test at root
- No pytest/unittest framework used

## Conventions
- No frontend framework; all state in `localStorage` + DOM manipulation
- Singletons: PortfolioManager, RateLimiter, NetworkClient, DataOrchestrator
- Theme system: dark/light/solaris/contrast via CSS variables, persisted in localStorage
- Data source toggle at runtime with instant cache clear
- Background cache warming on startup for critical paths

## Config
- `.env`: `DEFEATBETA_ENABLED=0`
- `requirements.txt`: fastapi, starlette, uvicorn, yfinance, yahooquery, pandas, numpy, feedparser, requests, pdfplumber, python-multipart, gunicorn, python-dotenv
- `render.yaml`: Python 3.13, Oregon region

## Useful Commands
- Run: `python run.py` or `./start.sh`
- Start for testing (no reload): `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000`
- If tests exist and server is running: `python backend/tests/comprehensive_test.py` or `python backend/tests/functional_test.py`
- There is no lint/typecheck command configured

## 🚫 Commit Quality Gate — Sanity/Smoke Test Requirement

**Before any commit, ALL of the following must pass.** Do not commit if any endpoint returns an error, times out, or returns empty data where real data is expected.

### 1. All API endpoints must return 200 with valid data

Run the following health check with the server running. Every endpoint must return HTTP 200 and contain meaningful data (not empty arrays/objects where real data is expected).

```bash
# Fast endpoints (should respond in < 5s each)
for ep in "/" "/api/market-status" "/api/macro" "/api/news" "/api/money-flow" \
          "/api/economic-indicators" "/api/industries/top" "/api/admin/data-source" \
          "/api/admin/cache/stats"; do
  code=$(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "http://0.0.0.0:8000$ep")
  echo "$ep -> $code"
done

# Slow endpoints (may need 60-120s each on cold cache)
for ep in "/api/stocks/Technology" "/api/analyze/AAPL" "/api/dip-hunter/summary" \
          "/api/dip-hunter/etfs" "/api/screeners/deep_value"; do
  code=$(curl -s --max-time 120 -o /dev/null -w "%{http_code}" "http://0.0.0.0:8000$ep")
  echo "$ep -> $code"
done
```

Also verify data is non-empty:
```bash
# Money flow must have 13 symbols
curl -s --max-time 15 http://0.0.0.0:8000/api/money-flow | python3 -c "import json,sys; d=json.load(sys.stdin); assert len(d['data']) == 13, f'Expected 13, got {len(d[\"data\"])}'; print('OK: 13 symbols')"

# Market status must have ratio and rating
curl -s --max-time 15 http://0.0.0.0:8000/api/market-status | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ratio_percent'), 'Missing ratio'; assert d.get('rating'), 'Missing rating'; print(f'OK: {d[\"rating\"]}')"

# Analyze must return a rating
curl -s --max-time 120 http://0.0.0.0:8000/api/analyze/AAPL | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('rating'), 'Missing rating'; print(f'OK: {d[\"rating\"]}')"

# Dip hunter summary must return data
curl -s --max-time 120 http://0.0.0.0:8000/api/dip-hunter/summary | python3 -c "import json,sys; d=json.load(sys.stdin); assert len(d) > 0; print(f'OK: {len(d)} items')"

# Test that the server is stable (no circuit breaker open)
curl -s --max-time 15 http://0.0.0.0:8000/api/stocks/Technology | python3 -c "import json,sys; d=json.load(sys.stdin); assert len(d.get('top_stocks',[])) > 0; print(f'OK: {len(d[\"top_stocks\"])} tech picks')"
```

### 2. No circuit breaker may be open

Check the server log for circuit breaker errors:
```bash
grep -c "CIRCUIT OPEN\|Invalid Crumb\|Too Many Requests" /path/to/server.log
```
If > 0 circuit breaker errors appear, the Yahoo API is rate-limiting and the web-app will show blank pages. **Do not commit in this state.** Restart the server and wait 60s for staggered warming to complete, then re-test.

### 3. Server must be stable (no crashes on repeated requests)

Hit the 5 most critical endpoints sequentially — if any hangs or crashes the worker, fix before commit:
```bash
for ep in "/api/market-status" "/api/macro" "/api/money-flow" "/api/industries/top" "/api/analyze/AAPL"; do
  code=$(curl -s --max-time 60 -o /dev/null -w "%{http_code}" "http://0.0.0.0:8000$ep")
  [ "$code" != "200" ] && echo "FAIL: $ep -> $code" || echo "OK: $ep -> $code"
done
```

### 4. Frontend smoke test

Load the app's root URL and verify all JS modules are served correctly:
```bash
curl -s --max-time 5 http://0.0.0.0:8000/ | grep -q "app.js" || echo "FAIL: app.js not loaded"
curl -s --max-time 5 http://0.0.0.0:8000/static/js/components/marketStatus.js | head -1
curl -s --max-time 5 http://0.0.0.0:8000/static/portfolio.js | head -1
```

### When to skip the smoke test

Only skip if the change is purely cosmetic (CSS, typo fixes, comments, documentation). Any backend logic, data fetching, caching, or frontend data-rendering change requires the full smoke test above.
