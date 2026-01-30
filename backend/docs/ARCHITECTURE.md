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
       +--- [ Data Access Layer (portfolio.py) ]
       |
       v
[ SQLite Database ] / [ External APIs (yfinance, FRED) ]
```

## 2. Backend Design Patterns

### 2.1. Layered Architecture
Usage: The application strictly separates concerns.
*   **API/Controller**: `main.py` handles input validation (Pydantic), HTTP routing, and response formatting.
*   **Business Logic**: `analyst.py` and `screeners.py` contain the core intelligence. They do not know about the HTTP layer.
*   **Data Access**: `portfolio.py` encapsulates all SQL queries.

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
**Usage**: `market_data.py`
This module acts as a Facade over the complex and potentially unstable external data sources (yfinance, FRED). It provides a simplified interface (`get_batch_quotes`, `get_buffett_indicator`) to the application, handling error catching, data normalization, and fallback logic internally.

## 3. Frontend Architecture

### 3.1. Page Controller / Single Page Application (SPA)
**Usage**: `app.js` and `portfolio.js`
The frontend acts as a lightweight SPA.
*   **Routing**: Tab-based navigation (`switchTab`) manages view visibility without page reloads.
*   **Event Delegation**: Modal handlers and chart toggles are attached to the global scope or delegated.
*   **State Management**: `currentPortfolioId`, `portfolios` array, and `DATA_CACHE` (frontend side implied) manage local state.

## 4. Data Flow
1.  **User Request**: User clicks "Analyze AAPL".
2.  **Controller**: `main.py` receives GET `/api/analyze/AAPL?strategy=buffett`.
3.  **Service**: `analyze_stock` instantiates `BuffettStrategy`.
4.  **Facade**: Strategy calls `yfinance` to get raw data.
5.  **Logic**: Strategy applies rules (e.g., `if roe > 15: score += 1`).
6.  **Response**: JSON verdict returned to Frontend.
7.  **Render**: `app.js` updates the DOM with the "Scorecard" and "Reasons".

## 5. Directory Structure
*   `backend/` - Root application folder.
    *   `main.py` - Entry point.
    *   `static/` - Frontend assets (served directly).
    *   `data/` - SQLite database location.
    *   `docs/` - Documentation.
