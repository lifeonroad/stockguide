"""
Dip Hunter Module
Detects market dips and classifies them as good/better/best opportunities

Architecture
------------
1. Dynamic sector expansion: detects "bleeding" sectors via ETF analysis
   (drop > 8%, RSI < 40). For bleeding sectors, scans ALL constituents from
   SECTOR_STOCKS; for normal sectors, uses curated DIP_UNIVERSE subset.
   This catches sector-wide events like SaaS crashes or healthcare selloffs.
2. Batch price download via yf.download() (batches of 50, single HTTP call per batch).
3. Fast bulk fundamentals via yahooquery (parallel batches of 40, ~10s for 120 tickers).
4. @timed_cache with SWR: cached responses are instant; stale data served
   while background refresh runs.

Performance:
- Normal market: ~108 tickers, first run ~15s, cached <1ms
- Sector crash: ~150-250 tickers (expanded), first run ~20-30s, cached <1ms
- Original (pre-optimization): ~293s
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import concurrent.futures
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def _save_hist_to_db(symbol: str, df: pd.DataFrame):
    """Save price history DataFrame to persistent DB."""
    try:
        from persistent_cache import save_price_history
        rows = []
        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            rows.append({
                "date": date_str,
                "open": float(row.get("open", 0)) if row.get("open") is not None else 0,
                "high": float(row.get("high", 0)) if row.get("high") is not None else 0,
                "low": float(row.get("low", 0)) if row.get("low") is not None else 0,
                "close": float(row.get("close", 0)) if row.get("close") is not None else 0,
                "volume": float(row.get("volume", 0)) if row.get("volume") is not None else 0,
            })
        if rows:
            save_price_history(symbol, rows)
    except Exception as e:
        logger.debug("Failed to save price history for %s: %s", symbol, e)

def _save_fundamentals_to_db(symbol: str, data: dict):
    """Save fundamentals to persistent DB."""
    try:
        from persistent_cache import save_ticker_info
        db_data = {
            "symbol": symbol,
            "roe": data.get("roe"),
            "debt_to_equity": data.get("debt_to_equity"),
            "avg_volume": data.get("avg_volume"),
            "shortName": data.get("shortName", symbol),
        }
        # Add any extra fields from bulk fetch
        for key in ["market_cap", "trailing_pe", "forward_pe", "price_to_book",
                     "price_to_sales", "trailing_eps", "forward_eps", "roa",
                     "current_ratio", "free_cashflow", "total_debt", "total_cash",
                     "revenue_growth", "earnings_growth", "revenue", "net_income",
                     "dividend_yield", "dividend_rate", "payout_ratio", "beta",
                     "fifty_two_week_high", "fifty_two_week_low", "shares_outstanding",
                     "profit_margin", "peg_ratio", "ev_ebitda", "book_value",
                     "short_ratio", "operating_cashflow", "price", "name", "sector",
                     "longBusinessSummary"]:
            if key in data:
                db_data[key] = data[key]
        save_ticker_info(db_data)
    except Exception as e:
        logger.debug("Failed to save fundamentals for %s: %s", symbol, e)
from screener import SECTOR_ETFS, SECTOR_STOCKS, get_sector_stocks
from cache_utils import fetch_with_retry, timed_cache
from data_client import get_ticker_info, get_price_history

class DipCache:
    """Simple in-memory cache with TTL"""
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds
        self.last_update = None

    def get(self, key: str):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return data
        return None

    def set(self, key: str, data):
        self.cache[key] = (data, datetime.now())
        self.last_update = datetime.now()

# Global cache instance
_DIP_CACHE = DipCache(ttl_seconds=3600)

# ──────────────────────────────────────────────────────────
# Curated dip-hunt universe (~80 tickers across quality segments)
# Full sector lists are too large for efficient scanning.
# ──────────────────────────────────────────────────────────
DIP_UNIVERSE = {
    # Mega-cap tech (always worth watching)
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "ADBE", "AMD", "CRM", "INTC", "QCOM", "INTU", "AMAT"],
    # Financials
    "Financials": ["JPM", "BAC", "GS", "V", "MA", "BLK", "AXP", "SPGI", "C", "SCHW"],
    # Healthcare
    "Healthcare": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "PFE", "TMO", "DHR", "BMY", "GILD"],
    # Consumer
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "BKNG", "SBUX", "TJX", "CMG"],
    "Consumer Staples": ["PG", "COST", "PEP", "KO", "WMT", "PM", "MO", "CL", "MDLZ"],
    # Energy + Materials
    "Energy": ["XOM", "CVX", "COP", "SLB", "OXY", "HAL"],
    "Materials": ["LIN", "SHW", "FCX", "APD", "NEM", "DOW"],
    # Industrials
    "Industrials": ["CAT", "GE", "HON", "DE", "UNP", "BA", "LMT", "RTX", "UPS"],
    # Defensive
    "Utilities": ["NEE", "DUK", "SO", "AEP", "D"],
    "Real Estate": ["PLD", "AMT", "EQIX", "PSA", "O", "VICI"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS"],
    # High-conviction growth names
    "Hyper-Growth": ["PLTR", "SNOW", "ARM", "MSTR", "SHOP", "DDOG", "NET", "CRWD", "PANW", "COIN"],
    # Dividend quality
    "Dividend Kings": ["KO", "PEP", "PG", "JNJ", "ABBV", "LOW", "CVX", "XOM", "MCD", "CL"],
}

# Major Market ETFs to track
MARKET_ETFS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "DIA": "Dow Jones",
    "IWM": "Russell 2000"
}

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """
    Calculate Relative Strength Index (RSI)
    Returns a value between 0-100
    """
    if len(prices) < period + 1:
        return 50.0  # Neutral if not enough data
    
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return float(rsi.iloc[-1])


def get_drop_from_high(ticker_obj, period: str = '52w') -> Tuple[float, float, float]:
    """
    Calculate % drop from high
    Returns: (drop_pct, current_price, high_price)
    """
    try:
        if period == '52w':
            hist = fetch_with_retry(lambda: ticker_obj.history(period='1y'), max_attempts=3, base_delay=1.5)
        else:  # 20d
            hist = fetch_with_retry(lambda: ticker_obj.history(period='1mo'), max_attempts=3, base_delay=1.5)
        
        if hist.empty:
            return 0.0, 0.0, 0.0
        
        current_price = hist['Close'].iloc[-1]
        high_price = hist['High'].max()
        
        drop_pct = ((current_price - high_price) / high_price) * 100
        
        return round(drop_pct, 2), round(current_price, 2), round(high_price, 2)
    
    except Exception as e:
        print(f"Error calculating drop for ticker: {e}")
        return 0.0, 0.0, 0.0


def classify_dip_quality(drop_pct: float, rsi: float, roe: float = 0, debt_equity: float = 0) -> str:
    """
    Classify dip as GOOD / BETTER / BEST
    
    Logic:
    - BEST: 12%+ drop, RSI < 30, ROE > 15%, Debt/Equity < 150
    - BETTER: 8-12% drop, RSI < 35
    - GOOD: 5-8% drop
    """
    abs_drop = abs(drop_pct)
    
    # BEST dip: Deep drop + oversold + quality fundamentals
    if abs_drop >= 12 and rsi < 30 and roe > 15 and debt_equity < 150:
        return "BEST"
    
    # BETTER dip: Moderate drop + oversold
    if abs_drop >= 8 and abs_drop < 12 and rsi < 35:
        return "BETTER"
    
    # Also BETTER if deep drop with good RSI
    if abs_drop >= 12 and rsi < 35:
        return "BETTER"
    
    # GOOD dip: Small drop
    if abs_drop >= 5 and abs_drop < 8:
        return "GOOD"
    
    # GOOD for moderate drop with ok fundamentals
    if abs_drop >= 8 and abs_drop < 12:
        return "GOOD"
    
    return "NONE"


def scan_etf_dips() -> List[Dict]:
    """Scan major market ETFs and sector ETFs for dips with caching"""
    cached_data = _DIP_CACHE.get("etf_dips")
    if cached_data:
        return cached_data

    results = []
    # SECTOR_ETFS is {Name: Ticker}, MARKET_ETFS is {Ticker: Name}
    # We need to harmonize them to {Ticker: Name}
    harmonized_sectors = {v: k for k, v in SECTOR_ETFS.items()}
    all_etfs = {**MARKET_ETFS, **harmonized_sectors}
    
    def fetch_etf_data(ticker, name):
        # Small random sleep to spread concurrent requests from same IP
        time.sleep(random.uniform(0.1, 0.5))
        try:
            etf = yf.Ticker(ticker)
            hist = fetch_with_retry(lambda t=etf: t.history(period='1y'), max_attempts=3, base_delay=1.5)
            if hist.empty: return None
            
            drop_pct, current_price, high_price = get_drop_from_high(etf, '52w')
            rsi = calculate_rsi(hist['Close'])
            
            low_5d = hist['Low'].tail(5).min()
            recovery_5d = round(((current_price - low_5d) / low_5d) * 100, 2) if low_5d > 0 else 0.0
            
            low_15d = hist['Low'].tail(15).min()
            recovery_15d = round(((current_price - low_15d) / low_15d) * 100, 2) if low_15d > 0 else 0.0
            
            if abs(drop_pct) >= 3:
                try:
                    info = fetch_with_retry(lambda t=etf: t.info, max_attempts=3, base_delay=1.5)
                except Exception:
                    info = {}
                vol = info.get('volume', 0)
                avg_vol = info.get('averageVolume', vol)
                return {
                    "ticker": ticker,
                    "name": name,
                    "current_price": current_price,
                    "high_52w": high_price,
                    "drop_pct": drop_pct,
                    "rsi": round(rsi, 1),
                    "volume": vol,
                    "avg_volume": avg_vol,
                    "volume_ratio": round(vol / avg_vol, 2) if avg_vol > 0 else 1.0,
                    "recovery_5d": recovery_5d,
                    "recovery_15d": recovery_15d,
                    "classification": classify_dip_quality(drop_pct, rsi),
                    "is_market_etf": ticker in MARKET_ETFS
                }
        except Exception: return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(fetch_etf_data, t, n) for t, n in all_etfs.items()]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: results.append(res)

    results.sort(key=lambda x: x['drop_pct'])
    _DIP_CACHE.set("etf_dips", results)
    return results

def _fetch_batch_history(tickers: List[str], days: int = 252) -> Dict[str, pd.DataFrame]:
    """Fetch 1-year price history. DB-first, then yfinance for missing/stale."""
    hist_cache = {}
    if not tickers:
        return hist_cache
    
    # Step 1: Try DB first (instant for 500+ tickers)
    from persistent_cache import get_price_history_cached, needs_refresh
    missing_tickers = []
    
    for sym in tickers:
        rows = get_price_history_cached(sym, days=days)
        if rows and len(rows) >= 200 and not needs_refresh(sym, "history"):
            # Convert DB rows to DataFrame (keep lowercase columns for consistency)
            import pandas as pd
            df = pd.DataFrame(rows)
            df.set_index(pd.to_datetime(df['date']), inplace=True)
            df.sort_index(inplace=True)
            hist_cache[sym] = df
        else:
            missing_tickers.append(sym)
    
    if not missing_tickers:
        return hist_cache  # All found in DB
    
    # Step 2: Fetch missing from yfinance
    batch_size = 50
    for i in range(0, len(missing_tickers), batch_size):
        batch = missing_tickers[i:i + batch_size]
        try:
            data = fetch_with_retry(
                lambda b=batch: yf.download(b, period="1y", progress=False, threads=True),
                max_attempts=2,
                base_delay=2.0,
            )
            if data is None or data.empty:
                continue

            # Handle multi-index columns: levels[0]=price type, levels[1]=ticker
            if isinstance(data.columns, pd.MultiIndex):
                tickers_in_data = data.columns.levels[1]
                for sym in batch:
                    if sym not in tickers_in_data:
                        continue
                    try:
                        df = pd.DataFrame({
                            "close": data[("Close", sym)].dropna(),
                            "high": data[("High", sym)].dropna(),
                            "low": data[("Low", sym)].dropna(),
                            "open": data[("Open", sym)].dropna() if ("Open", sym) in data.columns else None,
                            "volume": data[("Volume", sym)].dropna() if ("Volume", sym) in data.columns else None,
                        })
                        if not df.empty:
                            hist_cache[sym] = df
                            _save_hist_to_db(sym, df)
                    except Exception:
                        pass
            else:
                # Single ticker case
                sym = batch[0] if len(batch) == 1 else None
                if sym and len(data) > 0:
                    df = pd.DataFrame({
                        "close": data["Close"].dropna() if "Close" in data.columns else data["close"].dropna(),
                        "high": data["High"].dropna() if "High" in data.columns else data["high"].dropna(),
                        "low": data["Low"].dropna() if "Low" in data.columns else data["low"].dropna(),
                        "open": data["Open"].dropna() if "Open" in data.columns else data.get("open", pd.Series()).dropna(),
                        "volume": data["Volume"].dropna() if "Volume" in data.columns else data.get("volume", pd.Series()).dropna(),
                    })
                    if not df.empty:
                        hist_cache[sym] = df
                        _save_hist_to_db(sym, df)
        except Exception:
            continue

    return hist_cache


def _score_stock(ticker, sector, fund_data, hist_cache):
    """Score a single stock using pre-fetched bulk data (no network calls)."""
    try:
        fd = fund_data.get(ticker)
        if not fd:
            return None

        roe = fd.get("roe", 0) or 0
        debt_equity = fd.get("debt_to_equity", 0) or 0
        pe_ratio = fd.get("trailing_pe")  # Can be None if invalid
        profit_margin = fd.get("profit_margin", 0) or 0

        # Compute drop from cached history
        hist = hist_cache.get(ticker)
        if hist is None or hist.empty:
            return None

        current_price = hist["close"].iloc[-1]
        high_price = hist["high"].max()
        drop_pct = round(((current_price - high_price) / high_price) * 100, 2)

        # Recovery metrics
        low_5d = hist["low"].tail(5).min()
        recovery_5d = round(((current_price - low_5d) / low_5d) * 100, 2) if low_5d > 0 else 0.0

        low_15d = hist["low"].tail(15).min()
        recovery_15d = round(((current_price - low_15d) / low_15d) * 100, 2) if low_15d > 0 else 0.0

        if abs(drop_pct) < 5 and sector != "Tracked":
            return None

        rsi = calculate_rsi(hist["close"])
        roe_pct = round(roe * 100, 2) if roe else 0

        quality_score = 0
        if roe_pct > 15:
            quality_score += 30
        if debt_equity < 100:
            quality_score += 25
        elif debt_equity < 200:
            quality_score += 15
        if profit_margin and profit_margin > 0.10:
            quality_score += 25
        if pe_ratio and pe_ratio < 25:
            quality_score += 20

        classification = classify_dip_quality(drop_pct, rsi, roe_pct, debt_equity)
        if classification == "NONE":
            return None

        return {
            "ticker": ticker,
            "name": fd.get("shortName", ticker),
            "sector": sector,
            "current_price": round(current_price, 2),
            "high_52w": round(high_price, 2),
            "drop_pct": drop_pct,
            "rsi": round(rsi, 1),
            "roe": roe_pct if roe_pct else None,
            "debt_equity": round(debt_equity, 2) if debt_equity else None,
            "profit_margin": round(profit_margin * 100, 2) if profit_margin else None,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
            "recovery_5d": recovery_5d,
            "recovery_15d": recovery_15d,
            "quality_score": quality_score,
            "volume": fd.get("avg_volume", 0),
            "avg_volume": fd.get("avg_volume", 0),
            "classification": classification,
        }
    except Exception:
        return None


def _bulk_fundamentals_fast(tickers: List[str]) -> Dict[str, dict]:
    """
    Fetch fundamentals. DB-first for cached tickers, yahooquery for missing.
    """
    from yahooquery import Ticker
    from persistent_cache import get_bulk_ticker_info
    
    out = {}
    if not tickers:
        return out
    
    # Step 1: Try DB first (instant for 500+ tickers)
    cached = get_bulk_ticker_info(tickers)
    for sym in tickers:
        data = cached.get(sym.upper(), {})
        if data and data.get('price') and data.get('price') > 0:
            out[sym.upper()] = {
                "roe": data.get("roe"),
                "debt_to_equity": data.get("debt_to_equity"),
                "shortName": data.get("name") or sym,
                "avg_volume": data.get("avg_volume"),
                "market_cap": data.get("market_cap"),
                "trailing_pe": data.get("trailing_pe"),
                "forward_pe": data.get("forward_pe"),
                "price_to_book": data.get("price_to_book"),
                "price_to_sales": data.get("price_to_sales"),
                "trailing_eps": data.get("trailing_eps"),
                "forward_eps": data.get("forward_eps"),
                "roa": data.get("roa"),
                "current_ratio": data.get("current_ratio"),
                "free_cashflow": data.get("free_cashflow"),
                "total_debt": data.get("total_debt"),
                "total_cash": data.get("total_cash"),
                "revenue_growth": data.get("revenue_growth"),
                "earnings_growth": data.get("earnings_growth"),
                "revenue": data.get("revenue"),
                "net_income": data.get("net_income"),
                "dividend_yield": data.get("dividend_yield"),
                "dividend_rate": data.get("dividend_rate"),
                "payout_ratio": data.get("payout_ratio"),
                "beta": data.get("beta"),
                "fifty_two_week_high": data.get("fifty_two_week_high"),
                "fifty_two_week_low": data.get("fifty_two_week_low"),
                "shares_outstanding": data.get("shares_outstanding"),
                "price": data.get("price"),
                "profit_margin": data.get("profit_margin"),
                "peg_ratio": data.get("peg_ratio"),
                "ev_ebitda": data.get("ev_ebitda"),
                "book_value": data.get("book_value"),
                "short_ratio": data.get("short_ratio"),
                "operating_cashflow": data.get("operating_cashflow"),
            }
    
    # Step 2: Fetch missing from yahooquery
    missing = [t for t in tickers if t.upper() not in out]
    if not missing:
        return out
    
    batch_size = 40
    batches = [missing[i:i + batch_size] for i in range(0, len(missing), batch_size)]
    
    def fetch_batch(batch):
        batch_out = {}
        try:
            tq = Ticker(batch)
            financial_data = tq.financial_data
            summary_detail = tq.summary_detail
            price_data = tq.price
            key_stats = tq.key_stats
            asset_profile = tq.asset_profile
            
            for sym in batch:
                try:
                    fd = financial_data.get(sym, {}) if isinstance(financial_data, dict) else {}
                    sd = summary_detail.get(sym, {}) if isinstance(summary_detail, dict) else {}
                    pd_data = price_data.get(sym, {}) if isinstance(price_data, dict) else {}
                    ks = key_stats.get(sym, {}) if isinstance(key_stats, dict) else {}
                    ap = asset_profile.get(sym, {}) if isinstance(asset_profile, dict) else {}
                    
                    roe = float(fd.get("returnOnEquity", 0) or 0)
                    de_ratio = float(fd.get("debtToEquity", 0) or 0)
                    mkt_cap = float(pd_data.get("marketCap", 0) or 0)
                    pe = float(sd.get("trailingPE", 0) or 0)
                    fpe = float(sd.get("forwardPE", 0) or 0)
                    pb = float(sd.get("priceToBook", 0) or 0)
                    ps = float(sd.get("priceToSalesTrailing12Months", 0) or 0)
                    eps = float(sd.get("trailingEps", 0) or 0)
                    feps = float(sd.get("forwardEps", 0) or 0)
                    roa = float(ks.get("returnOnAssets", 0) or 0)
                    cr = float(sd.get("currentRatio", 0) or 0)
                    fcf = float(fd.get("freeCashflow", 0) or 0)
                    td = float(fd.get("totalDebt", 0) or 0)
                    tc = float(fd.get("totalCash", 0) or 0)
                    rg = float(fd.get("revenueGrowth", 0) or 0)
                    eg = float(fd.get("earningsGrowth", 0) or 0)
                    rev = float(fd.get("totalRevenue", 0) or 0)
                    ni = float(fd.get("netIncomeToCommon", 0) or 0)
                    dy = float(sd.get("dividendYield", 0) or 0)
                    dr = float(sd.get("dividendRate", 0) or 0)
                    pr = float(sd.get("payoutRatio", 0) or 0)
                    beta = float(pd_data.get("beta", 0) or sd.get("beta", 0) or 0)
                    high52 = float(pd_data.get("fiftyTwoWeekHigh", 0) or 0)
                    low52 = float(pd_data.get("fiftyTwoWeekLow", 0) or 0)
                    shares = float(pd_data.get("sharesOutstanding", 0) or 0)
                    avg_vol = float(sd.get("averageVolume", 0) or 0)
                    current_price = float(pd_data.get("currentPrice", 0) or pd_data.get("regularMarketPrice", 0) or 0)
                    
                    batch_out[sym] = {
                        "roe": roe,  # yahooquery already returns as decimal (1.41 = 141%)
                        "debt_to_equity": de_ratio,
                        "shortName": pd_data.get("shortName") or sym,
                        "avg_volume": avg_vol,
                        "market_cap": mkt_cap,
                        "trailing_pe": pe if pe and pe > 0 else None,
                        "forward_pe": fpe if fpe and fpe > 0 else None,
                        "price_to_book": pb,
                        "price_to_sales": ps,
                        "trailing_eps": eps,
                        "forward_eps": feps,
                        "roa": roa,
                        "current_ratio": cr,
                        "free_cashflow": fcf,
                        "total_debt": td,
                        "total_cash": tc,
                        "revenue_growth": rg,
                        "earnings_growth": eg,
                        "revenue": rev,
                        "net_income": ni,
                        "dividend_yield": dy / 100 if dy > 1 else dy,
                        "dividend_rate": dr,
                        "payout_ratio": pr,
                        "beta": beta,
                        "fifty_two_week_high": high52,
                        "fifty_two_week_low": low52,
                        "shares_outstanding": shares,
                        "price": current_price,
                        "name": pd_data.get("shortName") or sym,
                        "sector": ap.get("sector") or "Unknown",
                        "industry": ap.get("industry") or "Unknown",
                        "longBusinessSummary": ap.get("longBusinessSummary") or "No business summary available.",
                        "profit_margin": float(ks.get("profitMargin", 0) or 0) / 100 if float(ks.get("profitMargin", 0) or 0) > 1 else float(ks.get("profitMargin", 0) or 0),
                        "peg_ratio": float(sd.get("pegRatio")) if sd.get("pegRatio") else None,
                        "ev_ebitda": float(sd.get("enterpriseToEbitda")) if sd.get("enterpriseToEbitda") else None,
                        "book_value": float(ks.get("bookValue")) if ks.get("bookValue") else None,
                        "short_ratio": float(sd.get("shortRatio")) if sd.get("shortRatio") else None,
                        "operating_cashflow": float(fd.get("operatingCashflow")) if fd.get("operatingCashflow") else None,
                    }
                    
                    # Save to persistent DB in background
                    try:
                        from persistent_cache import save_ticker_info
                        save_ticker_info(batch_out[sym])
                    except Exception:
                        pass
                except Exception:
                    continue
        except Exception:
            pass
        return batch_out
    
    # Fetch batches in parallel (3 batches max for ~120 tickers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_batch, b): b for b in batches}
        for future in concurrent.futures.as_completed(futures):
            batch_result = future.result()
            out.update(batch_result)
    
    return out


def _quick_filter(hist_cache, min_drop_pct: float = 5.0) -> List[str]:
    """Quick pre-filter: only keep tickers with meaningful drops."""
    candidates = []
    for ticker, hist in hist_cache.items():
        if hist is None or hist.empty:
            continue
        try:
            current = hist["close"].iloc[-1]
            high = hist["high"].max()
            drop = abs(((current - high) / high) * 100)
            if drop >= min_drop_pct:
                candidates.append(ticker)
        except Exception:
            continue
    return candidates


def _get_bleeding_sectors(drop_threshold: float = 8.0, rsi_threshold: float = 40.0) -> List[str]:
    """
    Identify sectors that are currently "bleeding" (underperforming).
    A sector is bleeding if its ETF has dropped more than `drop_threshold`%
    from its 52-week high AND RSI is below `rsi_threshold`.
    
    Returns list of sector names that qualify.
    """
    harmonized_sectors = {v: k for k, v in SECTOR_ETFS.items()}
    bleeding = []
    
    def check_sector(ticker_name):
        ticker, name = ticker_name
        try:
            etf = yf.Ticker(ticker)
            hist = fetch_with_retry(lambda t=etf: t.history(period='1y'), max_attempts=2, base_delay=1.0)
            if hist.empty:
                return None
            
            current = hist['Close'].iloc[-1]
            high = hist['High'].max()
            drop = ((current - high) / high) * 100
            rsi = calculate_rsi(hist['Close'])
            
            if abs(drop) > drop_threshold and rsi < rsi_threshold:
                return name
        except Exception:
            pass
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(check_sector, (t, n)): n for t, n in harmonized_sectors.items()}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                bleeding.append(result)
    
    return bleeding


def _build_scan_tasks(min_drop_pct: float = 3.0) -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    """
    Build scan task list with dynamic sector expansion.
    
    Logic:
    1. Check sector ETFs for "bleeding" sectors (drop > 8%, RSI < 40)
    2. For bleeding sectors → include ALL SECTOR_STOCKS constituents
    3. For normal sectors → use curated DIP_UNIVERSE subset
    4. Always include owned portfolio tickers (as "Tracked")
    
    Returns:
        tasks: List of (ticker, sector) tuples
        ticker_sector: Dict mapping ticker → sector
    """
    # Step 1: Detect bleeding sectors
    bleeding = _get_bleeding_sectors()
    
    # Step 2: Build task list
    tasks = []
    
    # Curated universe for normal sectors
    for sector, tickers in DIP_UNIVERSE.items():
        for s in tickers:
            tasks.append((s, sector))
    
    # Expand bleeding sectors to full constituent list
    for sector in bleeding:
        if sector in SECTOR_STOCKS:
            for s in SECTOR_STOCKS[sector]:
                tasks.append((s, sector))
    
    # Also include owned portfolio tickers
    try:
        from portfolio import PortfolioManager
        pm = PortfolioManager()
        owned = pm.get_all_owned_tickers()
        for s in owned:
            tasks.append((s.upper(), "Tracked"))
    except Exception:
        pass
    
    # Deduplicate while preserving sector mapping (bleeding sector overrides curated)
    ticker_sector = {}
    for ticker, sector in tasks:
        ticker_sector[ticker] = sector
    
    return [(t, s) for t, s in ticker_sector.items()], ticker_sector


@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)  # 1h hard, 30m soft (SWR)
def scan_stock_dips(min_quality_score: float = 0) -> List[Dict]:
    """
    Scan for dip opportunities with dynamic sector expansion.
    
    Architecture:
    1. Detect "bleeding" sectors via ETF analysis (drop > 8%, RSI < 40)
    2. For bleeding sectors → scan ALL constituents from SECTOR_STOCKS
    3. For normal sectors → scan curated DIP_UNIVERSE subset
    4. Batch download prices, pre-filter by drop %, fetch fundamentals for candidates
    5. Score and rank locally (no network calls in scoring phase)
    
    Performance:
    - Normal market: ~108 tickers, first run ~2-3 min, cached <1ms
    - Sector crash: ~150-250 tickers (expanded), first run ~3-5 min, cached <1ms
    - SWR: returns stale data instantly while refreshing in background
    """
    import time as _time
    _t0 = _time.time()
    
    # Build dynamic task list
    tasks, ticker_sector = _build_scan_tasks()
    # Filter out invalid symbols (e.g., those with $ prefix that cause yfinance errors)
    unique_tickers = [t for t in ticker_sector.keys() if not t.startswith('$') and len(t) <= 5]
    # Rebuild ticker_sector with filtered tickers
    ticker_sector = {t: s for t, s in ticker_sector.items() if t in unique_tickers}
    
    print(f"[Dip Hunter] Scanning {len(unique_tickers)} tickers ({len(_get_bleeding_sectors())} bleeding sectors)")
    
    # === PHASE 1: Batch price download (fast, ~3-6s for 100-250 tickers) ===
    print(f"[Dip Hunter] Phase 1/3: Downloading price history for {len(unique_tickers)} tickers...")
    hist_cache = _fetch_batch_history(unique_tickers, days=252)
    print(f"[Dip Hunter] Phase 1/3: Done in {_time.time()-_t0:.1f}s ({len(hist_cache)} tickers cached, saved to DB)")
    
    # === PHASE 2: Pre-filter by drop %, fetch fundamentals only for candidates ===
    candidate_tickers = _quick_filter(hist_cache, min_drop_pct=3.0)
    # Always include "Tracked" portfolio tickers regardless of drop
    for t, s in tasks:
        if s == "Tracked" and t not in candidate_tickers:
            candidate_tickers.append(t)
    
    print(f"[Dip Hunter] Phase 2/3: {len(candidate_tickers)} candidates after pre-filter. Fetching fundamentals...")
    
    fund_map = _bulk_fundamentals_fast(candidate_tickers) if candidate_tickers else {}
    print(f"[Dip Hunter] Phase 2/3: Done in {_time.time()-_t0:.1f}s ({len(fund_map)} fundamentals fetched, saved to DB)")
    
    # === PHASE 3: Score all candidates locally (no network calls) ===
    print(f"[Dip Hunter] Phase 3/3: Scoring {len(candidate_tickers)} candidates...")
    results = []
    for ticker in candidate_tickers:
        sector = ticker_sector.get(ticker, "Unknown")
        res = _score_stock(ticker, sector, fund_map, hist_cache)
        if res and res["quality_score"] >= min_quality_score:
            results.append(res)
    
    results.sort(key=lambda x: (-x["quality_score"], x["drop_pct"]))
    print(f"[Dip Hunter] Complete: {len(results)} opportunities found in {_time.time()-_t0:.1f}s")
    return results[:100]


def get_dip_summary() -> Dict:
    """
    Get overall dip market summary
    """
    etf_dips = scan_etf_dips()
    stock_dips = scan_stock_dips()
    
    # Count by classification
    best_count = sum(1 for s in stock_dips if s['classification'] == 'BEST')
    better_count = sum(1 for s in stock_dips if s['classification'] == 'BETTER')
    good_count = sum(1 for s in stock_dips if s['classification'] == 'GOOD')
    
    # Get market ETF status
    market_etf_dips = [e for e in etf_dips if e['is_market_etf']]
    
    return {
        "total_opportunities": len(stock_dips),
        "best_dips": best_count,
        "better_dips": better_count,
        "good_dips": good_count,
        "market_etfs_dipping": len(market_etf_dips),
        "avg_market_drop": round(sum(e['drop_pct'] for e in market_etf_dips) / len(market_etf_dips), 2) if market_etf_dips else 0,
        "last_updated": _DIP_CACHE.last_update.isoformat() if _DIP_CACHE.last_update else datetime.now().isoformat()
    }
