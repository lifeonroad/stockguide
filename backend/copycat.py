import yfinance as yf

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

def get_copycat_performance():
    """
    Fetches real-time performance for the Superinvestor Copycat Portfolio.
    """
    tickers = [h['symbol'] for h in COPYCAT_HOLDINGS]
    data = []

    try:
        # Batch fetch for efficiency
        tickers_str = " ".join(tickers)
        stocks = yf.Tickers(tickers_str)

        for holding in COPYCAT_HOLDINGS:
            sym = holding['symbol']
            stock = stocks.tickers[sym]
            
            # Fast info access
            info = stock.info
            
            # Get price data
            price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
            prev_close = info.get('regularMarketPreviousClose', price)
            
            # Daily Change
            change_pct = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
            
            # YTD / 52W Change (YTD is often not direct, use 52WeekChange as proxy or calculate)
            # info.get('ytdReturn') is sometimes available for ETFs, or '52WeekChange' for stocks
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

        # Sort by best daily performer
        data.sort(key=lambda x: x['daily_change'], reverse=True)
        return data

    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching copycat data: {error_msg}")
        
        # Check if it's a rate limit error
        if "rate" in error_msg.lower() or "too many" in error_msg.lower():
            return {
                "error": "Rate Limited",
                "message": "Too many requests to Yahoo Finance. Please wait 5-10 minutes and try again.",
                "data": []
            }
        
        return {
            "error": "Data Fetch Error", 
            "message": f"Unable to fetch data: {error_msg}",
            "data": []
        }
