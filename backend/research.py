
import asyncio
import yfinance as yf
from analyst import BuffettStrategy, BurryStrategy, LynchStrategy
from cache_utils import timed_cache, fetch_with_retry
import math

@timed_cache(ttl_seconds=3600)
def get_comprehensive_research(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol)
    
    try:
        # 1. Fetch Core Info
        info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3)
        if not info or 'symbol' not in info:
            return {"error": f"Symbol {symbol} not found."}
            
        # 2. Run Analyst Brains
        buffett = BuffettStrategy(symbol).run()
        burry = BurryStrategy(symbol).run()
        lynch = LynchStrategy(symbol).run()
        
        # 3. Deep Fundatmentals
        price = info.get('currentPrice', 0)
        mkt_cap = info.get('marketCap', 0)
        forward_pe = info.get('forwardPE', 0)
        trailing_pe = info.get('trailingPE', 0)
        ps = info.get('priceToSalesTrailing12Months', 0)
        pb = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0)
        roa = info.get('returnOnAssets', 0)
        fcf = info.get('freeCashflow', 0)
        total_debt = info.get('totalDebt', 0)
        cash = info.get('totalCash', 0)
        
        # 4. Reality Check (Reverse DCF)
        # Using 9% hurdle rate
        eps = info.get('trailingEps', 0)
        implied_g = 0
        if price > 0 and eps > 0:
            numerator = (price * 0.09) - eps
            denominator = price + eps
            implied_g = (numerator / denominator) * 100
            
        # 5. Moat Assessment
        moat_score = 0
        moat_reasons = []
        if roe > 0.20:
             moat_score += 40
             moat_reasons.append("High ROE suggests established pricing power.")
        if roa > 0.10:
             moat_score += 20
             moat_reasons.append("Efficient asset utilization.")
        if fcf > 0:
             moat_score += 20
             moat_reasons.append("Self-funding operations (Positive FCF).")
        if (total_debt / (cash + 1)) < 2:
             moat_score += 20
             moat_reasons.append("Strong balance sheet minimizes disruption risk.")
             
        moat_rating = "None"
        if moat_score >= 80: moat_rating = "Wide Moat"
        elif moat_score >= 50: moat_rating = "Narrow Moat"
        else: moat_rating = "Speculative / Weak"

        # 6. Comparison vs S&P 500 (Proxied)
        # S&P Avg PE ~ 20-25, RoE ~ 15%
        rel_pe = (trailing_pe / 22.0) if trailing_pe else 0
        rel_roe = (roe / 0.15) if roe else 0

        return {
            "symbol": symbol,
            "name": info.get('longName', info.get('shortName', symbol)),
            "summary": info.get('longBusinessSummary', "No summary available."),
            "sector": info.get('sector', 'Unknown'),
            "industry": info.get('industry', 'Unknown'),
            "market_data": {
                "price": price,
                "mkt_cap": mkt_cap,
                "change_pct": info.get('regularMarketChangePercent', 0)
            },
            "analysts": {
                "buffett": {
                    "rating": buffett.get('rating'),
                    "score": buffett.get('score'),
                    "verdict": buffett.get('reasons')[:3] # Top 3 reasons
                },
                "burry": {
                    "rating": burry.get('rating'),
                    "score": burry.get('score'),
                    "verdict": burry.get('reasons')[:3]
                },
                "lynch": {
                    "rating": lynch.get('rating'),
                    "score": lynch.get('score'),
                    "verdict": lynch.get('reasons')[:3]
                }
            },
            "growth": {
                "rev_growth": info.get('revenueGrowth', 0) * 100,
                "eps_growth": info.get('earningsGrowth', 0) * 100,
                "implied_growth": round(implied_g, 1),
                "projected_5yr": buffett.get('projected_growth_rate', 0)
            },
            "valuation_scorecard": {
                "trailing_pe": trailing_pe,
                "forward_pe": forward_pe,
                "ps": ps,
                "pb": pb,
                "fcf_yield": (fcf / mkt_cap * 100) if mkt_cap else 0
            },
            "quality_scorecard": {
                "roe": roe * 100,
                "roa": roa * 100,
                "debt_to_equity": info.get('debtToEquity', 0),
                "current_ratio": info.get('currentRatio', 0)
            },
            "moat": {
                "rating": moat_rating,
                "score": moat_score,
                "reasons": moat_reasons
            },
            "efficiency": {
                "rel_pe": round(rel_pe, 2),
                "rel_roe": round(rel_roe, 2)
            }
        }
    except Exception as e:
        return {"error": f"Research failed: {str(e)}"}
