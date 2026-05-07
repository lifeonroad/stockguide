
import yfinance as yf
import pandas as pd
from cache_utils import timed_cache, fetch_with_retry

@timed_cache(ttl_seconds=1800, soft_ttl_seconds=1200)  # 30m hard, 20m soft (SWR)
def analyze_stock_buffett(symbol):
    """
    Analyzes a single stock using Warren Buffett's core principles:
    1. Consistent Earnings (Proxy: Positive EPS history)
    2. High ROE (Quality)
    3. Low Debt (Safety)
    4. Fair Valuation (Margin of Safety)
    """
    ticker = yf.Ticker(symbol)
    try:
        info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3, base_delay=2.0)
    except Exception:
        return {"error": "Symbol not found or data unavailable."}

    # 1. Gather Metrics
    price = info.get('currentPrice', 0)
    eps_ttm = info.get('trailingEps', 0)
    pe_ratio = info.get('trailingPE', info.get('forwardPE', 0))
    roe = info.get('returnOnEquity', 0) # decimal
    debt_to_equity = info.get('debtToEquity', 0) # typically returns percentage in yfinance, e.g. 150 for 1.5 ratio? check docs. 
    # yfinance usually returns DebtToEquity as a ratio * 100 or just a huge number? 
    # Actually yfinance info 'debtToEquity' is typically Total Debt / Total Equity * 100. So 50 = 0.5.
    
    payout_ratio = info.get('payoutRatio', 0) # decimal
    
    # 2. Forecasting Logic (The "Crystal Ball")
    # Retention Ratio = 1 - Payout
    # Sustainable Growth Rate (SGR) = ROE * Retention Ratio
    if payout_ratio is None: payout_ratio = 0
    if roe is None: roe = 0
    if eps_ttm is None: eps_ttm = 0
    
    retention_ratio = 1 - payout_ratio
    projected_growth_rate = roe * retention_ratio
    
    # Cap growth for realism (Buffett rarely projects > 15% long term for big caps)
    projected_growth_rate = min(projected_growth_rate, 0.15) 
    # If negative (losing money), growth is 0 for valuation safety
    projected_growth_rate = max(projected_growth_rate, 0)

    # 5-Year Projection
    # Future EPS = EPS * (1 + g)^5
    future_eps = eps_ttm * ((1 + projected_growth_rate) ** 5)
    
    # Terminal Valuation
    # Assume stock trades at its average historical PE or a conservative 15 (Buffett default)
    # We will use the lower of current PE or 20 to be safe, but at least 10.
    termina_pe = min(max(pe_ratio, 10), 25) 
    
    future_price = future_eps * termina_pe
    
    # Intrinsic Value (Discounted back to today at 10% Hurdle Rate)
    # IV = Future Price / (1.10)^5
    hurdle_rate = 0.10
    intrinsic_value = future_price / ((1 + hurdle_rate) ** 5)
    
    # Margin of Safety
    margin_of_safety = (intrinsic_value - price) / price if price > 0 else 0
    
    # 3. Generating "Practical Reasons"
    reasons = []
    score = 0
    
    # --- Macro Context Integration ---
    try:
        from macro import get_macro_trends, SECTOR_MAP
        macro_data = get_macro_trends()
        stock_sector = info.get('sector', 'Unknown')
        
        if stock_sector in macro_data['sector_impacts']:
             matched_impact = macro_data['sector_impacts'][stock_sector]
        else:
            # Fallback Fuzzy Match
            for key in macro_data['sector_impacts'].keys():
                if key.lower() in stock_sector.lower():
                    matched_impact = macro_data['sector_impacts'][key]
                    break
            else:
                matched_impact = None
        
        if matched_impact:
            direction = matched_impact.get('impact', 'Neutral')
            macro_reasons = matched_impact.get('reasons', [])
            
            if direction == 'Tailwind':
                score += 1
                reasons.append(f"🚀 Macro Tailwind: {stock_sector} benefiting from {', '.join(macro_reasons).lower()}.")
            elif direction == 'Headwind':
                score -= 1
                reasons.append(f"🌬️ Macro Headwind: {stock_sector} facing pressure from {', '.join(macro_reasons).lower()}.")
            else:
                 reasons.append(f"⚖️ Macro Neutral: {stock_sector} is relatively stable in current conditions.")
    except Exception as e:
        print(f"Macro integration error: {e}")

    # ROE Check
    if roe > 0.15:
        reasons.append(f"✅ High ROE of {round(roe*100, 1)}% suggests a durable competitive advantage (Moat).")
        score += 1
    elif roe > 0.10:
        reasons.append(f"⚠️ Moderate ROE of {round(roe*100, 1)}%. Business is decent but not exceptional.")
    else:
        reasons.append(f"❌ Low ROE of {round(roe*100, 1)}% indicates capital inefficiency.")
        score -= 1

    # Debt Check
    if debt_to_equity < 50: # < 0.5 ratio
        reasons.append("✅ Conservative financing (Debt/Equity < 0.5). Low risk of bankruptcy.")
        score += 1
    elif debt_to_equity < 100:
        reasons.append("⚠️ Moderate leverage. Acceptable for stable industries.")
    else:
        reasons.append("❌ High debt load. Interest payments may eat into profits during downturns.")
        score -= 1
        
    # Valuation Check
    if price < intrinsic_value:
        reasons.append(f"✅ Undervalued. Trading at a {round(margin_of_safety * 100, 1)}% discount to estimated intrinsic value.")
        score += 2
    elif price < intrinsic_value * 1.1:
        reasons.append("⚠️ Fairly Valued. Price matches economic reality.")
    else:
        reasons.append("❌ Overvalued. Market price implies growth that may not materialize.")
        score -= 1
        
    # Rating
    if score >= 4: # Higher bar with macro bonus
        rating = "STRONG BUY"
        verdict_color = "text-warren-success"
    elif score >= 2:
        rating = "BUY"
        verdict_color = "text-warren-success"
    elif score >= 0:
        rating = "HOLD"
        verdict_color = "text-warren-warning"
    else:
        rating = "AVOID / SELL"
        verdict_color = "text-warren-danger"

    return {
        "symbol": symbol.upper(),
        "name": info.get('shortName', symbol),
        "sector": info.get('sector', 'Unknown'),
        "current_price": round(price, 2),
        "intrinsic_value": round(intrinsic_value, 2),
        "target_price_5yr": round(future_price, 2),
        "projected_growth_rate": round(projected_growth_rate * 100, 1),
        "rating": rating,
        "score": score,
        "reasons": reasons,
        "metrics": {
            "roe": round(roe * 100, 2),
            "pe": round(pe_ratio, 2) if pe_ratio else 0,
            "eps": round(eps_ttm, 2),
            "debt_to_equity": round(debt_to_equity, 2)
        }
    }
