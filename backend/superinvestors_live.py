"""
Live 13F Data Fetcher
Fetches real-time hedge fund holdings from Financial Modeling Prep API.
Falls back to static data if API is unavailable.

Caching strategy — filing-aware:
- Outside filing window: 30-day cache (data is completely static)
- Inside filing window (45 days after quarter end): 6-hour cache
- Day of deadline: 1-hour cache (checking aggressively)
- Post-deadline stragglers (15 days): 1-hour cache

See filing_calendar.py for the schedule logic.
"""

import os
import time
import requests
from datetime import datetime, date
from superinvestors import get_superinvestors as get_static_superinvestors
from filing_calendar import get_filing_status, filing_aware_ttl

# CIK codes for our tracked investors
INVESTOR_CIKS = {
    "buffett": "0001067983",  # Berkshire Hathaway
    "burry": "0001649339",    # Scion Asset Management
    "druckenmiller": "0001536411",  # Duquesne Family Office
    "pabrai": "0001336528"    # Dalal Street LLC
}

# ──────────────────────────────────────────────────────────
# Manual cache (filing-aware TTL)
# ──────────────────────────────────────────────────────────
_13F_CACHE = {
    "result": None,
    "expiry": 0.0,
    "last_good": None,
    "cached_quarter": None,  # tracks which quarter the cached data covers
}


def _cache_valid():
    """Check if the current cache entry is still valid."""
    if _13F_CACHE["result"] is None:
        return False
    if time.time() > _13F_CACHE["expiry"]:
        return False
    return True


def _set_cache(result, ttl_seconds):
    """Store result in cache with the given TTL."""
    filing_status = get_filing_status()
    _13F_CACHE["result"] = result
    _13F_CACHE["expiry"] = time.time() + ttl_seconds
    _13F_CACHE["last_good"] = result
    _13F_CACHE["cached_quarter"] = filing_status["data_through_quarter"]


def _get_cached_or_fetch():
    """
    Return cached 13F data if valid, otherwise fetch fresh with filing-aware TTL.
    """
    if _cache_valid():
        return _13F_CACHE["result"]

    ttl = filing_aware_ttl()
    data = _fetch_all_investors()

    if data:
        _set_cache(data, ttl)
    elif _13F_CACHE["last_good"] is not None:
        # API failed — return stale data briefly
        return _13F_CACHE["last_good"]

    return data


def _fetch_all_investors():
    """Fetch 13F data for all tracked investors."""
    api_key = os.getenv('FMP_API_KEY')

    if not api_key:
        return None

    static_fallback = get_static_superinvestors()
    live_data = []

    for investor_id, cik in INVESTOR_CIKS.items():
        holdings = _fetch_13f_holdings(cik, api_key)

        if holdings:
            static_investor = next((inv for inv in static_fallback if inv['id'] == investor_id), None)
            if static_investor:
                parsed = _parse_13f_to_format(holdings, investor_id, static_investor['name'])
                if parsed:
                    parsed['firm'] = static_investor['firm']
                    parsed['style'] = static_investor['style']
                    live_data.append(parsed)
                else:
                    live_data.append(static_investor)
            else:
                live_data.append(static_investor)
        else:
            static_investor = next((inv for inv in static_fallback if inv['id'] == investor_id), None)
            if static_investor:
                live_data.append(static_investor)

    return live_data if live_data else static_fallback


def get_next_filing_info():
    """
    Returns information about the next 13F filing deadline.
    Delegates to filing_calendar for accurate schedule logic.
    """
    status = get_filing_status()
    days_remaining = status["days_until_deadline"]

    if days_remaining is not None:
        if days_remaining < 0:
            filing_status_text = "Filing window recently closed"
        elif days_remaining == 0:
            filing_status_text = "Filings are due TODAY!"
        elif days_remaining <= 7:
            filing_status_text = f"Filings due in {days_remaining} days (Active Window)"
        else:
            filing_status_text = f"Next major update: {status['next_deadline']}"
    else:
        days_remaining = status.get("days_until_window")
        if days_remaining is not None:
            filing_status_text = f"Next filing window opens in {days_remaining} days"
        else:
            filing_status_text = status["badge"]

    return {
        "status": filing_status_text,
        "quarter": status["next_filing_quarter"] or "Unknown",
        "deadline": status["next_deadline"],
        "days_remaining": days_remaining,
    }


def _fetch_13f_holdings(cik, api_key):
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


def _parse_13f_to_format(holdings_data, investor_id, investor_name):
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
    Uses filing-aware caching: 30-day cache outside filing window,
    6-hour cache inside filing window.
    Falls back to static data if API key is missing or fetch fails.
    """
    api_key = os.getenv('FMP_API_KEY')

    if not api_key:
        print("FMP_API_KEY not found, using static data")
        return get_static_superinvestors()

    data = _get_cached_or_fetch()
    return data if data else get_static_superinvestors()


if __name__ == "__main__":
    # Test the fetcher
    print("Testing Live 13F Fetcher...")
    status = get_filing_status()
    print(f"Filing status: {status['badge']}")
    print(f"Cache TTL: {status['cache_ttl_seconds']}s ({status['cache_ttl_seconds'] / 3600:.1f}h)")
    print(f"Filing window open: {status['filing_window_open']}")
    print()
    data = get_live_superinvestors()
    print(f"Fetched data for {len(data)} investors")
