"""
Persistent SQLite cache for stock data.

Architecture:
- SQLite with WAL mode for concurrent reads
- Three core tables: ticker_info, price_history, scan_cache
- Background refresh on stale records
- API endpoints read from DB instantly, refresh in background

Staleness rules:
- Price: stale after 5 minutes (market hours), 30 minutes (off-hours)
- Fundamentals: stale after 24 hours
- Price history: stale after 6 hours
- Scan results: stale after 1 hour
"""

import sqlite3
import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("PERSISTENT_DB", os.path.join(os.path.dirname(__file__), "data", "stockguide.db"))

# Staleness thresholds (seconds)
PRICE_TTL = 300        # 5 min (market hours)
PRICE_TTL_OFFHOURS = 1800  # 30 min (off-hours)
FUNDAMENTALS_TTL = 86400  # 24 hours
PRICE_HISTORY_TTL = 21600  # 6 hours
SCAN_CACHE_TTL = 3600     # 1 hour

_lock = threading.Lock()
_db_initialized = False


def _is_market_hours() -> bool:
    """Check if US market is open (Mon-Fri, 9:30 AM - 4:00 PM ET)."""
    now = datetime.now(timezone.utc)
    # ET is UTC-5 (standard) or UTC-4 (DST). Rough approximation:
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
    """Initialize database schema. Idempotent."""
    global _db_initialized
    if _db_initialized:
        return

    with _lock:
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
            CREATE INDEX IF NOT EXISTS idx_ticker_info_price ON ticker_info(price_fetched_at);
        """)
        conn.commit()
        conn.close()
        _db_initialized = True
        logger.info("Persistent DB initialized at %s", DB_PATH)


def get_ticker_info_cached(symbol: str) -> Optional[Dict]:
    """Read ticker info from DB. Returns None if not found or very stale."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM ticker_info WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        age = time.time() - (d.get("price_fetched_at") or d.get("fetched_at") or 0)
        # Return stale data up to 2x TTL, beyond that return None to force refresh
        if age > _price_ttl() * 4:
            return None
        return d
    finally:
        conn.close()


def save_ticker_info(data: Dict):
    """Upsert ticker info into DB. Accepts both yfinance-style and snake_case keys."""
    init_db()
    symbol = data.get("symbol", "").upper()
    if not symbol:
        return

    # Normalize keys: prefer yfinance-style, fall back to snake_case
    def _val(*keys):
        for k in keys:
            v = data.get(k)
            if v is not None:
                return v
        return None

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
                shares_outstanding, fetched_at, price_fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            time.time(), time.time()
        ))
        conn.commit()
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
        if not rows:
            return None
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_price_history(symbol: str, rows: List[Dict]):
    """Upsert price history rows into DB."""
    init_db()
    symbol = symbol.upper()
    conn = _get_conn()
    try:
        conn.executemany("""
            INSERT OR REPLACE INTO price_history (symbol, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [(symbol, r.get("date", ""), r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"))
              for r in rows])
        conn.commit()
    finally:
        conn.close()


def get_scan_cached(scan_name: str, params: str = "") -> Optional[Any]:
    """Read cached scan results."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM scan_cache WHERE scan_name = ? AND params = ?",
            (scan_name, params)
        ).fetchone()
        if not row:
            return None
        age = time.time() - row["fetched_at"]
        if age > SCAN_CACHE_TTL * 2:
            return None
        return json.loads(row["results"])
    finally:
        conn.close()


def save_scan(scan_name: str, params: str, results: Any):
    """Cache scan results."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO scan_cache (scan_name, params, results, fetched_at)
            VALUES (?, ?, ?, ?)
        """, (scan_name, params, json.dumps(results), time.time()))
        conn.commit()
    finally:
        conn.close()


def get_bulk_ticker_info(symbols: List[str]) -> Dict[str, Optional[Dict]]:
    """Bulk read ticker info from DB. Returns dict of symbol -> data (or None)."""
    init_db()
    conn = _get_conn()
    try:
        symbols_upper = [s.upper() for s in symbols]
        placeholders = ",".join("?" * len(symbols_upper))
        rows = conn.execute(
            f"SELECT * FROM ticker_info WHERE symbol IN ({placeholders})",
            symbols_upper
        ).fetchall()
        result = {}
        for s in symbols_upper:
            result[s] = None
        for row in rows:
            d = dict(row)
            age = time.time() - (d.get("price_fetched_at") or d["fetched_at"])
            if age <= _price_ttl() * 4:
                result[d["symbol"]] = d
        return result
    finally:
        conn.close()


def needs_refresh(symbol: str, field: str = "price") -> bool:
    """Check if a symbol's data needs background refresh."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT price_fetched_at, fetched_at FROM ticker_info WHERE symbol = ?",
            (symbol.upper(),)
        ).fetchone()
        if not row:
            return True
        if field == "price":
            age = time.time() - (row["price_fetched_at"] or row["fetched_at"])
            return age > _price_ttl()
        else:
            age = time.time() - row["fetched_at"]
            return age > FUNDAMENTALS_TTL
    finally:
        conn.close()


def get_db_stats() -> Dict:
    """Get database statistics."""
    init_db()
    conn = _get_conn()
    try:
        ticker_count = conn.execute("SELECT COUNT(*) FROM ticker_info").fetchone()[0]
        price_count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        scan_count = conn.execute("SELECT COUNT(*) FROM scan_cache").fetchone()[0]
        oldest_price = conn.execute(
            "SELECT MIN(price_fetched_at) FROM ticker_info"
        ).fetchone()[0]
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "ticker_count": ticker_count,
            "price_history_rows": price_count,
            "cached_scans": scan_count,
            "oldest_data_age_hours": round((time.time() - oldest_price) / 3600, 1) if oldest_price else 0,
            "db_size_mb": round(db_size / 1024 / 1024, 1),
            "db_path": DB_PATH,
        }
    finally:
        conn.close()


def clear_db():
    """Clear all data from the database."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM ticker_info")
        conn.execute("DELETE FROM price_history")
        conn.execute("DELETE FROM scan_cache")
        conn.commit()
    finally:
        conn.close()


def close_db():
    """Close any open connections (for cleanup)."""
    global _db_initialized
    _db_initialized = False
