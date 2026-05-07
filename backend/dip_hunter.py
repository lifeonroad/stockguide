"""
Dip Hunter Module
Detects market dips and classifies them as good/better/best opportunities

Architecture
------------
1. Uses yf.download() in batches of 50 for price history (single HTTP call per batch).
2. Uses _bulk_fundamentals() for fundamentals (parallel ThreadPoolExecutor).
3. @timed_cache with SWR: cached responses are instant; stale data served
   while background refresh runs.
4. Scans ~250 tickers in ~15-25s on first run; <1ms on cache hits.
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
from screener import SECTOR_ETFS, get_sector_stocks
from cache_utils import fetch_with_retry, timed_cache
from data_client import get_ticker_info, get_price_history
from dynamic_universe import _bulk_fundamentals

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
    """Fetch 1-year price history for many tickers in a single yf.download() call."""
    hist_cache = {}
    if not tickers:
        return hist_cache

    # yf.download() with ~80 tickers in one go is much faster than individual calls
    # Split into batches of 50 to avoid timeout
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
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
                        })
                        if not df.empty:
                            hist_cache[sym] = df
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
                    })
                    if not df.empty:
                        hist_cache[sym] = df
        except Exception:
            continue

    return hist_cache


def _score_stock(ticker, sector, fund_data, hist_cache):
    """Score a single stock using pre-fetched bulk data (no network calls)."""
    try:
        fd = fund_data.get(ticker)
        if not fd:
            return None

        roe = fd.get("roe", 0)
        debt_equity = fd.get("debt_to_equity", 0)
        pe_ratio = 0
        profit_margin = 0

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
            "roe": roe_pct,
            "debt_equity": round(debt_equity, 2) if debt_equity else 0,
            "profit_margin": round(profit_margin * 100, 2) if profit_margin else 0,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else 0,
            "recovery_5d": recovery_5d,
            "recovery_15d": recovery_15d,
            "quality_score": quality_score,
            "volume": fd.get("avg_volume", 0),
            "avg_volume": fd.get("avg_volume", 0),
            "classification": classification,
        }
    except Exception:
        return None


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


@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)  # 1h hard, 30m soft (SWR)
def scan_stock_dips(min_quality_score: float = 0) -> List[Dict]:
    """
    Scan curated quality stock list (~80 tickers) for dip opportunities.
    
    Two-phase approach:
    1. Batch download all prices at once (fast, single HTTP call per 50 tickers)
    2. Pre-filter by drop %, then fetch fundamentals only for candidates
    3. Score and rank locally
    
    Performance:
    - First run: ~8-15s (phase 1 ~3s, phase 2 ~5-12s depending on candidates)
    - Cached: < 1ms
    - SWR: returns stale data instantly while refreshing in background
    """
    tasks = []

    # Build task list from curated DIP_UNIVERSE
    for sector, tickers in DIP_UNIVERSE.items():
        for s in tickers:
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

    unique_tickers = list({t[0]: t for t in tasks}.keys())
    ticker_sector = {t[0]: t[1] for t in tasks}

    # === PHASE 1: Batch price download (fast, ~3s for 80 tickers) ===
    hist_cache = _fetch_batch_history(unique_tickers, days=252)

    # === PHASE 2: Pre-filter by drop %, fetch fundamentals only for candidates ===
    candidate_tickers = _quick_filter(hist_cache, min_drop_pct=3.0)
    # Always include "Tracked" portfolio tickers regardless of drop
    for t, s in tasks:
        if s == "Tracked" and t not in candidate_tickers:
            candidate_tickers.append(t)

    fund_map = _bulk_fundamentals(candidate_tickers) if candidate_tickers else {}

    # === PHASE 3: Score all candidates locally (no network calls) ===
    results = []
    for ticker in candidate_tickers:
        sector = ticker_sector.get(ticker, "Unknown")
        res = _score_stock(ticker, sector, fund_map, hist_cache)
        if res and res["quality_score"] >= min_quality_score:
            results.append(res)

    results.sort(key=lambda x: (-x["quality_score"], x["drop_pct"]))
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
