# System Architecture & Design Patterns

## 1. High-Level Architecture
The application follows a **Monolithic Client-Server** architecture, designed for easy local deployment.

```
[ Frontend (Browser) ]
       |
       | HTTP / JSON (REST API)
       v
[ Backend (FastAPI) ]
       |
       +--- [ Controller Layer (main.py) ]
       |
       +--- [ Service Layer (analyst.py, screener.py) ]
       |
       +--- [ Data Access Layer (data_client.py, portfolio.py) ]
       |
       v
[ SQLite Database ] / [ External APIs (yfinance, defeatbeta, FRED) ]
```

## 2. Backend Design Patterns

### 2.1. Layered Architecture
Usage: The application strictly separates concerns.
*   **API/Controller**: `main.py` handles input validation (Pydantic), HTTP routing, and response formatting.
*   **Business Logic**: `analyst.py` and `screeners.py` contain the core intelligence. They do not know about the HTTP layer.
*   **Data Access**: `portfolio.py` encapsulates all SQL queries. `data_client.py` abstracts external data sources.

### 2.2. Strategy Pattern
**Usage**: `analyst.py`
The core analysis engine uses the Strategy Pattern to swap evaluation logic based on the user's selection.
*   **Context**: `analyze_stock(symbol, strategy_name)` acts as the Context/Factory.
*   **Strategy Interface**: `BaseStrategy` defines the contract (`run`, `get_metric`, `sanitize`).
*   **Concrete Strategies**: 
    *   `BuffettStrategy`: Focuses on ROE, Moat, Fair Value.
    *   `BurryStrategy`: Focuses on EV/EBITDA, Debt, Short Interest.
    *   `LynchStrategy`: Focuses on PEG Ratio, Growth.

### 2.3. Repository Pattern
**Usage**: `portfolio.py`
The `PortfolioManager` class acts as a Repository.
*   It provides an object-oriented collection-like interface (`add_position`, `get_portfolio`, `delete_portfolio`).
*   It hides the complexity of SQL/Storage from the rest of the app.
*   It handles data mapping (SQL Row -> Python Dict).

### 2.4. Facade Pattern
**Usage**: `data_client.py`
This module acts as a Facade over external data sources (yfinance, defeatbeta). It provides a simplified interface (`get_fundamentals`, `get_price_history`, `get_news`, `get_dcf`) to the application, handling error catching, data normalization, fallback logic, and caching internally.

### 2.5. Toggleable Data Sources
**Usage**: `data_client.py`
The `DEFEATBETA_ENABLED` environment variable (default: `1`) controls whether defeatbeta or yfinance/yahooquery is used for fundamental data, price history, news, and DCF calculations.
*   **Enabled (`1`)**: Uses defeatbeta for fundamentals/history/news/DCF (weekly cached snapshots, no rate limits), yfinance for live price only.
*   **Disabled (`0`)**: Falls back entirely to yfinance/yahooquery for all data.
*   Each function checks the flag at entry and branches accordingly — no duplicate code paths.

## 3. Frontend Architecture

### 3.1. Page Controller / Single Page Application (SPA)
**Usage**: `app.js` and `portfolio.js`
The frontend acts as a lightweight SPA.
*   **Routing**: Tab-based navigation (`switchTab`) manages view visibility without page reloads.
*   **Event Delegation**: Modal handlers and chart toggles are attached to the global scope or delegated.
*   **State Management**: `currentPortfolioId`, `portfolios` array, and `DATA_CACHE` (frontend side implied) manage local state.

### 3.2. Cache-Busting Strategy
The `index.html` response includes `Cache-Control: no-cache` headers. Script tags include `?v=N` version query parameters that must be bumped when JS files change. Current version: `v=17`.

## 4. Data Flow
1.  **User Request**: User clicks "Analyze AAPL".
2.  **Controller**: `main.py` receives GET `/api/analyze/AAPL?strategy=buffett`.
3.  **Service**: `analyze_stock` instantiates `BuffettStrategy`.
4.  **Facade**: Strategy calls `data_client.py` which routes to defeatbeta or yfinance based on `DEFEATBETA_ENABLED`.
5.  **Logic**: Strategy applies rules (e.g., `if roe > 15: score += 1`).
6.  **Response**: JSON verdict returned to Frontend.
7.  **Render**: `app.js` updates the DOM with the "Scorecard" and "Reasons".

## 5. Directory Structure
*   `backend/` - Root application folder.
    *   `main.py` - Entry point.
    *   `static/` - Frontend assets (served directly).
    *   `data/` - SQLite database location.
    *   `docs/` - Documentation.
*   `frontend/` - Client-side code.
    *   `app.js` - Main orchestrator, tab navigation.
    *   `portfolio.js` - Portfolio CRUD and trade modal.
    *   `js/api.js` - API base config.
    *   `js/utils.js` - Shared utilities (formatting, tooltips, TradingView links).
    *   `js/components/` - Feature-specific modules (marketStatus, researchUi, thematic, etc.).
