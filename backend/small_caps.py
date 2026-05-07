import asyncio
import logging
import yfinance as yf
from typing import List, Dict, Any, Optional
from datetime import datetime
from cache_utils import timed_cache, sanitize_metric
from dynamic_universe import _bulk_fundamentals, _bulk_momentum

logger = logging.getLogger(__name__)

# Representative list of Small-Cap / Mid-Cap candidates to screen for "Gems"
# These are often Russell 2000 components or high-growth small caps.
SMALL_CAP_CANDIDATES = [
    "ASGN", "AMN", "SGRY", "ENSG", "STAA", "NEOG", "VCYT", "SHLS", # Healthcare/Tech
    "NOVT", "COHR", "ONTO", "AEIS", "CLBT", "PRFT", "SPSC", "ALTR", # Tech
    "CALX", "EBIX", "BLKB", "PRO", "RAMP", "QMCO", "AOUT", "SWBI", # Tech/Cons
    "UPST", "AFRM", "SOFI", "LC", "DKNG", "PENN", "WYNN", "CZP",   # Fintech/Ent
    "RUN", "SUNW", "BE", "FCEL", "FSLR", "CSIQ", "NOVA", "SPWR",   # Energy
    "CHPT", "BLNK", "EVGO", "QS", "RIVN", "LCID", "FSR", "NKLA",   # EV (Risky)
    "CELH", "UTZ", "BRBR", "FRPT", "ELF", "SKIN", "BOOT", "CROX",  # Growth Cons
    "WING", "LOCO", "SHAK", "TXRH", "CAKE", "BJ", "SFM", "GO",     # Food/Retail
    "HDSN", "AAON", "FIX", "VMI", "TNC", "ACM", "KBR", "EME",      # Industrials
    "RH", "W", "RVLV", "FIGS", "DASH", "CART", "INST", "COUR",     # Ecommerce/Ed
    "MTCH", "BMBL", "GRPN", "IAC", "ANGI", "LQDT", "YELP", "ZD",   # Internet
    "AA", "CENX", "ATI", "HWM", "X", "CLF", "STLD", "NUE"         # Materials (Small/Mid)
]

# Add some explicitly identified small caps from Russell 2000 top holdings/trending
SMALL_CAP_CANDIDATES += [
    "VTEX", "FLYR", "PAY", "PRCT", "SMCI", "VRT", "POWI", "SIMO",
    "GPRO", "FITB", "HBAN", "ONB", "ZION", "BOKF", "CADE", "HWC"
]

@timed_cache(ttl_seconds=14400, soft_ttl_seconds=10800) # 4h hard, 3h soft (SWR)
def get_small_cap_gems(min_growth: float = 0.05, max_pe: float = 25.0, min_roe: float = 0.10):
    """
    Screens for Small-Cap Gems: consistent growth + undervaluation.
    """
    candidates = list(set(SMALL_CAP_CANDIDATES))
    
    # Use bulk fetchers from dynamic_universe for speed
    fund_map = _bulk_fundamentals(candidates)
    
    gems = []
    
    for symbol in candidates:
        try:
            fd = fund_map.get(symbol)
            if not fd:
                continue
            
            mkt_cap = fd.get("market_cap", 0)
            avg_vol = fd.get("avg_volume", 0)
            roe = fd.get("roe", 0)
            eps = fd.get("eps", 0)
            sector = fd.get("sector", "Unknown")
            
            # 1. Market Cap Filter ($300M - $3B)
            if not (3e8 <= mkt_cap <= 3e9):
                continue
                
            # 2. Liquidity Filter (> 100k avg volume)
            if avg_vol < 100000:
                continue
            
            # 3. Quality/ROE Filter (Dynamic)
            if roe < min_roe or eps <= 0:
                continue
            
            # 4. Fetch deeper metrics for filtered subset
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            forward_pe = info.get('forwardPE') or info.get('trailingPE') or 0
            price_to_book = info.get('priceToBook') or 0
            rev_growth = sanitize_metric(info.get('revenueGrowth'), 0)
            
            # 5. Value Filtering (Dynamic)
            if forward_pe <= 0 or forward_pe > max_pe:
                continue
            if price_to_book <= 0 or price_to_book > 3.0:
                continue
                
            # 6. Growth Filter (Dynamic)
            if rev_growth < min_growth:
                continue
            
            # Calculate Gem Score (0-100)
            growth_score = min(rev_growth * 200, 40)
            value_score = max(0.0, (30.0 - (forward_pe / max_pe) * 30.0)) if max_pe > 0 else 0.0
            quality_score = min(roe * 100, 30)
            
            gem_score = round(growth_score + value_score + quality_score)
            
            gems.append({
                "symbol": symbol,
                "name": info.get('shortName', symbol),
                "sector": sector,
                "price": round(info.get('currentPrice', 0), 2),
                "market_cap": round(mkt_cap / 1e6, 2),
                "pe": round(forward_pe, 2),
                "pb": round(price_to_book, 2),
                "roe": round(roe * 100, 2),
                "rev_growth": round(rev_growth * 100, 2),
                "gem_score": gem_score,
                "sentiment": "Strong Gem" if gem_score > 75 else "Potential Gem",
                "desc": info.get('longBusinessSummary')[:150] + "..." if info.get('longBusinessSummary') else "Small-cap opportunity."
            })
            
        except Exception as e:
            logger.warning("Error screening small cap %s: %s", symbol, e)
            continue
    
    gems.sort(key=lambda x: x['gem_score'], reverse=True)
    
    return {
        "data": gems,
        "last_updated": datetime.now().isoformat(),
        "notes": [
            f"Filtered for Revenue Growth > {min_growth*100}% and P/E < {max_pe}.",
            f"Quality check: ROE > {min_roe*100}% and positive EPS required.",
            "Market Cap restricted to $300M - $3B range for pure small-cap focus."
        ]
    }

if __name__ == "__main__":
    # Test
    import time
    start = time.time()
    data = get_small_cap_gems()
    print(f"Fetch took {time.time() - start:.2f}s")
    print(f"Found {len(data['data'])} gems")
    for gem in data['data'][:5]:
        print(f"{gem['symbol']}: Score {gem['gem_score']} | PE {gem['pe']} | Growth {gem['rev_growth']}%")
