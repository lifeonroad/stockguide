"""
data_client.py — Unified Data Abstraction Layer
===============================================
Routes calls to the right data source:
  - defeatbeta: fundamentals, historical data, news, DCF  (weekly snapshots, no rate limits)
  - yfinance:   live price & % change only                (real-time)

All callers import from here — never directly from yfinance or defeatbeta.
"""

import logging
import os
from datetime import date

import yfinance as yf

from cache_utils import timed_cache, fetch_with_retry

logger = logging.getLogger(__name__)

# Toggle defeatbeta on/off — runtime mutable, set via API or env var.
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
# Live Price  (yfinance — real-time)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=300, soft_ttl_seconds=180)   # 5m hard, 3m soft (SWR)
def get_price_live(symbol: str) -> dict:
    """
    Returns real-time price data for a symbol.
    Falls back to last-known price if yfinance fails.
    """
    try:
        info = _get_yq_info(symbol)
        return {
            "price":      _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
            "change_pct": _safe_float(info.get("regularMarketChangePercent")),
            "volume":     _safe_float(info.get("regularMarketVolume")),
            "mkt_cap":    _safe_float(info.get("marketCap")),
        }
    except Exception as e:
        logger.warning("get_price_live(%s) failed: %s", symbol, e)
        return {"price": 0.0, "change_pct": 0.0, "volume": 0.0, "mkt_cap": 0.0}


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
# Price History  (defeatbeta — sub-second DuckDB, cached 6h)
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=21600, soft_ttl_seconds=10800)  # 6h hard, 3h soft (SWR)
def get_price_history(symbol: str, days: int = 90):
    """
    Returns a pandas DataFrame with columns: [report_date, open, close, high, low, volume]
    Sliced to the last `days` trading days.
    Falls back to yfinance on error.
    """
    if is_defeatbeta_enabled():
        try:
            t = _db_ticker(symbol)
            df = t.price()
            if df is not None and not df.empty:
                return df.tail(days).reset_index(drop=True)
        except Exception as e:
            logger.warning("get_price_history defeatbeta(%s) failed: %s — falling back to yfinance", symbol, e)

    # yfinance fallback
    try:
        import pandas as pd
        hist = yf.Ticker(symbol).history(period=f"{days}d")
        hist = hist.reset_index().rename(columns={
            "Date": "report_date",
            "Open": "open", "Close": "close",
            "High": "high", "Low": "low", "Volume": "volume",
        })
        return hist[["report_date", "open", "close", "high", "low", "volume"]]
    except Exception as e2:
        logger.error("get_price_history yfinance fallback(%s) failed: %s", symbol, e2)
        return None


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
