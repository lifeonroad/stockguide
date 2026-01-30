# Gap Analysis & Improvement Roadmap

## 1. Code Redundancy & Refactoring
*   **Screener Duplication**: 
    *   *Gap*: `screener.py` (legacy) and `screeners.py` (new engine) coexist. `main.py` imports from both.
    *   *Fix*: Merge `SECTOR_STOCKS` into `universe.py`. Refactor `main.py` to use `screeners.py` primarily. Deprecate `screener.py`.
*   **Superinvestor Logic**:
    *   *Gap*: `superinvestors.py` (mock data?) versus `superinvestors_live.py` (API/Scraper?).
    *   *Fix*: Consolidate into a single service. Ensure fallback to static data if live fetch fails.

## 2. Scalability & Performance
*   **In-Memory Caching**:
    *   *Gap*: `screeners.py` uses a global `DATA_CACHE` variable. This renders the app hard to scale to multiple workers (gunicorn) as cache isn't shared.
    *   *Fix*: Move cache to `functools.lru_cache` (for thread safety per process) or Redis (for distibuted). For a personal tool, SQLite Caching might be better.
*   **Blocking Operations**:
    *   *Gap*: Some yfinance calls might still be blocking the main thread despite `ThreadPoolExecutor`.
    *   *Fix*: Fully async yfinance wrapper or move heavy compute to a background queue (Celery/RQ) if scaling.

## 3. Data Integrity & Management
*   **Hardcoded Universe**:
    *   *Gap*: `universe.py` and `screener.py` contain hardcoded lists of tickers.
    *   *Fix*: Implement a dynamic "Universe Updater" that fetches S&P 500 / Nasdaq 100 constituents periodically. (Partially implemented in `updater.py` but needs full integration).
*   **Schema Mgmt**:
    *   *Gap*: `portfolio.py` manages tables via `CREATE TABLE IF NOT EXISTS` strings.
    *   *Fix*: Use Alembic for proper DB migrations.

## 4. Frontend Architecture
*   **Monolithic JS**:
    *   *Gap*: `app.js` and `portfolio.js` are becoming huge. Hard to maintain.
    *   *Fix*: Migrate to a component-based framework (Vue/React) or at least use ES6 Modules per feature (`import { renderChart } from './charts.js'`).
*   **State Management**:
    *   *Gap*: State is scattered across DOM elements and global variables.
    *   *Fix*: Centralized Store pattern or improved State object.

## 5. Security (GitHub Readiness)
*   **Secrets Management**:
    *   *Gap*: Potential for hardcoded API keys in old commits.
    *   *Fix*: Ensure all keys (FRED_API_KEY) are loaded via `.env` only. Add `.env` to `.gitignore`.
*   **Input Sanitization**:
    *   *Gap*: `portfolio.py` uses parameterized queries (Good!), but `analyst.py` needed patches for NaN/Infinity.
    *   *Fix*: comprehensive input validation via Pydantic on all endpoints.

## 6. Testing
*   **Coverage**:
    *   *Gap*: Low unit test coverage.
    *   *Fix*: Add `pytest` suite for each Strategy and Repository method.
