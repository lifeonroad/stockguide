"""
Dip Hunter Module
Detects market dips and classifies them as good/better/best opportunities
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from screener import SECTOR_ETFS, SECTOR_STOCKS, GROWTH_STOCKS, DIVIDEND_KINGS

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
            hist = ticker_obj.history(period='1y')
        else:  # 20d
            hist = ticker_obj.history(period='1mo')
        
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
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period='1y')
            if hist.empty: return None
            
            drop_pct, current_price, high_price = get_drop_from_high(etf, '52w')
            rsi = calculate_rsi(hist['Close'])
            
            if abs(drop_pct) >= 3:
                info = etf.info
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
                    "classification": classify_dip_quality(drop_pct, rsi),
                    "is_market_etf": ticker in MARKET_ETFS
                }
        except Exception: return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_etf_data, t, n) for t, n in all_etfs.items()]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: results.append(res)

    results.sort(key=lambda x: x['drop_pct'])
    _DIP_CACHE.set("etf_dips", results)
    return results

def fetch_single_stock(ticker, sector):
    """Helper for concurrent stock scanning"""
    try:
        stock = yf.Ticker(ticker)
        # We only need enough history for RSI (30 days is fine, but 1y is safer for 52w high)
        hist = stock.history(period='1y')
        if hist.empty: return None
        
        # Calculate drop metrics first for quick filtering
        current_price = hist['Close'].iloc[-1]
        high_price = hist['High'].max()
        drop_pct = round(((current_price - high_price) / high_price) * 100, 2)
        
        if abs(drop_pct) < 5: return None
        
        info = stock.info
        rsi = calculate_rsi(hist['Close'])
        roe = info.get('returnOnEquity', 0)
        debt_equity = info.get('debtToEquity', 0)
        profit_margin = info.get('profitMargins', 0)
        pe_ratio = info.get('trailingPE', 0)
        roe_pct = round(roe * 100, 2) if roe else 0
        
        quality_score = 0
        if roe_pct > 15: quality_score += 30
        if debt_equity < 100: quality_score += 25
        elif debt_equity < 200: quality_score += 15
        if profit_margin and profit_margin > 0.10: quality_score += 25
        if pe_ratio and pe_ratio < 25: quality_score += 20
        
        classification = classify_dip_quality(drop_pct, rsi, roe_pct, debt_equity)
        if classification == "NONE": return None
        
        return {
            "ticker": ticker,
            "name": info.get('shortName', ticker),
            "sector": sector,
            "current_price": round(current_price, 2),
            "high_52w": round(high_price, 2),
            "drop_pct": drop_pct,
            "rsi": round(rsi, 1),
            "roe": roe_pct,
            "debt_equity": round(debt_equity, 2) if debt_equity else 0,
            "profit_margin": round(profit_margin * 100, 2) if profit_margin else 0,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else 0,
            "quality_score": quality_score,
            "volume": info.get('volume', 0),
            "avg_volume": info.get('averageVolume', 0),
            "classification": classification
        }
    except Exception: return None

def scan_stock_dips(min_quality_score: float = 0) -> List[Dict]:
    """Scan expanded quality stock list (Sectors, Growth, Dividends) with caching"""
    cache_key = f"stock_dips_{min_quality_score}"
    cached_data = _DIP_CACHE.get(cache_key)
    if cached_data:
        return cached_data

    results = []
    tasks = []
    
    for sector, stocks in SECTOR_STOCKS.items():
        for s in stocks: tasks.append((s, sector))
    for s in GROWTH_STOCKS: tasks.append((s, "Hyper-Growth"))
    for s in DIVIDEND_KINGS: tasks.append((s, "Dividend Kings"))
    
    unique_tasks = list({t[0]: t for t in tasks}.values())

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_single_stock, t, s) for t, s in unique_tasks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res and res['quality_score'] >= min_quality_score:
                results.append(res)

    results.sort(key=lambda x: (-x['quality_score'], x['drop_pct']))
    final_results = results[:100]
    _DIP_CACHE.set(cache_key, final_results)
    return final_results


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
