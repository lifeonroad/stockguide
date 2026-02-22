
import time
import yfinance as yf
from typing import Optional
import pandas as pd
import random
from cache_utils import timed_cache, fetch_with_retry

# Mapping Sectors to ETFs (Proxies)
SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC"
}

# Pre-defined list of top stocks per sector for MVP scanning
# Expanded to ~20-25 per sector for deeper dip hunting
SECTOR_STOCKS = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "ADBE", "CSCO", "CRM",
        "AMD", "TXN", "QCOM", "INTU", "AMAT", "IBM", "MU", "NOW",
        "PANW", "SNPS", "CDNS", "KLAC", "APH", "MSI", "TEL", "LRCX"
    ],
    "Financials": [
        "JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "C",
        "V", "MA", "SPGI", "PYPL", "FIS", "ICE", "CB", "PGR",
        "MET", "AIG", "TRV", "PNC", "USB", "TFC", "SCHW", "BRK-B"
    ],
    "Healthcare": [
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "PFE", "AMGN",
        "DHR", "ISRG", "SYK", "VRTX", "REGN", "BMY", "GILD", "ZTS",
        "MDT", "BDX", "BSX", "HUM", "CI", "ELV", "MCK", "ABT"
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO",
        "OXY", "HAL", "BKR", "HES", "KMI", "WMB", "TRGP", "FANG",
        "DVN", "CTRA", "OKE", "APA"
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG",
        "TJX", "LULU", "CMG", "F", "GM", "MAR", "HLT", "RCL",
        "CCL", "AZO", "ORLY", "EBAY", "ETSY", "PHM", "LEN", "DHI"
    ],
    "Industrials": [
        "CAT", "UNP", "GE", "HON", "DE", "UPS", "LMT", "BA",
        "RTX", "MMM", "L3H", "NSC", "CSX", "FDX", "WM", "RSG",
        "PH", "ITW", "ETN", "EMR", "ROP", "TDG", "GD", "NOC"
    ],
    "Consumer Staples": [
        "PG", "COST", "PEP", "KO", "WMT", "PM", "MO", "CL",
        "EL", "TGT", "KHC", "MDLZ", "GIS", "SYY", "ADM", "MNST",
        "HSY", "KR", "STZ", "K", "MKC", "CHD"
    ],
    "Materials": [
        "LIN", "SHW", "FCX", "APD", "ECL", "NEM", "DOW", "DD",
        "ALB", "PPG", "VMC", "MLM", "CTVA", "CF", "MOS", "NUE",
        "STLD", "FREE", "FMC", "CE"
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "AEP", "SRE", "D", "EXC", "PEG",
        "XEL", "ED", "WEC", "ES", "PCG", "FE", "VST", "CEG",
        "CNP", "CMS", "ATO", "NI"
    ],
    "Real Estate": [
        "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "VICI", "DLR",
        "SPG", "WELL", "CBRE", "AVB", "EQR", "ARE", "WY", "IRM",
        "VTR", "BXP", "HST", "MAA"
    ],
    "Communication Services": [
        "GOOGL", "META", "NFLX", "DIS", "TMUS", "CMCSA", "VZ", "T",
        "CHTR", "WBD", "FOXA", "PARA", "TTWO", "EA", "MTCH", "OMC",
        "IPG", "LYV", "NFLX", "GOOG"
    ]
}

# Specialized Lists
GROWTH_STOCKS = [
    "NVDA", "PLTR", "SNOW", "TSLA", "AMD", "ARM", "MSTR", "SQ", 
    "SHOP", "MDB", "DDOG", "NET", "CRWD", "ZS", "OKTA", "PANW", 
    "SMCI", "ANET", "U", "MELI", "COIN", "DKNG", "HOOD", "RBLX"
]

DIVIDEND_KINGS = [
    "KO", "PEP", "PG", "JNJ", "MMM", "ABBV", "LOW", "TGT", 
    "CVX", "XOM", "MCD", "SYY", "ADM", "CL", "GPC", "SPGI", 
    "ITW", "EMR", "DOV", " Genuine Parts (GPC)", "SPG", "K", "MO", "PM"
]


def get_sector_stocks(sector: Optional[str] = None, n: int = 25) -> dict:
    """
    Single source of truth for sector ticker lists.
    Returns INSTANTLY — never blocks on network calls.
    Triggers background scoring on first call so future requests get live data.

    Returns
    -------
    If *sector* is given:
        { "tickers": [...], "is_dynamic": bool, "scored_at": str }
    If *sector* is None:
        Full dict keyed by sector name.
    """
    try:
        from dynamic_universe import (  # noqa: PLC0415
            get_sector_stocks_cached,
            trigger_background_score,
        )
        # Kick off background scoring (no-op if already running or cache fresh)
        trigger_background_score(n=n)
        universe = get_sector_stocks_cached(n=n)
    except Exception:
        from datetime import datetime, timezone  # noqa: PLC0415
        now = datetime.now(timezone.utc).isoformat()
        universe = {
            s: {"tickers": t, "is_dynamic": False, "scored_at": now}
            for s, t in SECTOR_STOCKS.items()
        }

    if sector is not None:
        return universe.get(sector, {
            "tickers": SECTOR_STOCKS.get(sector, []),
            "is_dynamic": False,
            "scored_at": None,
        })
    return universe


def get_sector_meta(sector: Optional[str] = None) -> dict:
    """
    Return universe metadata (is_dynamic, scored_at, ttl_hours, partially_dynamic).
    Instant — reads from cache only, never triggers network calls.
    """
    try:
        from dynamic_universe import get_sector_meta as _get_meta  # noqa: PLC0415
        return _get_meta(sector=sector)
    except Exception:
        return {
            "is_dynamic": False,
            "partially_dynamic": False,
            "scored_at": None,
            "ttl_hours": 24,
        }


def get_sector_metrics_from_constituents(sector_name):
    """
    Calculate sector average ROE and Debt/Equity from top constituent stocks.
    Returns tuple: (avg_roe, avg_debt_equity)
    """
    stocks = get_sector_stocks(sector_name).get("tickers", [])
    if not stocks:
        return 0, 0
    
    roe_values = []
    debt_values = []
    
    # Sample top 5 stocks for speed (instead of all)
    for symbol in stocks[:5]:  # noqa: E501
        try:
            ticker = yf.Ticker(symbol)
            info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3, base_delay=1.5)

            roe = info.get('returnOnEquity', 0)
            debt = info.get('debtToEquity', 0)

            # Only include valid values
            if roe and roe > 0:
                roe_values.append(roe * 100)  # Convert to percentage
            if debt and debt >= 0:  # 0 debt is valid
                debt_values.append(debt)
        except Exception:
            # Skip stocks with errors
            continue
        time.sleep(0.2)  # gentle throttle between per-stock calls
    
    # Calculate averages
    avg_roe = sum(roe_values) / len(roe_values) if roe_values else 0
    avg_debt = sum(debt_values) / len(debt_values) if debt_values else 0
    
    return round(avg_roe, 2), round(avg_debt, 2)


@timed_cache(ttl_seconds=3600)  # Cache for 1 hour
def get_industry_rankings():
    """
    Analyzes Sector ETFs with real constituent-based metrics.
    Calculates ROE and Debt/Equity from top holdings in each sector.
    """
    results = []
    
    for sector, ticker_symbol in SECTOR_ETFS.items():
        ticker = yf.Ticker(ticker_symbol)
        try:
            info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3, base_delay=1.5)
        except Exception:
            info = {}
        time.sleep(0.2)  # gentle throttle between ETF calls

        # Extract ETF-level metrics
        pe = info.get('trailingPE') or info.get('forwardPE') or 20
        div_yield = info.get('yield', 0) or info.get('trailingAnnualDividendYield', 0)
        
        # Calculate constituent-based metrics
        avg_roe, avg_debt = get_sector_metrics_from_constituents(sector)
        
        results.append({
            "industry": sector,
            "etf": ticker_symbol,
            "pe": round(pe, 2),
            "dividend_yield": round(div_yield * 100, 2) if div_yield else 0,
            "roe": avg_roe,
            "debt_to_equity": avg_debt
        })

    # Sort by 'Value' (Low PE)
    sorted_results = sorted(results, key=lambda x: x['pe'])
    return sorted_results


def analyze_sector_fundamentals(sector_name):
    """
    Deep dive into a sector:
    Fetches top stocks, calculates avg ROE, Debt/Eq, P/E.
    Returns: Sector Stats + Top Pick Stocks
    """
    stocks = SECTOR_STOCKS.get(sector_name, [])
    if not stocks:
        # Fallback for sectors not in our short list
        return {"error": "Sector data not fully mapped for MVP"}
        
    stock_data = []
    
    for symbol in stocks:
        t = yf.Ticker(symbol)
        try:
            i = fetch_with_retry(lambda _t=t: _t.info, max_attempts=3, base_delay=1.5)
        except Exception:
            i = {}
        time.sleep(0.2)  # gentle throttle
        
        # Fundamental checks
        roe = i.get('returnOnEquity', 0)
        de = i.get('debtToEquity', 0)
        pe = i.get('trailingPE', 99)
        profit_margin = i.get('profitMargins', 0)
        
        stock_data.append({
            "symbol": symbol,
            "name": i.get('shortName', symbol),
            "price": i.get('currentPrice', 0),
            "pe": round(pe, 2) if pe else 0,
            "roe": round(roe * 100, 2) if roe else 0,
            "debt_to_equity": round(de, 2) if de else 0,
            "profit_margin": round(profit_margin * 100, 2) if profit_margin else 0
        })
        
    # Calculate Sector Averages
    avg_roe = sum(s['roe'] for s in stock_data) / len(stock_data) if stock_data else 0
    avg_pe = sum(s['pe'] for s in stock_data) / len(stock_data) if stock_data else 0
    avg_de = sum(s['debt_to_equity'] for s in stock_data) / len(stock_data) if stock_data else 0
    avg_margin = sum(s['profit_margin'] for s in stock_data) / len(stock_data) if stock_data else 0
    
    # Filter for "Warren's Picks"
    # Logic: High ROE (>15), Healthy Debt (<100 approx), Fair PE
    top_picks = [
        s for s in stock_data 
        if s['roe'] > 15 and s['debt_to_equity'] < 200 # Relaxed for MVP (Banks have high D/E)
    ]
    
    # Tie-breaker: PE (Lower is better)
    top_picks = sorted(top_picks, key=lambda x: x['pe'])[:5]
    
    return {
        "sector": sector_name,
        "avg_roe": round(avg_roe, 2),
        "avg_pe": round(avg_pe, 2),
        "avg_debt_equity": round(avg_de, 2),
        "avg_profit_margin": round(avg_margin, 2),
        "top_stocks": top_picks,
        "all_analyzed": stock_data
    }
