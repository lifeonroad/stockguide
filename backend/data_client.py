"""
data_client.py — Unified Data Abstraction Layer
================================================
DB-first architecture with rate limiting. Routes calls to:
  - persistent_db: primary source (SQLite, instant reads, background refresh)
  - rate_limiter: enforces conservative limits (30min floor, 48/day)
  - yfinance: data source (with yahooquery fallback)

All callers import from here — never directly from yfinance or defeatbeta.

Architecture:
  Business Logic → data_client (public) → RateLimiter + PersistentCache (DB)
                                ↓
                          yfinance/yahooquery (private network calls)

Rate Limiting:
  - MIN_REFRESH_INTERVAL: 1800s (30 min) between same ticker fetches
  - DAILY_FETCH_LIMIT: 48 fetches per ticker per day
  - Returns stale data with warning when rate limited
"""

import logging
import os
import time
import threading
from datetime import date
from typing import Dict, List, Optional, Tuple, Any

import yfinance as yf

from cache_utils import timed_cache, fetch_with_retry
from persistent_cache import (
    init_db, get_ticker_info_cached, save_ticker_info,
    get_price_history_cached, save_price_history,
    needs_refresh, get_bulk_ticker_info,
    PRICE_TTL, FUNDAMENTALS_TTL,
)

# Import new orchestrator components
from rate_limiter import get_rate_limiter, RateLimiter
from network_client import get_network_client
from intelligent_ttl import get_adjusted_ttl, get_cached_ttl, calculate_refresh_priority, set_next_earnings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter Singleton
# ─────────────────────────────────────────────────────────────────────────────

_rate_limiter: Optional[RateLimiter] = None


def _get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = get_rate_limiter()
    return _rate_limiter


# ─────────────────────────────────────────────────────────────────────────────
# Network Client (Private - internal use only)
# ─────────────────────────────────────────────────────────────────────────────

_network_client = None


def _get_network_client():
    """Get the private network client."""
    global _network_client
    if _network_client is None:
        _network_client = get_network_client()
    return _network_client

# ─────────────────────────────────────────────────────────────────────────────
# Data Source Configuration (defeatbeta disabled - using yfinance only)
# ─────────────────────────────────────────────────────────────────────────────

# defeatbeta is disabled - we use yfinance only with DB-first architecture
# This toggle is kept for backward compatibility but has no effect
_DEFEATBETA_ENABLED = False


def is_defeatbeta_enabled() -> bool:
    """Returns whether defeatbeta is enabled (always False - using yfinance)."""
    return False


def set_defeatbeta_enabled(enabled: bool) -> dict:
    """
    Toggle defeatbeta on/off at runtime.
    Note: defeatbeta is disabled - this is a no-op.
    """
    return {
        "previous": "defeatbeta" if _DEFEATBETA_ENABLED else "yfinance",
        "current": "defeatbeta" if enabled else "yfinance",
        "reload_recommended": False,
        "message": "defeatbeta is disabled. Using yfinance with DB-first architecture."
    }


def get_data_source_status() -> dict:
    """Returns current data source configuration."""
    return {
        "defeatbeta_enabled": False,
        "current_source": "yfinance (DB-first)",
        "rate_limiting": "enabled (30min floor, 48/day limit)",
    }

# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _db_ticker(symbol: str):
    """Return a defeatbeta Ticker (lazy — no network call until a method is invoked)."""
    from defeatbeta_api.data.ticker import Ticker
    return Ticker(symbol)


def _safe_scalar(df, col: str, default=0.0):
    """Pull the latest non-null scalar from a defeatbeta DataFrame column."""
    try:
        if df is None or df.empty:
            return default
        series = df[col].dropna()
        return float(series.iloc[-1]) if not series.empty else default
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default

def _get_yq_info(symbol: str) -> dict:
    from yahooquery import Ticker
    tq = Ticker(symbol)
    info = {}
    for d in [tq.price, tq.financial_data, tq.key_stats, tq.summary_detail, tq.asset_profile]:
        if isinstance(d, dict) and isinstance(d.get(symbol), dict):
            info.update(d[symbol])
    return info


def _get_yf_fundamentals(symbol: str) -> dict:
    """Get fundamentals from yfinance. DB handles caching/persistence."""
    try:
        info = _get_yq_info(symbol)
        mkt_cap = info.get("marketCap", 0.0)
        ttm_fcf = info.get("freeCashflow", 0.0)
        return {
            "symbol":   symbol,
            "longName": info.get("longName") or info.get("shortName") or symbol,
            "shortName": info.get("shortName") or symbol,
            "sector":   info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "longBusinessSummary": info.get("longBusinessSummary", "No business summary available."),
            "data_as_of": str(date.today()),
            "trailingPE": info.get("trailingPE", 0.0),
            "forwardPE": info.get("forwardPE", 0.0),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months", 0.0),
            "priceToBook": info.get("priceToBook", 0.0),
            "pegRatio": info.get("pegRatio", 0.0),
            "trailingEps": info.get("trailingEps", 0.0),
            "forwardEps": info.get("forwardEps", 0.0),
            "returnOnEquity": info.get("returnOnEquity", 0.0),
            "returnOnAssets": info.get("returnOnAssets", 0.0),
            "roic": info.get("roic", 0.0),
            "wacc": info.get("wacc", 0.0),
            "totalDebt": info.get("totalDebt", 0.0),
            "totalCash": info.get("totalCash", 0.0),
            "debtToEquity": info.get("debtToEquity", 0.0),
            "currentRatio": info.get("currentRatio", 0.0),
            "freeCashflow": ttm_fcf,
            "fcf_yield": (ttm_fcf / mkt_cap) if mkt_cap else 0.0,
            "revenueGrowth": info.get("revenueGrowth", 0.0),
            "earningsGrowth": info.get("earningsGrowth", 0.0),
            "revenue": info.get("totalRevenue", 0.0),
            "netIncome": info.get("netIncomeToCommon", 0.0),
            "marketCap": mkt_cap,
            "profitMargin": info.get("profitMargin", 0.0),
            "enterpriseToEbitda": info.get("enterpriseToEbitda", 0.0),
            "bookValue": info.get("bookValue", 0.0),
            "shortRatio": info.get("shortRatio", 0.0),
            "operatingCashflow": info.get("operatingCashflow", 0.0),
            "dividendYield": info.get("dividendYield", 0.0),
            "dividendRate": info.get("dividendRate", 0.0),
            "payoutRatio": info.get("payoutRatio", 0.0),
            "beta": info.get("beta", 0.0),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh", 0.0),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow", 0.0),
            "averageVolume": info.get("averageVolume", 0),
            "sharesOutstanding": info.get("sharesOutstanding", 0.0),
        }
    except Exception as e:
        logger.error("yfinance fundamentals failed for %s: %s", symbol, e)
        return {}


# ──────────────────────────────────────────────────────────
# Unified Ticker Info  (DB-first with rate limiting)
# ──────────────────────────────────────────────────────────

def _background_refresh_ticker(symbol: str):
    """Refresh ticker data in the background (fire-and-forget) with intelligent TTL."""
    def _worker():
        limiter = _get_rate_limiter()
        
        # Get cached info for beta/sector if available
        cached = get_ticker_info_cached(symbol)
        beta = cached.get("beta") if cached else None
        sector = cached.get("sector") if cached else None
        
        # Calculate priority based on intelligent TTL
        priority = calculate_refresh_priority(symbol, "fundamentals", beta, sector)
        
        # Check rate limiter before fetch
        can_fetch, reason = limiter.can_fetch(symbol, "fundamentals")
        
        if not can_fetch:
            logger.debug("Rate limited for %s/fundamentals: %s", symbol, reason)
            # Delay based on priority (higher priority = shorter delay)
            delay = 300 if priority == 1 else (600 if priority == 2 else 900)
            _schedule_delayed_refresh(symbol, delay=delay)
            return
        
        try:
            fresh = _fetch_ticker_info_raw(symbol)
            if fresh and fresh.get("symbol"):
                save_ticker_info(fresh)
                
                # Extract and cache earnings date if available
                if fresh.get("earningsTimestamp"):
                    set_next_earnings(symbol, fresh["earningsTimestamp"])
                
                logger.debug("Background refresh complete for %s (priority=%d)", symbol, priority)
        except Exception as e:
            logger.warning("Background refresh failed for %s: %s", symbol, e)
    threading.Thread(target=_worker, daemon=True).start()


def _schedule_delayed_refresh(symbol: str, delay: int = 600):
    """Schedule a delayed refresh."""
    def _delayed():
        time.sleep(delay)
        _background_refresh_ticker(symbol)
    threading.Thread(target=_delayed, daemon=True).start()


def _fetch_ticker_info_raw(symbol: str) -> dict:
    """Fetch ticker info from source (no caching). Used by background refresh."""
    symbol = symbol.upper()
    limiter = _get_rate_limiter()
    
    # Check rate limiting before fetch
    can_fetch, reason = limiter.can_fetch(symbol, "fundamentals")
    if not can_fetch:
        logger.debug("Rate limited: %s/fundamentals - %s", symbol, reason)
        return {}
    
    try:
        base = _get_fundamentals_raw(symbol)
        if not base:
            return {}
        live = _get_price_live_raw(symbol)
        
        # Record successful fetch
        limiter.record_fetch(symbol, "fundamentals")
        
        return {
            **base,
            "currentPrice": live.get("price", 0.0),
            "regularMarketPrice": live.get("price", 0.0),
            "regularMarketChangePercent": live.get("change_pct", 0.0),
            "averageVolume": live.get("volume", 0),
        }
    except Exception as e:
        logger.warning("Fetch ticker info raw(%s) failed: %s", symbol, e)
        return {}


@timed_cache(ttl_seconds=60, soft_ttl_seconds=30)   # Short in-memory cache; persistent DB is primary
def get_ticker_info(symbol: str) -> dict:
    """
    Returns a yfinance-compatible info dict. Primary source is persistent SQLite DB.
    If data is stale, schedules background refresh and returns cached data immediately.
    If no cached data exists, blocks on fetch.
    """
    symbol = symbol.upper()
    init_db()

    # 1. Try persistent DB first (instant)
    cached = get_ticker_info_cached(symbol)
    logger.info("get_ticker_info(%s): DB lookup result=%s, price=%s", symbol, "found" if cached else "miss", cached.get("price") if cached else "N/A")
    if cached:
        logger.info("get_ticker_info(%s): from persistent DB, price=%s", symbol, cached.get("price"))
        # Schedule background refresh if stale (using intelligent TTL)
        from intelligent_ttl import get_cached_ttl
        from persistent_cache import needs_refresh_intelligent
        needs, reason = needs_refresh_intelligent(symbol, "fundamentals")
        if needs:
            logger.debug("get_ticker_info(%s): data is stale (%s)", symbol, reason)
            _background_refresh_ticker(symbol)
        # Build full dict from cached DB data
        return _build_ticker_info_from_cache(cached, symbol)

    # 2. No cached data — must fetch (blocks, but only once ever)
    logger.info("No cached data for %s — fetching fresh (this will persist)", symbol)
    fresh = _fetch_ticker_info_raw(symbol)
    logger.info("get_ticker_info(%s): fresh fetch, currentPrice=%s", symbol, fresh.get("currentPrice"))
    if fresh and fresh.get("symbol") and fresh.get("currentPrice", 0) > 0:
        save_ticker_info(fresh)
    elif fresh and fresh.get("symbol"):
        logger.warning("get_ticker_info(%s): skipping DB save — price is 0.0", symbol)
    return _build_ticker_info_from_cache(fresh or {}, symbol)


def _val(data, key, default=None):
    """Return value only if it's valid (non-zero, non-None)."""
    v = data.get(key)
    if v is None or v == 0 or v == "":
        return default
    return v

def _val_allow_zero(data, key, default=None):
    """Return value, allowing 0 as valid."""
    return data.get(key, default)


def _build_ticker_info_from_cache(data: dict, symbol: str) -> dict:
    """Build full yfinance-compatible dict from cached/partial data."""
    high_52w = _val_allow_zero(data, "fifty_two_week_high") or 0.0
    low_52w = _val_allow_zero(data, "fifty_two_week_low") or 0.0

    change_52w = 0.0
    hist = get_price_history_cached(symbol, days=252)
    if hist and len(hist) > 2:
        try:
            import pandas as pd
            closes = [float(r["close"]) for r in hist if r.get("close")]
            if len(closes) > 2:
                change_52w = (closes[-1] - closes[0]) / closes[0]
        except Exception:
            pass

    result = {
        "symbol": _val_allow_zero(data, "symbol", symbol),
        "shortName": _val(data, "name") or _val(data, "longName", symbol),
        "longName": _val(data, "name") or _val(data, "longName", symbol),
        "sector": _val(data, "sector", "Unknown"),
        "industry": _val(data, "industry", "Unknown"),
        "longBusinessSummary": _val(data, "summary") or _val(data, "longBusinessSummary") or "No business summary available.",
        "currentPrice": _val_allow_zero(data, "price", 0.0),
        "marketCap": _val_allow_zero(data, "market_cap", 0.0),
        "averageVolume": _val_allow_zero(data, "avg_volume") or _val_allow_zero(data, "averageVolume", 0),
        "52WeekChange": change_52w,
        "fiftyTwoWeekHigh": high_52w,
        "fiftyTwoWeekLow": low_52w,
        "beta": _val_allow_zero(data, "beta", 0.0),
        "sharesOutstanding": _val_allow_zero(data, "shares_outstanding", 0.0),
    }
    
    # Valuation metrics - only include if non-zero
    trailing_pe = _val(data, "trailing_pe")
    if trailing_pe:
        result["trailingPE"] = trailing_pe
        result["forwardPE"] = _val(data, "forward_pe") or trailing_pe
        result["trailingEps"] = _val_allow_zero(data, "trailing_eps", 0.0)
        result["forwardEps"] = _val(data, "forward_eps") or _val_allow_zero(data, "trailing_eps", 0.0)
    
    for key in ["priceToBook", "priceToSalesTrailing12Months", "pegRatio"]:
        db_key = key.replace("priceToBook", "price_to_book").replace("priceToSalesTrailing12Months", "price_to_sales")
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    # Quality metrics - only include if non-zero
    for key in ["returnOnEquity", "returnOnAssets"]:
        db_key = "roe" if key == "returnOnEquity" else "roa"
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    # Financial metrics - only include if non-zero
    for key in ["debtToEquity", "currentRatio"]:
        db_key = "debt_to_equity" if key == "debtToEquity" else "current_ratio"
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    for key in ["freeCashflow", "totalDebt", "totalCash"]:
        db_key = key.replace("freeCashflow", "free_cashflow").replace("totalDebt", "total_debt").replace("totalCash", "total_cash")
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    # Growth metrics - only include if non-zero
    for key in ["revenueGrowth", "earningsGrowth"]:
        db_key = "revenue_growth" if key == "revenueGrowth" else "earnings_growth"
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    # Financial totals - only include if non-zero
    for key in ["totalRevenue", "netIncomeToCommon", "operatingCashflow"]:
        db_key = key.replace("totalRevenue", "revenue").replace("netIncomeToCommon", "net_income").replace("operatingCashflow", "operating_cashflow")
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    # Dividend metrics - allow 0 as valid (no dividend)
    for key in ["trailingAnnualDividendYield", "dividendRate", "dividendYield", "payoutRatio"]:
        db_key = "dividend_yield" if "Yield" in key else key.replace("dividendRate", "dividend_rate").replace("payoutRatio", "payout_ratio")
        v = _val_allow_zero(data, db_key)
        if v is not None:
            result[key] = v
    
    # Other metrics
    for key in ["shortRatio", "enterpriseToEbitda", "profitMargin", "bookValue"]:
        db_key = key.replace("shortRatio", "short_ratio").replace("enterpriseToEbitda", "ev_ebitda").replace("profitMargin", "profit_margin").replace("bookValue", "book_value")
        v = _val(data, db_key)
        if v is not None:
            result[key] = v
    
    return result


def _get_fundamentals_raw(symbol: str) -> dict:
    """Fetch fundamentals using yfinance only. DB handles caching/persistence."""
    return _get_yf_fundamentals(symbol)


def _get_price_live_raw(symbol: str) -> dict:
    """Fetch live price without any caching. Retries on transient failures."""
    for attempt in range(1, 4):
        try:
            info = _get_yq_info(symbol)
            price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
            if price > 0:
                return {
                    "price": price,
                    "change_pct": _safe_float(info.get("regularMarketChangePercent")),
                    "volume": _safe_float(info.get("regularMarketVolume")),
                }
            if attempt < 3:
                logger.debug("_get_price_live_raw(%s): attempt %d returned price=0, retrying...", symbol, attempt)
                time.sleep(1.0 * attempt)
        except Exception as e:
            if attempt < 3:
                logger.debug("_get_price_live_raw(%s): attempt %d failed: %s, retrying...", symbol, attempt, e)
                time.sleep(1.0 * attempt)
            else:
                logger.warning("_get_price_live_raw(%s) failed after 3 attempts: %s", symbol, e)
    return {"price": 0.0, "change_pct": 0.0, "volume": 0.0}


# ──────────────────────────────────────────────────────────
# Live Price  (yfinance — real-time, cached in persistent DB, rate-limited)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=60, soft_ttl_seconds=30)
def get_price_live(symbol: str) -> dict:
    """
    Returns real-time price data. Reads from persistent DB first,
    schedules background refresh if stale (with rate limiting).
    """
    init_db()
    limiter = _get_rate_limiter()
    
    # Check rate limit before any network call
    can_fetch_price, reason = limiter.can_fetch(symbol, "price")
    
    cached = get_ticker_info_cached(symbol)
    if cached and cached.get("price") and cached.get("price") > 0:
        if needs_refresh(symbol, "price"):
            if can_fetch_price:
                _background_refresh_ticker(symbol)
            else:
                logger.debug("Rate limited: %s/price - %s", symbol, reason)
        return {
            "price": cached["price"],
            "change_pct": 0.0,
            "volume": cached.get("avg_volume", 0),
            "mkt_cap": cached.get("market_cap", 0.0),
            "stale": can_fetch_price is False,  # Flag if we're returning stale due to rate limit
        }

    # No cached price — check if we can fetch
    if not can_fetch_price:
        logger.info("Rate limited for %s/price, returning partial data", symbol)
        return {
            "price": cached.get("price", 0) if cached else 0,
            "change_pct": 0.0,
            "volume": cached.get("avg_volume", 0) if cached else 0,
            "stale": True,
            "warning": f"Rate limited. {reason}",
        }
    
    result = _get_price_live_raw(symbol)
    if result.get("price", 0) > 0:
        limiter.record_fetch(symbol, "price")
        # Update price in DB without re-fetching fundamentals
        init_db()
        conn = None
        try:
            from persistent_cache import _get_conn
            conn = _get_conn()
            conn.execute("""
                INSERT INTO ticker_info (symbol, price, price_fetched_at, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    price=excluded.price, price_fetched_at=excluded.price_fetched_at
            """, (symbol.upper(), result["price"], time.time(), time.time()))
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()
    return result


# ──────────────────────────────────────────────────────────
# Fundamentals  (defeatbeta — weekly snapshot, cached 24h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=86400, soft_ttl_seconds=43200)   # 24h hard, 12h soft (SWR)
def get_fundamentals(symbol: str) -> dict:
    """
    Returns fundamentals dict from yfinance. Cached for 5 minutes.
    DB handles persistent caching; this function handles short-term in-memory cache.
    """
    return _get_yf_fundamentals(symbol)


# ──────────────────────────────────────────────────────────
# Price History  (persistent DB → defeatbeta → yfinance)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)  # 1h hard, 30m soft (SWR)
def get_price_history(symbol: str, days: int = 90):
    """
    Returns a pandas DataFrame with columns: [report_date, open, close, high, low, volume]
    Sliced to the last `days` trading days.
    Primary source: persistent SQLite DB. Falls back to defeatbeta/yfinance.
    """
    import pandas as pd

    symbol = symbol.upper()

    # 1. Try persistent DB first (instant)
    cached_rows = get_price_history_cached(symbol, days)
    if cached_rows and len(cached_rows) > 1:
        df = pd.DataFrame(cached_rows).rename(columns={"date": "report_date"})
        # Schedule background refresh if stale
        init_db()
        conn = None
        try:
            from persistent_cache import _get_conn
            conn = _get_conn()
            row = conn.execute(
                "SELECT MAX(date) FROM price_history WHERE symbol = ?", (symbol,)
            ).fetchone()
            if row and row[0]:
                from datetime import datetime
                last_date = datetime.fromisoformat(row[0])
                age = (datetime.now() - last_date).total_seconds()
                if age > 21600:  # 6h stale
                    threading.Thread(
                        target=_background_refresh_history, args=(symbol, days), daemon=True
                    ).start()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()
        return df

    # 2. No cached data — fetch from yfinance and persist to DB
    try:
        hist = yf.Ticker(symbol).history(period=f"{days}d")
        if hist.empty:
            return None
        hist = hist.reset_index().rename(columns={
            "Date": "report_date",
            "Open": "open", "Close": "close",
            "High": "high", "Low": "low", "Volume": "volume",
        })
        df = hist[["report_date", "open", "close", "high", "low", "volume"]]
        _save_history_to_db(symbol, df)
        return df
    except Exception as e2:
        logger.error("get_price_history yfinance(%s) failed: %s", symbol, e2)
        return None


def _save_history_to_db(symbol: str, df):
    """Save price history DataFrame to persistent DB."""
    try:
        import pandas as pd
        rows = []
        for _, row in df.iterrows():
            date_val = row.get("report_date", "")
            if hasattr(date_val, "strftime"):
                date_val = date_val.strftime("%Y-%m-%d")
            rows.append({
                "date": date_val,
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
            })
        if rows:
            save_price_history(symbol, rows)
    except Exception as e:
        logger.debug("Failed to save history to DB for %s: %s", symbol, e)


def _background_refresh_history(symbol: str, days: int = 252):
    """Refresh price history in background with rate limiting."""
    limiter = _get_rate_limiter()
    can_fetch, reason = limiter.can_fetch(symbol, "history")
    
    if not can_fetch:
        logger.debug("Rate limited for %s/history: %s", symbol, reason)
        _schedule_delayed_refresh_history(symbol, days, delay=600)
        return
    
    try:
        import pandas as pd
        logger.info("Background refresh: price history for %s", symbol)
        hist = yf.Ticker(symbol).history(period=f"{days}d")
        if not hist.empty:
            hist = hist.reset_index().rename(columns={
                "Date": "report_date",
                "Open": "open", "Close": "close",
                "High": "high", "Low": "low", "Volume": "volume",
            })
            df = hist[["report_date", "open", "close", "high", "low", "volume"]]
            _save_history_to_db(symbol, df)
            limiter.record_fetch(symbol, "history")
            logger.info("Background refresh complete: price history for %s", symbol)
    except Exception as e:
        logger.warning("Background refresh failed: price history for %s: %s", symbol, e)


def _schedule_delayed_refresh_history(symbol: str, days: int, delay: int = 600):
    """Schedule a delayed history refresh."""
    def _delayed():
        time.sleep(delay)
        _background_refresh_history(symbol, days)
    threading.Thread(target=_delayed, daemon=True).start()


# ──────────────────────────────────────────────────────────
# News  (defeatbeta, cached 1h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)  # 1h hard, 30m soft (SWR)
def get_news(symbol: str, n: int = 5) -> list:
    """
    Returns a list of recent news dicts: [{title, date, source, url}]
    """
    try:
        news = yf.Ticker(symbol).news
        if not news:
            return []
        result = []
        for item in news[:n]:
            if isinstance(item, dict):
                result.append({
                    "title": item.get("title") or "",
                    "date": str(item.get("pubDate") or item.get("publishedAt") or ""),
                    "source": item.get("source") or "",
                    "url": item.get("link") or item.get("canonicalUrl") or "#",
                })
        return result
    except Exception as e:
        logger.debug("get_news(%s) failed: %s", symbol, e)
        return []


# ──────────────────────────────────────────────────────────
# DCF Valuation  (defeatbeta, cached 24h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=86400, soft_ttl_seconds=43200)  # 24h hard, 12h soft (SWR)
def get_dcf(symbol: str) -> dict:
    """
    Returns a DCF valuation summary: {fair_value, current_price, upside_pct, wacc, recommendation}
    Note: yfinance doesn't provide DCF data. Returns empty dict for now.
    TODO: Implement DCF calculation or find alternative data source.
    """
    return {}


# ──────────────────────────────────────────────────────────
# Bulk DB Warming  (pre-populate persistent cache on startup)
# ──────────────────────────────────────────────────────────

def warm_db_for_symbols(symbols: list):
    """
    Fetch and persist data for a list of symbols in parallel.
    Called on startup to pre-populate the DB so users get instant data.
    Runs in a background thread — does not block server startup.
    Rate-limited: max 5 concurrent workers, spread requests.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import random

    def _warm_one(symbol):
        symbol = symbol.upper()
        # Skip if we have fresh data
        if not needs_refresh(symbol, "price"):
            return "skipped"
        
        limiter = _get_rate_limiter()
        can_fetch, reason = limiter.can_fetch(symbol, "fundamentals")
        if not can_fetch:
            logger.debug("Warm rate limited for %s: %s", symbol, reason)
            return "rate_limited"
        
        try:
            time.sleep(random.uniform(1.5, 3.0))  # Spread requests to avoid rate limits
            fresh = _fetch_ticker_info_raw(symbol)
            price = fresh.get("currentPrice") or fresh.get("price", 0)
            if fresh and fresh.get("symbol") and price > 0:
                save_ticker_info(fresh)
                limiter.record_fetch(symbol, "fundamentals")
                logger.debug("Warmed %s: price=%.2f", symbol, price)
                return "success"
        except Exception as e:
            logger.debug("Warm failed for %s: %s", symbol, e)
        return "failed"

    def _worker():
        logger.info("DB warming: starting for %d symbols (rate-limited)...", len(symbols))
        t0 = time.time()
        done = {"success": 0, "skipped": 0, "rate_limited": 0, "failed": 0}
        
        # Limit concurrent workers to reduce load
        with ThreadPoolExecutor(max_workers=1) as executor:  # Single-threaded to avoid rate limits
            futures = {executor.submit(_warm_one, s): s for s in symbols}
            for future in as_completed(futures):
                result = future.result()
                done[result] = done.get(result, 0) + 1
        
        logger.info("DB warming: %d symbols in %.0fs (success=%d, skipped=%d, rate_limited=%d, failed=%d)",
                    len(symbols), time.time()-t0, done["success"], done["skipped"], 
                    done.get("rate_limited", 0), done["failed"])

    threading.Thread(target=_worker, daemon=True).start()
