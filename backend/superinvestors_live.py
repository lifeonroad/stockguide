"""
Live 13F Data Fetcher
Fetches real-time hedge fund holdings from Financial Modeling Prep API.
Falls back to static data if API is unavailable.
"""

import os
import requests
from superinvestors import get_superinvestors as get_static_superinvestors

from datetime import datetime, date, timedelta
from superinvestors import get_superinvestors as get_static_superinvestors

# CIK codes for our tracked investors
INVESTOR_CIKS = {
    "buffett": "0001067983",  # Berkshire Hathaway
    "burry": "0001649339",    # Scion Asset Management
    "druckenmiller": "0001536411",  # Duquesne Family Office
    "pabrai": "0001336528"    # Dalal Street LLC
}

def get_next_filing_info():
    """
    Returns information about the next 13F filing deadline.
    Deadlines are 45 days after each calendar quarter end.
    """
    today = date.today()
    year = today.year
    
    # Filing deadlines (roughly Feb 14, May 15, Aug 14, Nov 14)
    deadlines = [
        (date(year, 2, 14), "Q4 (prev year)"),
        (date(year, 5, 15), "Q1"),
        (date(year, 8, 14), "Q2"),
        (date(year, 11, 14), "Q3"),
        (date(year + 1, 2, 14), "Q4") # Next year transition
    ]
    
    next_deadline = None
    quarter_name = ""
    
    for d, q in deadlines:
        if d >= today:
            next_deadline = d
            quarter_name = q
            break
            
    if not next_deadline:
        # Fallback if somehow missed all
        next_deadline = date(year + 1, 2, 14)
        quarter_name = "Q4"

    days_left = (next_deadline - today).days
    
    if days_left < 0:
        status = "Filing window recently closed"
    elif days_left == 0:
        status = "Filings are due TODAY!"
    elif days_left <= 7:
        status = f"Filings due in {days_left} days (Active Window)"
    else:
        status = f"Next major update: {next_deadline.strftime('%b %d, %Y')}"
        
    return {
        "status": status,
        "quarter": quarter_name,
        "deadline": next_deadline.isoformat(),
        "days_remaining": days_left
    }

def fetch_13f_holdings(cik, api_key):
    """
    Fetch latest 13F holdings for a given CIK.
    Returns list of holdings or None if fetch fails.
    """
    try:
        url = f"https://financialmodelingprep.com/api/v3/form-thirteen/{cik}"
        params = {'apikey': api_key}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data
    except Exception as e:
        print(f"Error fetching 13F for CIK {cik}: {e}")
    
    return None

def parse_13f_to_format(holdings_data, investor_id, investor_name):
    """
    Convert FMP 13F data to our internal format.
    """
    if not holdings_data or len(holdings_data) == 0:
        return None
    
    # Group by quarter
    quarters = {}
    for holding in holdings_data[:50]:  # Limit to recent data
        quarter = holding.get('date', 'Unknown')[:7]  # YYYY-MM format
        
        if quarter not in quarters:
            quarters[quarter] = {
                'buys': [],
                'sells': [],
                'holdings': []
            }
        
        # Simplified: just track holdings
        quarters[quarter]['holdings'].append({
            'symbol': holding.get('cusip', ''),
            'name': holding.get('nameOfIssuer', ''),
            'shares': holding.get('shares', 0),
            'value': holding.get('value', 0)
        })
    
    # Format for our UI (simplified version)
    return {
        "id": investor_id,
        "name": investor_name,
        "firm": "Live Data",
        "style": "Dynamic",
        "history": [
            {
                "quarter": q,
                "summary": f"{len(data['holdings'])} holdings tracked",
                "top_buys": [],
                "top_sells": [],
                "weirdest_bet": None
            }
            for q, data in list(quarters.items())[:3]
        ]
    }

def get_live_superinvestors():
    """
    Fetch live 13F data for all tracked investors.
    Falls back to static data if API key is missing or fetch fails.
    """
    api_key = os.getenv('FMP_API_KEY')
    
    if not api_key:
        print("FMP_API_KEY not found, using static data")
        return get_static_superinvestors()
    
    live_data = []
    static_fallback = get_static_superinvestors()
    
    for investor_id, cik in INVESTOR_CIKS.items():
        holdings = fetch_13f_holdings(cik, api_key)
        
        if holdings:
            # Find matching static investor for metadata
            static_investor = next((inv for inv in static_fallback if inv['id'] == investor_id), None)
            if static_investor:
                parsed = parse_13f_to_format(holdings, investor_id, static_investor['name'])
                if parsed:
                    # Merge: use live holdings but keep static metadata
                    parsed['firm'] = static_investor['firm']
                    parsed['style'] = static_investor['style']
                    live_data.append(parsed)
                else:
                    live_data.append(static_investor)
            else:
                live_data.append(static_investor)
        else:
            # Fallback to static for this investor
            static_investor = next((inv for inv in static_fallback if inv['id'] == investor_id), None)
            if static_investor:
                live_data.append(static_investor)
    
    return live_data if live_data else static_fallback

if __name__ == "__main__":
    # Test the fetcher
    print("Testing Live 13F Fetcher...")
    data = get_live_superinvestors()
    print(f"Fetched data for {len(data)} investors")
