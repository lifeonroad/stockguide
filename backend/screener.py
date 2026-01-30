
import yfinance as yf
import pandas as pd
import random

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
# Fetching all stocks is too slow for yfinance without caching/batching
SECTOR_STOCKS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "ADBE", "CSCO", "CRM"],
    "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "C"],
    "Healthcare": ["LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "PFE", "AMGN"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG"],
    "Industrials": ["CAT", "UNP", "GE", "HON", "DE", "UPS", "LMT", "BA"],
    "Consumer Staples": ["PG", "COST", "PEP", "KO", "WMT", "PM", "MO", "CL"],
    "Materials": ["LIN", "SHW", "FCX", "APD", "ECL", "NEM", "DOW", "DD"],
    "Utilities": ["NEE", "DUK", "SO", "AEP", "SRE", "D", "EXC", "PEG"],
    "Real Estate": ["PLD", "AMT", "EQIX", "CCI", "PSA", "O", "VICI", "DLR"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "CMCSA", "VZ", "T"]
}

def get_industry_rankings():
    """
    Analyzes Sector ETFs to find the most 'Undervalued' and 'High Quality'.
    Note: ETF 'info' in yfinance often contains aggregate PE, Yield, etc.
    """
    results = []
    
    for sector, ticker_symbol in SECTOR_ETFS.items():
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Extract metrics (fallback to 0 or estimates if missing)
        # Note: ETF fields can be different from Stock fields
        pe = info.get('trailingPE') or info.get('forwardPE') or 20
        # PriceToSales is not always directly on ETF info, sometimes yield is better proxy for 'value' in sectors? 
        # We will iterate through a few stocks to get a better sector average if ETF data is sparse.
        
        # Let's try to be simple for MVP:
        # Use whatever ETF info we have.
        
        # Mocking or Approximate Logic if explicit aggregate fields missing:
        # We prioritize: PE, Yield.
        div_yield = info.get('yield', 0) or info.get('trailingAnnualDividendYield', 0)
        
        # Quality Proxy: ROE is hard to get for an ETF directly.
        # We will simulate "Screener" logic by picking top 3 stocks and averaging.
        
        results.append({
            "industry": sector,
            "etf": ticker_symbol,
            "pe": round(pe, 2),
            "dividend_yield": round(div_yield * 100, 2) if div_yield else 0,
            # Placeholder for calculated aggregate metrics
            "roe": 0, 
            "debt_to_equity": 0
        })

    # Sort by 'Value' (Low PE) for now
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
        i = t.info
        
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
