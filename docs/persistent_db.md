# StockGuide Persistent Database

SQLite database for instant data reads, background refresh, and reduced API calls.

**Location:** `backend/data/stockguide.db`

## Tables

### `ticker_info` (300+ rows)
Stores fundamental data and metrics for each stock.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT PK | Stock ticker (AAPL, MSFT...) |
| `name` | TEXT | Company name |
| `sector` | TEXT | e.g., "Technology" |
| `industry` | TEXT | e.g., "Semiconductors" |
| `summary` | TEXT | Business description |
| `price` | REAL | Current/last price |
| `market_cap` | REAL | Market capitalization |
| `trailing_pe` | REAL | Trailing P/E ratio |
| `forward_pe` | REAL | Forward P/E ratio |
| `price_to_book` | REAL | P/B ratio |
| `price_to_sales` | REAL | P/S ratio |
| `trailing_eps` | REAL | TTM EPS |
| `forward_eps` | REAL | Forward EPS |
| `roe` | REAL | Return on Equity (%) |
| `roa` | REAL | Return on Assets (%) |
| `debt_to_equity` | REAL | Debt/Equity ratio |
| `current_ratio` | REAL | Current ratio |
| `free_cashflow` | REAL | FCF amount |
| `total_debt` | REAL | Total debt |
| `total_cash` | REAL | Total cash |
| `revenue_growth` | REAL | Revenue growth (%) |
| `earnings_growth` | REAL | Earnings growth (%) |
| `revenue` | REAL | Total revenue |
| `net_income` | REAL | Net income |
| `dividend_yield` | REAL | Div yield (%) |
| `dividend_rate` | REAL | Annual div rate |
| `payout_ratio` | REAL | Payout ratio |
| `beta` | REAL | Beta coefficient |
| `fifty_two_week_high` | REAL | 52W high |
| `fifty_two_week_low` | REAL | 52W low |
| `avg_volume` | INTEGER | Avg daily volume |
| `shares_outstanding` | REAL | Shares outstanding |
| `profit_margin` | REAL | Net profit margin (%) |
| `peg_ratio` | REAL | Price/Earnings to Growth |
| `ev_ebitda` | REAL | Enterprise value / EBITDA |
| `book_value` | REAL | Book value per share |
| `short_ratio` | REAL | Short interest ratio |
| `operating_cashflow` | REAL | Operating cash flow |
| `fetched_at` | REAL | Unix timestamp |
| `price_fetched_at` | REAL | Price fetch time |

### `price_history` (87,783 rows)
Daily OHLCV data for charting and analysis.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT PK1 | Ticker |
| `date` | TEXT PK2 | Date (YYYY-MM-DD) |
| `open` | REAL | Opening price |
| `high` | REAL | Daily high |
| `low` | REAL | Daily low |
| `close` | REAL | Closing price |
| `volume` | INTEGER | Trading volume |

### `scan_cache` (0 rows)
Caches full scan results (dip hunter, screeners, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `scan_name` | TEXT PK1 | Scan identifier |
| `params` | TEXT PK2 | Parameters JSON |
| `results` | TEXT | Cached results JSON |
| `fetched_at` | REAL | Unix timestamp |

## Staleness Rules

| Data Type | Fresh TTL | Stale Threshold |
|-----------|----------|-----------------|
| Price | 5 min (market) / 30 min (off-hours) | 5-30 min |
| Fundamentals | 24 hours | 12 hours |
| Price History | 6 hours | 3 hours |
| Scan Results | 1 hour | 30 min |

## Usage

```python
from persistent_cache import get_ticker_info_cached, save_ticker_info

# Read from cache (instant)
data = get_ticker_info_cached('AAPL')
if data:
    print(data['price'], data['trailing_pe'])

# Save new data
save_ticker_info({'symbol': 'AAPL', 'price': 150.0, ...})
```

## Background Refresh

- **SWR (Stale-While-Revalidate):** Returns cached data immediately, refreshes in background
- **On server startup:** DB warming thread pre-loads common tickers
- **Dip Hunter:** Saves fetched data to DB during scan
- **Research:** Saves stock data to DB after fetch

## Deployment

The database file is tracked in git and included in deployments. New deploys will have cached data from the last run, reducing cold-start API calls and rate limiting.
