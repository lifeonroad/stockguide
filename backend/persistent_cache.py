"""
Persistent SQLite cache for stock data.

Architecture:
- SQLite with WAL mode for concurrent reads
- Three core tables: ticker_info, price_history, scan_cache
- Background refresh on stale records (rate-limited)
- API endpoints read from DB instantly, refresh in background

Staleness rules (with intelligent TTL):
- Price: stale after 30 minutes (floor), adjusted by beta/earnings/sector
- Fundamentals: stale after 24 hours (adjusted by sector)
- Price history: stale after 12 hours
- Scan results: stale after 2 hours

Rate Limiting:
- MIN_REFRESH_INTERVAL: 1800s (30 min) between same ticker fetches
- DAILY_FETCH_LIMIT: 48 fetches per ticker per day
- Intelligent TTL: beta-based, earnings-aware, sector-adjusted
"""

import sqlite3
import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("PERSISTENT_DB", os.path.join(os.path.dirname(__file__), "data", "stockguide.db"))

# Staleness thresholds (seconds)
# CONSERVATIVE SETTINGS: Prevent rate limiting
# Minimum refresh interval per ticker: 30 minutes (1800s)
# This prevents hitting yfinance rate limits while maintaining data freshness

PRICE_TTL = 1800          # 30 min (market hours) - MINIMUM FLOOR
PRICE_TTL_OFFHOURS = 3600 # 60 min (off-hours) - generous for inactive period
FUNDAMENTALS_TTL = 86400  # 24 hours - quarterly data doesn't change hourly
PRICE_HISTORY_TTL = 43200 # 12 hours - historical data rarely needs refresh
SCAN_CACHE_TTL = 7200     # 2 hours - scan results are expensive to compute

# Rate limiting constants
MIN_REFRESH_INTERVAL = 1800  # Never fetch same ticker more than once per 30 min
DAILY_FETCH_LIMIT = 48      # Max fetches per ticker per day (prevents DOS)
BULK_FETCH_BATCH = 10       # Max tickers per bulk request to spread load

db_write_lock = threading.Lock()
_db_initialized = False


def _is_market_hours() -> bool:
    """Check if US market is open (Mon-Fri, 9:30 AM - 4:00 PM ET)."""
    now = datetime.now(timezone.utc)
    hour_et = (now.hour - 4) % 24  # DST offset approximation
    return now.weekday() < 5 and 13 <= hour_et < 21


def _price_ttl() -> int:
    return PRICE_TTL if _is_market_hours() else PRICE_TTL_OFFHOURS


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-2000")  # 2MB cache
    return conn


def init_db():
    """Initialize DB with schema. Safe to call multiple times."""
    global _db_initialized
    with db_write_lock:
        if _db_initialized:
            return
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ticker_info (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                industry TEXT,
                summary TEXT,
                price REAL,
                market_cap REAL,
                trailing_pe REAL,
                forward_pe REAL,
                price_to_book REAL,
                price_to_sales REAL,
                trailing_eps REAL,
                forward_eps REAL,
                roe REAL,
                roa REAL,
                debt_to_equity REAL,
                current_ratio REAL,
                free_cashflow REAL,
                total_debt REAL,
                total_cash REAL,
                revenue_growth REAL,
                earnings_growth REAL,
                revenue REAL,
                net_income REAL,
                dividend_yield REAL,
                dividend_rate REAL,
                payout_ratio REAL,
                beta REAL,
                fifty_two_week_high REAL,
                fifty_two_week_low REAL,
                avg_volume REAL,
                shares_outstanding REAL,
                profit_margin REAL,
                peg_ratio REAL,
                ev_ebitda REAL,
                book_value REAL,
                short_ratio REAL,
                operating_cashflow REAL,
                gross_margin REAL,
                roic REAL,
                fetched_at REAL,
                price_fetched_at REAL
            );

            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (symbol, date)
            );

            CREATE TABLE IF NOT EXISTS scan_cache (
                scan_name TEXT NOT NULL,
                params TEXT NOT NULL,
                results TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (scan_name, params)
            );
            
            CREATE INDEX IF NOT EXISTS idx_price_history_symbol ON price_history(symbol);
            CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(date);
        """)
        conn.commit()
        conn.close()
        _db_initialized = True


def save_ticker_info(data: Dict):
    """Upsert ticker info into DB. Accepts both yfinance-style and snake_case keys."""
    init_db()
    symbol = data.get("symbol", "").upper()
    if not symbol:
        return

    def _val(*keys):
        for k in keys:
            v = data.get(k)
            if v is not None:
                return v
        return None

    with db_write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
    INSERT INTO ticker_info (symbol, name, sector, industry, summary,
    price, market_cap, trailing_pe, forward_pe, price_to_book,
    price_to_sales, trailing_eps, forward_eps, roe, roa,
    debt_to_equity, current_ratio, free_cashflow, total_debt,
    total_cash, revenue_growth, earnings_growth, revenue,
    net_income, dividend_yield, dividend_rate, payout_ratio,
    beta, fifty_two_week_high, fifty_two_week_low, avg_volume,
    shares_outstanding, profit_margin, peg_ratio, ev_ebitda,
    book_value, short_ratio, operating_cashflow,
    gross_margin, roic, fetched_at, price_fetched_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol) DO UPDATE SET
    name=excluded.name, sector=excluded.sector, industry=excluded.industry,
    summary=excluded.summary, price=excluded.price, market_cap=excluded.market_cap,
    trailing_pe=excluded.trailing_pe, forward_pe=excluded.forward_pe,
    price_to_book=excluded.price_to_book, price_to_sales=excluded.price_to_sales,
    trailing_eps=excluded.trailing_eps, forward_eps=excluded.forward_eps,
    roe=excluded.roe, roa=excluded.roa, debt_to_equity=excluded.debt_to_equity,
    current_ratio=excluded.current_ratio, free_cashflow=excluded.free_cashflow,
    total_debt=excluded.total_debt, total_cash=excluded.total_cash,
    revenue_growth=excluded.revenue_growth, earnings_growth=excluded.earnings_growth,
    revenue=excluded.revenue, net_income=excluded.net_income,
    dividend_yield=excluded.dividend_yield, dividend_rate=excluded.dividend_rate,
    payout_ratio=excluded.payout_ratio, beta=excluded.beta,
    fifty_two_week_high=excluded.fifty_two_week_high,
    fifty_two_week_low=excluded.fifty_two_week_low,
    avg_volume=excluded.avg_volume, shares_outstanding=excluded.shares_outstanding,
    profit_margin=excluded.profit_margin, peg_ratio=excluded.peg_ratio,
    ev_ebitda=excluded.ev_ebitda, book_value=excluded.book_value,
    short_ratio=excluded.short_ratio, operating_cashflow=excluded.operating_cashflow,
    gross_margin=excluded.gross_margin, roic=excluded.roic,
    fetched_at=excluded.fetched_at, price_fetched_at=excluded.price_fetched_at
""", (
                symbol,
                _val("longName", "name"),
                _val("sector"),
                _val("industry"),
                _val("longBusinessSummary", "summary"),
                _val("currentPrice", "price", "regularMarketPrice"),
                _val("marketCap", "market_cap"),
                _val("trailingPE", "trailing_pe"),
                _val("forwardPE", "forward_pe"),
                _val("priceToBook", "price_to_book"),
                _val("priceToSalesTrailing12Months", "price_to_sales"),
                _val("trailingEps", "trailing_eps"),
                _val("forwardEps", "forward_eps"),
                _val("returnOnEquity", "roe"),
                _val("returnOnAssets", "roa"),
                _val("debtToEquity", "debt_to_equity"),
                _val("currentRatio", "current_ratio"),
                _val("freeCashflow", "free_cashflow"),
                _val("totalDebt", "total_debt"),
                _val("totalCash", "total_cash"),
                _val("revenueGrowth", "revenue_growth"),
                _val("earningsGrowth", "earnings_growth"),
                _val("totalRevenue", "revenue"),
                _val("netIncomeToCommon", "net_income"),
                _val("dividendYield", "dividend_yield"),
                _val("dividendRate", "dividend_rate"),
                _val("payoutRatio", "payout_ratio"),
                _val("beta"),
                _val("fiftyTwoWeekHigh", "fifty_two_week_high"),
                _val("fiftyTwoWeekLow", "fifty_two_week_low"),
                _val("averageVolume", "avg_volume"),
                _val("sharesOutstanding", "shares_outstanding"),
                _val("profitMargin", "profit_margin"),
                _val("pegRatio", "peg_ratio"),
                _val("enterpriseToEbitda", "ev_ebitda"),
                _val("bookValue", "book_value"),
                _val("shortRatio", "short_ratio"),
                _val("operatingCashflow", "operating_cashflow"),
                _val("grossMargins", "gross_margin"),
                _val("returnOnInvestedCapital", "roic"),
                time.time(), time.time()
            ))
            conn.commit()
        finally:
            conn.close()


def get_ticker_info_cached(symbol: str) -> Optional[Dict]:
    """Read ticker info from DB. Returns None if not found."""
    init_db()
    symbol = symbol.upper()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM ticker_info WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_price_history_cached(symbol: str, days: int = 252) -> Optional[List[Dict]]:
    """Read price history from DB."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM price_history WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol.upper(), days)
        ).fetchall()
        return [dict(r) for r in rows] if rows else None
    finally:
        conn.close()


def save_price_history(symbol: str, rows: List[Dict]):
    """Upsert price history rows into DB."""
    init_db()
    symbol = symbol.upper()
    with db_write_lock:
        conn = _get_conn()
        try:
            conn.executemany("""
                INSERT OR REPLACE INTO price_history (symbol, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [(symbol, r.get("date", ""), r.get("open"), r.get("high"), 
                   r.get("low"), r.get("close"), r.get("volume")) for r in rows])
            conn.commit()
        finally:
            conn.close()


def get_bulk_ticker_info(symbols: List[str]) -> Dict[str, Dict]:
    """Read multiple tickers from DB in one query."""
    init_db()
    if not symbols:
        return {}
    symbols = [s.upper() for s in symbols]
    placeholders = ",".join(["?"] * len(symbols))
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM ticker_info WHERE symbol IN ({placeholders})",
            symbols
        ).fetchall()
        return {dict(r)["symbol"]: dict(r) for r in rows}
    finally:
        conn.close()


def needs_refresh(symbol: str, data_type: str = "price", effective_ttl: int = None) -> bool:
    """
    Check if cached data needs refresh based on TTL.
    
    Args:
        symbol: Ticker symbol
        data_type: Type of data ('price', 'fundamentals', 'history')
        effective_ttl: Override TTL with intelligent TTL (from intelligent_ttl module)
                       If None, uses default TTL from constants.
    """
    init_db()
    symbol = symbol.upper()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT fetched_at, price_fetched_at FROM ticker_info WHERE symbol = ?",
            (symbol,)
        ).fetchone()
        if not row:
            return True
        
        age = time.time() - (row["price_fetched_at"] or row["fetched_at"] or 0)
        
        # Use effective_ttl if provided (intelligent TTL), otherwise use default
        if effective_ttl is not None:
            return age > effective_ttl
        
        if data_type == "price":
            return age > _price_ttl()
        return age > FUNDAMENTALS_TTL
    finally:
        conn.close()


def needs_refresh_intelligent(symbol: str, data_type: str) -> Tuple[bool, str]:
    """
    Check if data needs refresh using intelligent TTL with detailed reasoning.
    
    Returns:
        (needs_refresh, reason)
    """
    from intelligent_ttl import get_cached_ttl, get_adjusted_ttl
    
    cached = get_ticker_info_cached(symbol)
    if not cached:
        return True, "No cached data"
    
    fetched_at = cached.get("price_fetched_at") or cached.get("fetched_at", 0)
    if fetched_at == 0:
        return True, "No fetch timestamp"
    
    # Get intelligent TTL
    ttl = get_cached_ttl(symbol, data_type)
    age = time.time() - fetched_at
    
    needs = age > ttl
    reason = f"Age: {age:.0f}s, TTL: {ttl}s"
    
    return needs, reason


def get_db_stats() -> Dict:
    """Get database statistics."""
    init_db()
    conn = _get_conn()
    try:
        ticker_count = conn.execute("SELECT COUNT(*) FROM ticker_info").fetchone()[0]
        price_count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        symbols_with_history = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM price_history"
        ).fetchone()[0]
        return {
            "ticker_count": ticker_count,
            "price_history_rows": price_count,
            "symbols_with_history": symbols_with_history,
        }
    finally:
        conn.close()


def clear_db():
    """Clear all cached data. Use with caution."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM ticker_info")
        conn.execute("DELETE FROM price_history")
        conn.execute("DELETE FROM scan_cache")
        conn.commit()
    finally:
        conn.close()
