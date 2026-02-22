
import yfinance as yf
import pandas as pd
import os
import requests
from cache_utils import timed_cache, fetch_with_retry

# Fallback GDP if API fails
FALLBACK_GDP = 28000000000000  # 28 Trillion USD

def get_gdp_from_fred():
    """
    Fetches latest US GDP from FRED API.
    Requires FRED_API_KEY environment variable.
    Returns GDP in dollars or None if fetch fails.
    """
    api_key = os.getenv('FRED_API_KEY')
    if not api_key:
        return None
    
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'GDP',
            'api_key': api_key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 1
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'observations' in data and len(data['observations']) > 0:
            # GDP is in billions, convert to dollars
            gdp_billions = float(data['observations'][0]['value'])
            return gdp_billions * 1_000_000_000
    except Exception as e:
        print(f"FRED API error: {e}")
    
    return None


@timed_cache(ttl_seconds=1800)  # Cache for 30 minutes
def get_market_cap():
    """
    Fetches the Total US Market Cap via S&P 500 daily % change applied
    to a base estimate.  Uses fetch_with_retry so transient Yahoo Finance
    rate-limits don't propagate as hard errors.
    """
    base_market_cap = 50_000_000_000_000  # 50 Trillion baseline

    try:
        def _download():
            return yf.download(
                "^GSPC",
                period="5d",
                progress=False,
                threads=False,   # avoid extra threads on shared cloud IPs
            )

        hist = fetch_with_retry(_download, max_attempts=3, base_delay=2.0)

        if len(hist) >= 2:
            last_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            pct_change = (last_close - prev_close) / prev_close
            # Flatten scalar if pandas returns a Series with one element
            if hasattr(pct_change, 'item'):
                pct_change = pct_change.item()
            return base_market_cap * (1 + float(pct_change))
    except Exception as e:
        print(f"get_market_cap error: {e}")

    return base_market_cap


@timed_cache(ttl_seconds=1800)  # Cache for 30 minutes
def get_buffett_indicator():
    mkt_cap = get_market_cap()
    
    # Try to fetch live GDP, fallback to constant
    gdp = get_gdp_from_fred()
    if gdp is None:
        gdp = FALLBACK_GDP
    
    ratio = mkt_cap / gdp
    
    if ratio < 0.75:
        rating = "Undervalued"
    elif ratio < 0.95:
        rating = "Fair Valued"
    elif ratio < 1.15:
        rating = "Overvalued"
    else:
        rating = "Significantly Overvalued"
        
    return {
        "market_cap": mkt_cap,
        "gdp": gdp,
        "ratio_percent": round(ratio * 100, 2),
        "rating": rating
    }


@timed_cache(ttl_seconds=900)  # Cache for 15 minutes
def get_batch_quotes(tickers: list):
    """
    Efficiently fetches current prices for multiple tickers.
    Returns dict: {symbol: price}

    Uses threads=False to avoid hammering Yahoo from a shared cloud IP.
    """
    if not tickers:
        return {}
    
    # Dedupe and format
    unique_tickers = list(set([t.upper().strip() for t in tickers]))
    
    if len(unique_tickers) == 0:
        return {}
    
    # Known Canadian tickers that need .TO suffix
    canadian_tickers = {
        'TD', 'BNS', 'RY', 'BMO', 'CM', 'ENB', 'TRP', 'SU', 'CNQ', 'AQN',
        'AC', 'RCI', 'TA', 'MG', 'NPI', 'VFV', 'XQQ', 'ZSP', 'XSP', 'HMMJ',
        'HIVE', 'BTCC', 'KILO',
    }
    
    formatted_tickers = []
    ticker_map = {}  # Maps formatted ticker back to original

    for t in unique_tickers:
        base = t.replace('.TO', '').replace('.B', '')
        if base in canadian_tickers and not t.endswith('.TO'):
            formatted = f"{base}.TO"
            formatted_tickers.append(formatted)
            ticker_map[formatted] = t
        else:
            formatted_tickers.append(t)
            ticker_map[t] = t
        
    try:
        def _download():
            return yf.download(
                formatted_tickers,
                period="5d",
                interval="1d",
                group_by='ticker',
                threads=False,   # avoid extra threads on shared cloud IPs
                progress=False,
            )

        data = fetch_with_retry(_download, max_attempts=3, base_delay=2.0)
        
        prices = {}
        
        if len(formatted_tickers) == 1:
            symbol = formatted_tickers[0]
            original = ticker_map[symbol]
            try:
                if not data.empty:
                    last_price = data['Close'].iloc[-1]
                    if hasattr(last_price, 'item'):
                        val = last_price.item()
                        prices[original] = round(val, 2) if not pd.isna(val) else 0
                    else:
                        prices[original] = round(float(last_price), 2) if not pd.isna(last_price) else 0
            except Exception:
                prices[original] = 0
                
        else:
            for symbol in formatted_tickers:
                original = ticker_map[symbol]
                try:
                    if symbol in data.columns.levels[0]:
                        symbol_data = data[symbol]
                        if not symbol_data.empty:
                            last_price = symbol_data['Close'].iloc[-1]
                            if hasattr(last_price, 'item'):
                                val = last_price.item()
                                prices[original] = round(val, 2) if not pd.isna(val) else 0
                            else:
                                prices[original] = round(float(last_price), 2) if not pd.isna(last_price) else 0
                        else:
                            prices[original] = 0
                    else:
                        prices[original] = 0
                except Exception:
                    prices[original] = 0
                     
        return prices
    except Exception as e:
        print(f"Batch fetch error: {e}")
        return {}
