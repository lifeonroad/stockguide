"""
Economic Indicators Module
Fetches key macroeconomic data from FRED (St. Louis Fed) API.
"""

import os
import requests
from datetime import datetime, timedelta
from cache_utils import timed_cache, fetch_with_retry


@timed_cache(ttl_seconds=86400, soft_ttl_seconds=43200)  # 24h hard, 12h soft (SWR)
def get_economic_indicators():
    """
    Fetches key economic indicators from FRED API.
    
    Returns dict with:
    - Unemployment Rate (UNRATE)
    - CPI / Inflation (CPIAUCSL)
    - Fed Funds Rate (DFF)
    - GDP Growth (GDP)
    """
    
    api_key = os.getenv('FRED_API_KEY')
    
    # If no API key, return mock data for demo
    if not api_key:
        return get_fallback_indicators()
    
    indicators = {}
    
    # Define series to fetch
    series_map = {
        'unemployment': 'UNRATE',
        'inflation': 'CPIAUCSL',
        'fed_rate': 'DFF',
        'gdp_growth': 'GDP'
    }
    
    for name, series_id in series_map.items():
        try:
            data = fetch_fred_series(api_key, series_id, limit=12)  # Last 12 months
            if data:
                indicators[name] = parse_indicator_data(data, name)
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            indicators[name] = get_fallback_indicator(name)
    
    return {
        'indicators': indicators,
        'last_updated': datetime.now().isoformat(),
        'source': 'FRED API' if api_key else 'Static Demo Data'
    }


def fetch_fred_series(api_key: str, series_id: str, limit: int = 12):
    """Fetch time series data from FRED API."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': limit
    }
    
    response = fetch_with_retry(
        lambda: requests.get(url, params=params, timeout=10),
        max_attempts=3,
        base_delay=2.0,
    )
    response.raise_for_status()
    data = response.json()
    
    if 'observations' in data and len(data['observations']) > 0:
        return data['observations']
    return None


def parse_indicator_data(observations: list, indicator_name: str):
    """Parse FRED observations into indicator metrics."""
    if not observations or len(observations) < 2:
        return get_fallback_indicator(indicator_name)
    
    # Latest value
    latest = observations[0]
    current_value = float(latest['value'])
    
    # Previous month
    prev_month = observations[1] if len(observations) > 1 else latest
    prev_value = float(prev_month['value'])
    
    # Year ago (12 months back)
    year_ago = observations[11] if len(observations) >= 12 else prev_month
    year_ago_value = float(year_ago['value'])
    
    # Calculate changes
    month_change = current_value - prev_value
    year_change = current_value - year_ago_value
    
    # Determine trend
    trend = '→'
    if abs(month_change) > 0.1:
        trend = '↑' if month_change > 0 else '↓'
    
    return {
        'value': round(current_value, 2),
        'month_change': round(month_change, 2),
        'year_change': round(year_change, 2),
        'trend': trend,
        'date': latest['date']
    }


def get_fallback_indicator(name: str):
    """Return static demo data when FRED API unavailable."""
    defaults = {
        'unemployment': {'value': 4.1, 'month_change': -0.1, 'year_change': -0.3, 'trend': '↓'},
        'inflation': {'value': 3.2, 'month_change': 0.1, 'year_change': -1.8, 'trend': '↓'},
        'fed_rate': {'value': 5.33, 'month_change': 0.0, 'year_change': 0.75, 'trend': '→'},
        'gdp_growth': {'value': 2.8, 'month_change': 0.3, 'year_change': 0.5, 'trend': '↑'}
    }
    
    data = defaults.get(name, {'value': 0, 'month_change': 0, 'year_change': 0, 'trend': '→'})
    data['date'] = datetime.now().strftime('%Y-%m-%d')
    return data


def get_fallback_indicators():
    """Return full static dataset when no API key."""
    return {
        'indicators': {
            'unemployment': get_fallback_indicator('unemployment'),
            'inflation': get_fallback_indicator('inflation'),
            'fed_rate': get_fallback_indicator('fed_rate'),
            'gdp_growth': get_fallback_indicator('gdp_growth')
        },
        'last_updated': datetime.now().isoformat(),
        'source': 'Static Demo Data (Set FRED_API_KEY for live data)'
    }
