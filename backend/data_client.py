"""
data_client.py — Unified Data Abstraction Layer
===============================================
Routes calls to the right data source:
  - persistent_db: primary source (SQLite, instant reads, background refresh)
  - defeatbeta: fundamentals, historical data, news, DCF  (weekly snapshots, no rate limits)
  - yfinance:   live price & % change only                (real-time)

All callers import from here — never directly from yfinance or defeatbeta.
"""

import logging
import os
import time
import threading
from datetime import date

import yfinance as yf

from cache_utils import timed_cache, fetch_with_retry
from persistent_cache import (
    init_db, get_ticker_info_cached, save_ticker_info,
    get_price_history_cached, save_price_history,
    needs_refresh, get_bulk_ticker_info,
)

logger = logging.getLogger(__name__)

# Toggle defeatbeta on/off — runtime mutable, set via env var.
# Initialized from env var, but can be changed at runtime without restart.
_DEFEATBETA_ENABLED = os.getenv("DEFEATBETA_ENABLED", "1") != "0"


def is_defeatbeta_enabled() -> bool:
    """Returns whether defeatbeta is currently the primary data source."""
    return _DEFEATBETA_ENABLED


def set_defeatbeta_enabled(enabled: bool) -> dict:
    """
    Toggle defeatbeta on/off at runtime.
    Returns dict with status info and whether a reload is recommended.
    """
    global _DEFEATBETA_ENABLED
    old_value = _DEFEATBETA_ENABLED
    _DEFEATBETA_ENABLED = enabled

    # Clear caches so the new data source isn't contaminated by old cached data
    from cache_utils import clear_cache
    clear_cache()
    from persistent_cache import clear_db
    clear_db()

    return {
        "previous": "defeatbeta" if old_value else "yfinance",
        "current": "defeatbeta" if enabled else "yfinance",
        "reload_recommended": True,
        "message": f"Switched to {'defeatbeta' if enabled else 'yfinance'}. Hard refresh (Ctrl+Shift+R) to apply."
    }


def get_data_source_status() -> dict:
    """Returns current data source configuration."""
    return {
        "defeatbeta_enabled": _DEFEATBETA_ENABLED,
        "current_source": "defeatbeta" if _DEFEATBETA_ENABLED else "yfinance",
        "env_default": os.getenv("DEFEATBETA_ENABLED", "1") != "0",
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
    """Get fundamentals directly from yfinance (defeatbeta bypass)."""
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
            "returnOnEquity": info.get("returnOnEquity", 0.0),
            "returnOnAssets": info.get("returnOnAssets", 0.0),
            "roic": 0.0,
            "wacc": 0.0,
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
        }
    except Exception as e:
        logger.error("yfinance fundamentals failed for %s: %s", symbol, e)
        return {}


# ──────────────────────────────────────────────────────────
# Unified Ticker Info  (respects defeatbeta toggle)
# ──────────────────────────────────────────────────────────

def _background_refresh_ticker(symbol: str):
    """Refresh ticker data in the background (fire-and-forget)."""
    def _worker():
        try:
            fresh = _fetch_ticker_info_raw(symbol)
            if fresh and fresh.get("symbol"):
                save_ticker_info(fresh)
                logger.debug("Background refresh complete for %s", symbol)
        except Exception as e:
            logger.warning("Background refresh failed for %s: %s", symbol, e)
    threading.Thread(target=_worker, daemon=True).start()


def _fetch_ticker_info_raw(symbol: str) -> dict:
    """Fetch ticker info from source (no caching). Used by background refresh."""
    symbol = symbol.upper()
    try:
        base = _get_fundamentals_raw(symbol)
        if not base:
            return {}
        live = _get_price_live_raw(symbol)
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
    if cached:
        logger.info("get_ticker_info(%s): from persistent DB, price=%s", symbol, cached.get("price"))
        # Schedule background refresh if stale
        if needs_refresh(symbol, "price"):
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


def _build_ticker_info_from_cache(data: dict, symbol: str) -> dict:
    """Build full yfinance-compatible dict from cached/partial data."""
    high_52w = data.get("fifty_two_week_high") or 0.0
    low_52w = data.get("fifty_two_week_low") or 0.0

    # Try to get price history from persistent DB for 52-week change
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

    return {
        "symbol": data.get("symbol", symbol),
        "shortName": data.get("name") or data.get("longName", symbol),
        "longName": data.get("name") or data.get("longName", symbol),
        "sector": data.get("sector", "Unknown"),
        "industry": data.get("industry", "Unknown"),
        "longBusinessSummary": data.get("summary") or data.get("longBusinessSummary", "No business summary available."),
        "currentPrice": data.get("price") or data.get("currentPrice", 0.0),
        "regularMarketPrice": data.get("price") or data.get("currentPrice") or data.get("regularMarketPrice", 0.0),
        "regularMarketChangePercent": data.get("regularMarketChangePercent", 0.0),
        "regularMarketVolume": data.get("avg_volume") or data.get("averageVolume", 0),
        "regularMarketPreviousClose": data.get("price") or data.get("currentPrice", 0.0),
        "marketCap": data.get("market_cap", 0.0),
        "trailingPE": data.get("trailing_pe", 0.0),
        "forwardPE": data.get("forward_pe", data.get("trailing_pe", 0.0)),
        "trailingEps": data.get("trailing_eps", 0.0),
        "forwardEps": data.get("forward_eps", data.get("trailing_eps", 0.0)),
        "priceToBook": data.get("price_to_book", 0.0),
        "priceToSalesTrailing12Months": data.get("price_to_sales", 0.0),
        "pegRatio": 0.0,
        "returnOnEquity": data.get("roe", 0.0),
        "returnOnAssets": data.get("roa", 0.0),
        "debtToEquity": data.get("debt_to_equity", 0.0),
        "currentRatio": data.get("current_ratio", 0.0),
        "freeCashflow": data.get("free_cashflow", 0.0),
        "totalDebt": data.get("total_debt", 0.0),
        "totalCash": data.get("total_cash", 0.0),
        "revenueGrowth": data.get("revenue_growth", 0.0),
        "earningsGrowth": data.get("earnings_growth", 0.0),
        "totalRevenue": data.get("revenue", 0.0),
        "netIncomeToCommon": data.get("net_income", 0.0),
        "operatingCashflow": data.get("free_cashflow", 0.0),
        "52WeekChange": change_52w,
        "fiftyTwoWeekHigh": high_52w,
        "fiftyTwoWeekLow": low_52w,
        "averageVolume": data.get("avg_volume") or data.get("averageVolume", 0),
        "volume": data.get("avg_volume") or data.get("averageVolume") or data.get("volume", 0),
        "beta": data.get("beta", 0.0),
        "trailingAnnualDividendYield": data.get("dividend_yield", 0.0),
        "dividendRate": data.get("dividend_rate", 0.0),
        "dividendYield": data.get("dividend_yield", 0.0),
        "payoutRatio": data.get("payout_ratio", 0.0),
        "shortRatio": 0.0,
        "sharesOutstanding": data.get("shares_outstanding", 0.0),
        "enterpriseToEbitda": 0.0,
    }


def _get_fundamentals_raw(symbol: str) -> dict:
    """Fetch fundamentals without any caching."""
    if not is_defeatbeta_enabled():
        return _get_yf_fundamentals(symbol)
    try:
        t = _db_ticker(symbol)
    except Exception:
        return _get_yf_fundamentals(symbol)

    def _fetch(method_name, col):
        try:
            df = getattr(t, method_name)()
            return _safe_scalar(df, col)
        except Exception:
            return 0.0

    ttm_pe = _fetch("ttm_pe", "ttm_pe")
    pb = _fetch("pb_ratio", "pb_ratio")
    ps = _fetch("ps_ratio", "ps_ratio")
    ttm_eps = _fetch("ttm_eps", "tailing_eps")
    ttm_rev = _fetch("ttm_revenue", "ttm_total_revenue")
    ttm_fcf = _fetch("ttm_fcf", "ttm_fcf")
    ttm_ni = _fetch("ttm_net_income_common_stockholders", "ttm_net_income")
    roe_val = _fetch("roe", "roe")
    roa_val = _fetch("roa", "roa")
    rev_growth = _fetch("quarterly_revenue_yoy_growth", "yoy_growth")
    eps_growth = _fetch("quarterly_eps_yoy_growth", "yoy_growth")
    mkt_cap = _fetch("market_capitalization", "market_capitalization")

    total_debt = total_cash = 0.0
    try:
        bs_stmt = t.quarterly_balance_sheet()
        if bs_stmt is not None and hasattr(bs_stmt, "data"):
            bs = bs_stmt.data
            if bs is not None and not bs.empty:
                total_debt = _safe_scalar(bs, "total_debt") if "total_debt" in bs.columns else 0.0
                total_cash = _safe_scalar(bs, "cash_cash_equivalents_and_short_term_investments") if "cash_cash_equivalents_and_short_term_investments" in bs.columns else 0.0
    except Exception:
        pass

    debt_to_equity = (total_debt / ((total_debt / (_fetch("debt_to_equity", "debt_to_equity") / 100)) if _fetch("debt_to_equity", "debt_to_equity") else total_debt + 1)) if total_debt else 0.0

    name = symbol
    sector = "Unknown"
    industry = "Unknown"
    summary = "No business summary available."
    if is_defeatbeta_enabled():
        try:
            meta = t.info() or {}
            name = meta.get("longName") or meta.get("shortName") or symbol
            sector = meta.get("sector") or "Unknown"
            industry = meta.get("industry") or "Unknown"
            summary = meta.get("longBusinessSummary") or "No business summary available."
        except Exception:
            pass

    return {
        "symbol": symbol,
        "longName": name,
        "shortName": name,
        "sector": sector,
        "industry": industry,
        "longBusinessSummary": summary,
        "trailing_pe": ttm_pe,
        "forward_pe": ttm_pe,
        "price_to_book": pb,
        "price_to_sales": ps,
        "trailing_eps": ttm_eps,
        "roe": roe_val,
        "roa": roa_val,
        "debt_to_equity": debt_to_equity,
        "free_cashflow": ttm_fcf,
        "total_debt": total_debt,
        "total_cash": total_cash,
        "revenue_growth": rev_growth,
        "earnings_growth": eps_growth,
        "market_cap": mkt_cap,
        "revenue": ttm_rev,
        "net_income": ttm_ni,
    }


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
# Live Price  (yfinance — real-time, cached in persistent DB)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=60, soft_ttl_seconds=30)
def get_price_live(symbol: str) -> dict:
    """
    Returns real-time price data. Reads from persistent DB first,
    schedules background refresh if stale.
    """
    init_db()
    cached = get_ticker_info_cached(symbol)
    if cached and cached.get("price") and cached.get("price") > 0:
        if needs_refresh(symbol, "price"):
            _background_refresh_ticker(symbol)
        return {
            "price": cached["price"],
            "change_pct": 0.0,
            "volume": cached.get("avg_volume", 0),
            "mkt_cap": cached.get("market_cap", 0.0),
        }

    # No cached price — fetch fresh
    result = _get_price_live_raw(symbol)
    if result.get("price", 0) > 0:
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
    Returns a yfinance-compatible fundamentals dict built from defeatbeta.
    Each metric is fetched in isolation — one failure does not block others.
    """
    if not is_defeatbeta_enabled():
        return _get_yf_fundamentals(symbol)
    try:
        t = _db_ticker(symbol)
    except Exception as e:
        logger.warning("defeatbeta init failed (%s), falling back to yfinance for fundamentals: %s", symbol, e)
        return _get_yf_fundamentals(symbol)

    def _fetch(method_name, col):
        try:
            df = getattr(t, method_name)()
            return _safe_scalar(df, col)
        except Exception as e:
            logger.debug("defeatbeta %s.%s(%s): %s", symbol, method_name, col, e)
            return 0.0

    ttm_pe    = _fetch("ttm_pe",    "ttm_pe")
    pb        = _fetch("pb_ratio",  "pb_ratio")
    ps        = _fetch("ps_ratio",  "ps_ratio")
    ttm_eps   = _fetch("ttm_eps",   "tailing_eps")  # defeatbeta typo: 'tailing_eps'
    ttm_rev   = _fetch("ttm_revenue", "ttm_total_revenue")
    ttm_fcf   = _fetch("ttm_fcf",   "ttm_fcf")
    ttm_ni    = _fetch("ttm_net_income_common_stockholders", "ttm_net_income")
    roe_val   = _fetch("roe",  "roe")
    roa_val   = _fetch("roa",  "roa")
    roic_val  = _fetch("roic", "roic")
    wacc_val  = _fetch("wacc", "wacc")
    rev_growth = _fetch("quarterly_revenue_yoy_growth", "yoy_growth")
    eps_growth = _fetch("quarterly_eps_yoy_growth",     "yoy_growth")
    mkt_cap   = _fetch("market_capitalization", "market_capitalization")

    peg = (ttm_pe / (eps_growth * 100)) if eps_growth and eps_growth != 0 else 0.0

    # Balance sheet (debt, cash, equity)
    total_debt = total_cash = total_equity = 0.0
    try:
        bs_stmt = t.quarterly_balance_sheet()
        if bs_stmt is not None and hasattr(bs_stmt, "data"):
            bs = bs_stmt.data
            if bs is not None and not bs.empty:
                if "total_debt" in bs.columns:
                    total_debt = _safe_scalar(bs, "total_debt")
                if "cash_cash_equivalents_and_short_term_investments" in bs.columns:
                    total_cash = _safe_scalar(bs, "cash_cash_equivalents_and_short_term_investments")
                if "stockholders_equity" in bs.columns:
                    total_equity = _safe_scalar(bs, "stockholders_equity")
    except Exception as e:
        logger.debug("defeatbeta balance_sheet(%s): %s", symbol, e)

    debt_to_equity = (total_debt / total_equity * 100) if total_equity else 0.0
    fcf_yield      = (ttm_fcf / mkt_cap) if mkt_cap else 0.0

    # Company identity — try defeatbeta info() first, fall back to yfinance
    name = symbol
    sector = "Unknown"
    industry = "Unknown"
    summary = "No business summary available."
    if is_defeatbeta_enabled():
        try:
            meta = t.info() or {}
            name     = meta.get("longName") or meta.get("shortName") or symbol
            sector   = meta.get("sector")   or "Unknown"
            industry = meta.get("industry") or "Unknown"
            summary  = meta.get("longBusinessSummary") or "No business summary available."
        except Exception:
            pass
    # Always try yfinance if identity is still default
    if name == symbol:
        try:
            yf_info = yf.Ticker(symbol).info or {}
            name     = yf_info.get("longName") or yf_info.get("shortName") or symbol
            sector   = yf_info.get("sector")   or "Unknown"
            industry = yf_info.get("industry") or "Unknown"
            summary  = yf_info.get("longBusinessSummary") or "No business summary available."
        except Exception:
            pass

    return {
        "symbol":   symbol,
        "longName": name,
        "shortName": name,
        "sector":   sector,
        "industry": industry,
        "longBusinessSummary": summary,
        "data_as_of": "2026-02-20" if is_defeatbeta_enabled() else str(date.today()),  # defeatbeta weekly snapshot

        # Valuation
        "trailingPE":                   ttm_pe,
        "forwardPE":                    ttm_pe,
        "priceToSalesTrailing12Months": ps,
        "priceToBook":                  pb,
        "pegRatio":                     peg,
        "trailingEps":                  ttm_eps,

        # Quality
        "returnOnEquity": roe_val,
        "returnOnAssets": roa_val,
        "roic":           roic_val,
        "wacc":           wacc_val,

        # Balance sheet
        "totalDebt":    total_debt,
        "totalCash":    total_cash,
        "debtToEquity": debt_to_equity,
        "currentRatio": 0.0,
        "freeCashflow": ttm_fcf,
        "fcf_yield":    fcf_yield,

        # Growth
        "revenueGrowth":  rev_growth,
        "earningsGrowth": eps_growth,
        "revenue":        ttm_rev,
        "netIncome":      ttm_ni,

        # Market
        "marketCap": mkt_cap,
    }


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

    # 2. No cached data — fetch from source
    if is_defeatbeta_enabled():
        try:
            t = _db_ticker(symbol)
            df = t.price()
            if df is not None and not df.empty:
                df = df.tail(days).reset_index(drop=True)
                _save_history_to_db(symbol, df)
                return df
        except Exception as e:
            logger.warning("get_price_history defeatbeta(%s) failed: %s", symbol, e)

    # 3. yfinance fallback
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
        logger.error("get_price_history yfinance fallback(%s) failed: %s", symbol, e2)
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
    """Refresh price history in background."""
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
            logger.info("Background refresh complete: price history for %s", symbol)
    except Exception as e:
        logger.warning("Background refresh failed: price history for %s: %s", symbol, e)


# ──────────────────────────────────────────────────────────
# News  (defeatbeta, cached 1h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)  # 1h hard, 30m soft (SWR)
def get_news(symbol: str, n: int = 5) -> list:
    """
    Returns a list of recent news dicts: [{title, date, source, url}]
    """
    if is_defeatbeta_enabled():
        try:
            t = _db_ticker(symbol)
            news_obj = t.news()
            if hasattr(news_obj, "get_news_list"):
                items = news_obj.get_news_list()
            elif hasattr(news_obj, "to_dict"):
                items = news_obj.to_dict("records")
            else:
                pass
            if items:
                result = []
                for item in items[:n]:
                    result.append({
                        "title":  item.get("title") or item.get("headline") or "",
                        "date":   str(item.get("publish_date") or item.get("date") or ""),
                        "source": item.get("source") or item.get("publisher") or "",
                        "url":    item.get("url") or item.get("link") or "#",
                    })
                return result
        except Exception as e:
            logger.warning("get_news(%s) failed: %s", symbol, e)


# ──────────────────────────────────────────────────────────
# DCF Valuation  (defeatbeta, cached 24h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=86400, soft_ttl_seconds=43200)  # 24h hard, 12h soft (SWR)
def get_dcf(symbol: str) -> dict:
    """
    Returns a DCF valuation summary: {fair_value, current_price, upside_pct, wacc, recommendation}
    """
    if is_defeatbeta_enabled():
        try:
            t = _db_ticker(symbol)
            dcf_obj = t.dcf()
            data = {}
            if hasattr(dcf_obj, "get_summary"):
                data = dcf_obj.get_summary() or {}
            elif hasattr(dcf_obj, "to_dict"):
                data = dcf_obj.to_dict() or {}
            fair_value = _safe_float(data.get("fair_value") or data.get("intrinsic_value"))
            wacc_val   = _safe_float(data.get("wacc"))
            recommendation = data.get("recommendation") or data.get("action") or "N/A"
            live = get_price_live(symbol)
            current_price = live.get("price", 0.0)
            upside_pct = ((fair_value - current_price) / current_price * 100) if current_price else 0.0
            return {
                "fair_value":     round(fair_value, 2),
                "current_price":  round(current_price, 2),
                "upside_pct":     round(upside_pct, 1),
                "wacc":           round(wacc_val * 100, 2) if wacc_val < 1 else round(wacc_val, 2),
                "recommendation": recommendation,
            }
        except Exception as e:
            logger.warning("get_dcf(%s) failed: %s", symbol, e)
    return {}


# ──────────────────────────────────────────────────────────
# Bulk DB Warming  (pre-populate persistent cache on startup)
# ──────────────────────────────────────────────────────────

def warm_db_for_symbols(symbols: list):
    """
    Fetch and persist data for a list of symbols in parallel.
    Called on startup to pre-populate the DB so users get instant data.
    Runs in a background thread — does not block server startup.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import random

    def _warm_one(symbol):
        symbol = symbol.upper()
        # Skip if we have fresh data
        if not needs_refresh(symbol, "price"):
            return
        try:
            time.sleep(random.uniform(0.2, 1.0))  # Spread requests
            fresh = _fetch_ticker_info_raw(symbol)
            price = fresh.get("currentPrice") or fresh.get("price", 0)
            if fresh and fresh.get("symbol") and price > 0:
                save_ticker_info(fresh)
                logger.debug("Warmed %s: price=%.2f", symbol, price)
        except Exception as e:
            logger.debug("Warm failed for %s: %s", symbol, e)

    def _worker():
        logger.info("DB warming: starting for %d symbols...", len(symbols))
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_warm_one, s): s for s in symbols}
            done = 0
            for f in as_completed(futures):
                done += 1
                if done % 20 == 0:
                    logger.info("DB warming: %d/%d done (%.0fs)", done, len(symbols), time.time()-t0)
        logger.info("DB warming: complete for %d symbols in %.0fs", len(symbols), time.time()-t0)

    threading.Thread(target=_worker, daemon=True).start()
