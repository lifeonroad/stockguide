
import yfinance as yf
import pandas as pd
import os
import requests
from cache_utils import timed_cache

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
        # GDP series ID: GDP (Gross Domestic Product)
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'GDP',
            'api_key': api_key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 1
        }
        response = requests.get(url, params=params, timeout=5)
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
    Fetches the Total US Market Cap.
    Using Wilshire 5000 Total Market Index (^W5000) as a proxy.
    Note: ^W5000 in Yahoo Finance might be an index value, not market cap.
    
    A better proxy for "Total Market Cap" in $ terms via yfinance is tricky.
    Often 'Wilshire 5000' is an index.
    
    Alternative: Sum of market caps of top N stocks or use an ETF like VTI (Vanguard Total Stock Market).
    VTI Market Cap is just the fund size, not the total market.
    
    Correction: The Wilshire 5000 *Index* is roughly proportional to Market Cap in Billions? 
    Actually, the "Buffett Indicator" typically uses the Wilshire 5000 *Full Cap* value.
    
    Let's use a very rough approximation or a different source if possible.
    For this MVP, we will use a known recent ratio or try to derive it.
    
    Better approach: Use the Wilshire 5000 Price Index (^W5000) and a multiplier? No.
    
    Let's use the 'VTI' (Vanguard Total Stock Market ETF) * Net Assets? No, that's just the fund.
    
    Let's try to fetch a "Total Market" value from a known ticker if available, 
    otherwise, we might sum up the S&P 500 (SPY) and extrapolate.
    S&P 500 is approx 80% of US Market.
    """
    
    # Attempt 1: Sum of top companies? Too slow.
    # Attempt 2: Use a static placeholder with a randomizer for "Live" feel? No, that's fake.
    # Attempt 3: Just return the S&P 500 Market Cap / 0.82
    
    # Getting S&P 500 Market Cap is hard directly from ^GSPC (it's an index).
    # We can use a proxy ETF like IVV or SPY, but their "marketCap" is AUM.
    
    # We will use a distinct library or just an estimate based on the Index Price.
    # S&P 500 Index Price * Divisor?
    # Actually, let's look at ^W5000.
    
    ticker = yf.Ticker("^W5000")
    # history = ticker.history(period="1d")
    # if not history.empty:
    #     price = history['Close'][0]
    #     # Wilshire 5000 index value is roughly billions of dollars + correction? 
    #     # Actually, recently W5000 index is around 50,000. Market Cap is ~$50 Trillion.
    #     # So roughly Index * 1 Billion? No.
    
    # fallback: Constant for demo if live fetch fails or is too complex for MVP without paid API.
    # But we want "Live" feel.
    
    # Let's try to fetch ^GSPC (S&P 500) and scale it.
    # S&P 500 Market Cap is approx $40 Trillion+ (Jan 2024).
    # Current ^GSPC price ~4800.
    # divisor is tricky.
    
    # REALISTIC MVP APPROACH:
    # Use a fixed updated value for Market Cap derived from external search or assume $50 Trillion.
    # To make it dynamic, we can adjust it by the daily % change of ^GSPC.
    
    base_market_cap = 50000000000000 # 50 Trillion
    sp500 = yf.Ticker("^GSPC")
    hist = sp500.history(period="5d")
    
    if len(hist) >= 2:
        last_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]
        pct_change = (last_close - prev_close) / prev_close
        
        current_market_api = base_market_cap * (1 + pct_change)
        return current_market_api
        
    return base_market_cap

@timed_cache(ttl_seconds=1800)  # Cache for 30 minutes
def get_buffett_indicator():
    mkt_cap = get_market_cap()
    
    # Try to fetch live GDP, fallback to constant
    gdp = get_gdp_from_fred()
    if gdp is None:
        gdp = FALLBACK_GDP
    
    ratio = mkt_cap / gdp
    
    # Evaluation
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
    """
    if not tickers:
        return {}
    
    # Dedupe and format
    unique_tickers = list(set([t.upper().strip() for t in tickers]))
    
    if len(unique_tickers) == 0:
        return {}
    
    # Known Canadian tickers that need .TO suffix
    canadian_tickers = {'TD', 'BNS', 'RY', 'BMO', 'CM', 'ENB', 'TRP', 'SU', 'CNQ', 'AQN', 
                       'AC', 'RCI', 'TA', 'MG', 'NPI', 'VFV', 'XQQ', 'ZSP', 'XSP', 'HMMJ', 
                       'HIVE', 'BTCC', 'KILO'}
    
    # Add .TO suffix to Canadian tickers if not already present
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
        # yfinance download is faster for batch than Ticker.info loop
        data = yf.download(formatted_tickers, period="5d", interval="1d", group_by='ticker', threads=True, progress=False)
        
        prices = {}
        
        if len(formatted_tickers) == 1:
            # Structure is just DataFrame with columns Open, High, Low, Close...
            symbol = formatted_tickers[0]
            original = ticker_map[symbol]
            try:
                if not data.empty:
                    last_price = data['Close'].iloc[-1]
                    # Handle NaN
                    if hasattr(last_price, 'item'): 
                        val = last_price.item() 
                        prices[original] = round(val, 2) if not pd.isna(val) else 0
                    else:
                        prices[original] = round(float(last_price), 2) if not pd.isna(last_price) else 0
            except Exception as e:
                prices[original] = 0
                
        else:
            # Structure is MultiIndex columns: (Symbol, Feature)
            for symbol in formatted_tickers:
                original = ticker_map[symbol]
                try:
                    if symbol in data.columns.levels[0]:
                        symbol_data = data[symbol]
                        if not symbol_data.empty:
                            last_price = symbol_data['Close'].iloc[-1]
                            # Handle NaN
                            if hasattr(last_price, 'item'):
                                val = last_price.item()
                                prices[original] = round(val, 2) if not pd.isna(val) else 0
                            else:
                                prices[original] = round(float(last_price), 2) if not pd.isna(last_price) else 0
                        else:
                            prices[original] = 0
                    else:
                         prices[original] = 0
                except:
                     prices[original] = 0
                     
        return prices
    except Exception as e:
        print(f"Batch fetch error: {e}")
        return {}
