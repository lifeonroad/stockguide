
import yfinance as yf
from analyst import BuffettStrategy, BurryStrategy, LynchStrategy
from cache_utils import timed_cache, fetch_with_retry

def safe_float(value, default=0.0):
    """Safely coerce a value to float, returning default if None or invalid."""
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default

def safe_list(value, n=3):
    """Return first n items of a list, or empty list if None."""
    if isinstance(value, list):
        return value[:n]
    return []

@timed_cache(ttl_seconds=3600)
def get_comprehensive_research(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol)

    try:
        # 1. Fetch Core Info
        info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3)
        if not info or 'symbol' not in info:
            return {"error": f"Symbol {symbol} not found or no data available."}

        # 2. Run Analyst Brains
        buffett = BuffettStrategy(symbol).run() or {}
        burry = BurryStrategy(symbol).run() or {}
        lynch = LynchStrategy(symbol).run() or {}

        # 3. Deep Fundamentals (all safe_float to handle None from yfinance)
        price     = safe_float(info.get('currentPrice'))
        mkt_cap   = safe_float(info.get('marketCap'))
        forward_pe = safe_float(info.get('forwardPE'))
        trailing_pe = safe_float(info.get('trailingPE'))
        ps        = safe_float(info.get('priceToSalesTrailing12Months'))
        pb        = safe_float(info.get('priceToBook'))
        roe       = safe_float(info.get('returnOnEquity'))
        roa       = safe_float(info.get('returnOnAssets'))
        fcf       = safe_float(info.get('freeCashflow'))
        total_debt = safe_float(info.get('totalDebt'))
        cash      = safe_float(info.get('totalCash'))
        eps       = safe_float(info.get('trailingEps'))
        rev_growth = safe_float(info.get('revenueGrowth'))
        eps_growth = safe_float(info.get('earningsGrowth'))
        change_pct = safe_float(info.get('regularMarketChangePercent'))
        debt_to_equity = safe_float(info.get('debtToEquity'))
        current_ratio  = safe_float(info.get('currentRatio'))

        # 4. Reality Check (Reverse DCF) — 9% hurdle rate
        implied_g = 0.0
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
        if cash > 0 and (total_debt / (cash + 1)) < 2:
            moat_score += 20
            moat_reasons.append("Strong balance sheet minimizes disruption risk.")

        if not moat_reasons:
            moat_reasons.append("Insufficient data for moat analysis.")

        moat_rating = "Speculative / Weak"
        if moat_score >= 80:
            moat_rating = "Wide Moat"
        elif moat_score >= 50:
            moat_rating = "Narrow Moat"

        # 6. Relative vs S&P 500 proxies
        rel_pe  = round((trailing_pe / 22.0), 2) if trailing_pe else 0.0
        rel_roe = round((roe / 0.15), 2) if roe else 0.0

        fcf_yield = (fcf / mkt_cap * 100) if mkt_cap else 0.0

        return {
            "symbol": symbol,
            "name": info.get('longName') or info.get('shortName') or symbol,
            "summary": info.get('longBusinessSummary') or "No business summary available.",
            "sector": info.get('sector') or "Unknown",
            "industry": info.get('industry') or "Unknown",
            "market_data": {
                "price": price,
                "mkt_cap": mkt_cap,
                "change_pct": change_pct
            },
            "analysts": {
                "buffett": {
                    "rating": buffett.get('rating') or "N/A",
                    "score": safe_float(buffett.get('score')),
                    "verdict": safe_list(buffett.get('reasons'), 3)
                },
                "burry": {
                    "rating": burry.get('rating') or "N/A",
                    "score": safe_float(burry.get('score')),
                    "verdict": safe_list(burry.get('reasons'), 3)
                },
                "lynch": {
                    "rating": lynch.get('rating') or "N/A",
                    "score": safe_float(lynch.get('score')),
                    "verdict": safe_list(lynch.get('reasons'), 3)
                }
            },
            "growth": {
                "rev_growth": round(rev_growth * 100, 1),
                "eps_growth": round(eps_growth * 100, 1),
                "implied_growth": round(implied_g, 1),
                "projected_5yr": safe_float(buffett.get('projected_growth_rate'))
            },
            "valuation_scorecard": {
                "trailing_pe": trailing_pe,
                "forward_pe": forward_pe,
                "ps": ps,
                "pb": pb,
                "fcf_yield": round(fcf_yield, 2)
            },
            "quality_scorecard": {
                "roe": round(roe * 100, 2),
                "roa": round(roa * 100, 2),
                "debt_to_equity": debt_to_equity,
                "current_ratio": current_ratio
            },
            "moat": {
                "rating": moat_rating,
                "score": moat_score,
                "reasons": moat_reasons
            },
            "efficiency": {
                "rel_pe": rel_pe,
                "rel_roe": rel_roe
            }
        }

    except Exception as e:
        return {"error": f"Research failed: {str(e)}"}
