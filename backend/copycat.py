from data_client import get_ticker_info
from cache_utils import timed_cache, fetch_with_retry

# Defined based on our Superinvestor research
COPYCAT_HOLDINGS = [
    {"symbol": "RIG", "name": "Transocean", "held_by": ["Pabrai"]},
    {"symbol": "AMR", "name": "Alpha Metallurgical", "held_by": ["Pabrai"]},
    {"symbol": "GOOGL", "name": "Alphabet", "held_by": ["Buffett", "Druckenmiller"]},
    {"symbol": "AMZN", "name": "Amazon", "held_by": ["Druckenmiller"]},
    {"symbol": "LEN", "name": "Lennar Corp", "held_by": ["Buffett"]},
    {"symbol": "MOH", "name": "Molina Healthcare", "held_by": ["Burry"]},
    {"symbol": "NTRA", "name": "Natera", "held_by": ["Druckenmiller"]},
    {"symbol": "STZ", "name": "Constellation Brands", "held_by": ["Buffett"]},
    {"symbol": "EEM", "name": "Emerging Markets ETF", "held_by": ["Druckenmiller"]},
    {"symbol": "BABA", "name": "Alibaba", "held_by": ["Burry (Q2)"]}
]

@timed_cache(ttl_seconds=600, soft_ttl_seconds=400)  # 10m hard, ~7m soft (SWR)
def get_copycat_performance():
    """
    Fetches real-time performance for the Superinvestor Copycat Portfolio.
    """
    import time
    tickers = [h['symbol'] for h in COPYCAT_HOLDINGS]
    data = []

    try:
        # Fetch using data_client (respects defeatbeta toggle)
        for holding in COPYCAT_HOLDINGS:
            sym = holding['symbol']
            
            try:
                info = get_ticker_info(sym)
                if not info:
                    continue
                
                # Get price data
                price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
                prev_close = info.get('regularMarketPreviousClose', price)
                
                # Daily Change
                change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
                
                # YTD / 52W Change
                perf_year = info.get('52WeekChange', 0.0) * 100

                data.append({
                    "symbol": sym,
                    "name": holding['name'],
                    "held_by": holding['held_by'],
                    "price": price,
                    "daily_change": round(change_pct, 2),
                    "yearly_change": round(perf_year, 2),
                    "market_cap": info.get('marketCap', 0)
                })
                
                # Small delay between requests to avoid overwhelming the API
                time.sleep(0.2)
                
            except Exception as stock_err:
                print(f"Error fetching {sym}: {stock_err}")
                continue

        # Sort by best daily performer
        if data:
            data.sort(key=lambda x: x['daily_change'], reverse=True)
        return data if data else {
            "error": "No Data",
            "message": "Unable to fetch any stock data. Yahoo Finance may be blocking requests.",
            "data": []
        }

    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching copycat data: {error_msg}")
        
        # Check for specific error types
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            return {
                "error": "API Access Blocked",
                "message": "Yahoo Finance is blocking automated requests. This is temporary - the dashboard will retry automatically.",
                "data": []
            }
        elif "rate" in error_msg.lower() or "too many" in error_msg.lower():
            return {
                "error": "Rate Limited",
                "message": "Too many requests. Please wait 5-10 minutes.",
                "data": []
            }
        
        return {
            "error": "Data Fetch Error", 
            "message": f"Unable to fetch data: {error_msg}",
            "data": []
        }
