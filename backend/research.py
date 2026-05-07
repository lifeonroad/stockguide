
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

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=2700)  # 1h hard, 45m soft (SWR)
def get_comprehensive_research(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol)

    try:
        # 1. Fetch Core Info
        info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=3)
        if not info or 'symbol' not in info:
            raise ValueError(f"Symbol {symbol} not found or no data available.")

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
        book_value = safe_float(info.get('bookValue'))
        dividend_rate = safe_float(info.get('dividendRate'))
        dividend_yield = safe_float(info.get('dividendYield'))
        payout_ratio = safe_float(info.get('payoutRatio'))
        shares_out = safe_float(info.get('sharesOutstanding'))
        op_cashflow = safe_float(info.get('operatingCashflow'))
        net_income = safe_float(info.get('netIncomeToCommon'))
        forward_eps = safe_float(info.get('forwardEps'))
        sector_name = info.get('sector') or 'Unknown'
        industry_name = info.get('industry') or 'Unknown'

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

        # ═══════════════════════════════════════════════════════
        # 7. INTRINSIC VALUE MODELS
        # ═══════════════════════════════════════════════════════
        import math

        valuation_models = []

        # --- Model 1: Graham Number ---
        # IV = sqrt(22.5 × EPS × Book Value)
        graham_iv = 0.0
        if eps > 0 and book_value > 0:
            graham_iv = round(math.sqrt(22.5 * eps * book_value), 2)
        graham_mos = round((1 - price / graham_iv) * 100, 1) if graham_iv > 0 and price > 0 else 0.0
        valuation_models.append({
            "name": "Graham Number",
            "method": "Defensive",
            "formula": "√(22.5 × EPS × Book Value)",
            "intrinsic_value": graham_iv,
            "margin_of_safety": graham_mos,
            "inputs": {"EPS": round(eps, 2), "Book Value": round(book_value, 2)},
            "verdict": "Undervalued" if graham_mos > 0 else "Overvalued"
        })

        # --- Model 2: DCF (Simplified 2-Stage) ---
        # Stage 1: 5 years at earnings growth rate
        # Stage 2: Terminal value at 3% perpetual growth, 10% discount
        dcf_iv = 0.0
        discount_rate = 0.10
        terminal_g = 0.03
        g1 = max(min(eps_growth, 0.30), 0.0)  # cap growth at 30%
        if eps > 0 and shares_out > 0:
            # Stage 1: project FCF (or net income) for 5 years
            base_cf = fcf if fcf > 0 else net_income
            if base_cf > 0:
                pv_stage1 = 0.0
                projected_cf = base_cf
                for yr in range(1, 6):
                    projected_cf *= (1 + g1)
                    pv_stage1 += projected_cf / ((1 + discount_rate) ** yr)
                # Terminal value
                terminal_cf = projected_cf * (1 + terminal_g)
                terminal_val = terminal_cf / (discount_rate - terminal_g)
                pv_terminal = terminal_val / ((1 + discount_rate) ** 5)
                enterprise_val = pv_stage1 + pv_terminal
                # Per-share: add cash, subtract debt
                equity_val = enterprise_val + cash - total_debt
                dcf_iv = round(max(equity_val / shares_out, 0), 2)
        dcf_mos = round((1 - price / dcf_iv) * 100, 1) if dcf_iv > 0 and price > 0 else 0.0
        valuation_models.append({
            "name": "DCF (2-Stage)",
            "method": "Intrinsic",
            "formula": "PV of 5yr projected FCF + Terminal Value",
            "intrinsic_value": dcf_iv,
            "margin_of_safety": dcf_mos,
            "inputs": {"Growth Rate": f"{round(g1*100,1)}%", "Discount Rate": "10%", "Terminal Growth": "3%"},
            "verdict": "Undervalued" if dcf_mos > 0 else "Overvalued"
        })

        # --- Model 3: Buffett Owner Earnings ---
        # Owner Earnings = Net Income + Depreciation - CapEx (approx: Operating CF)
        # Value = Owner Earnings / (Discount Rate - Growth Rate)
        owner_iv = 0.0
        owner_earnings = op_cashflow  # Best proxy available from yfinance
        stable_g = min(max(eps_growth, 0.02), 0.08)  # conservative 2-8%
        if owner_earnings > 0 and shares_out > 0 and discount_rate > stable_g:
            owner_val = owner_earnings / (discount_rate - stable_g)
            owner_equity = owner_val + cash - total_debt
            owner_iv = round(max(owner_equity / shares_out, 0), 2)
        owner_mos = round((1 - price / owner_iv) * 100, 1) if owner_iv > 0 and price > 0 else 0.0
        valuation_models.append({
            "name": "Owner Earnings",
            "method": "Buffett",
            "formula": "Operating CF / (Discount Rate − Growth)",
            "intrinsic_value": owner_iv,
            "margin_of_safety": owner_mos,
            "inputs": {"Op. Cash Flow": f"${op_cashflow/1e9:.1f}B" if op_cashflow > 1e9 else f"${op_cashflow/1e6:.0f}M", "Growth": f"{round(stable_g*100,1)}%"},
            "verdict": "Undervalued" if owner_mos > 0 else "Overvalued"
        })

        # --- Model 4: Gordon Growth (DDM) ---
        # IV = Dividend / (Required Return - Growth Rate)
        gordon_iv = 0.0
        required_return = 0.10
        div_growth = min(max(eps_growth, 0.02), 0.08)  # proxy dividend growth from earnings growth
        if dividend_rate > 0 and required_return > div_growth:
            gordon_iv = round(dividend_rate / (required_return - div_growth), 2)
        gordon_mos = round((1 - price / gordon_iv) * 100, 1) if gordon_iv > 0 and price > 0 else 0.0
        valuation_models.append({
            "name": "Gordon Growth (DDM)",
            "method": "Dividend",
            "formula": "Annual Dividend / (Required Return − Growth)",
            "intrinsic_value": gordon_iv,
            "margin_of_safety": gordon_mos,
            "inputs": {"Dividend": f"${dividend_rate:.2f}", "Required Return": "10%", "Div Growth": f"{round(div_growth*100,1)}%"},
            "verdict": "Undervalued" if gordon_mos > 0 else "Overvalued" if gordon_iv > 0 else "N/A (No Dividend)"
        })

        # --- Model 5: Multiples-Based Relative Valuation ---
        # Fair PE based on growth (PEG=1 implies fair PE = EPS Growth × 100)
        # Also compare to sector average (~22 for S&P)
        sector_avg_pe = 22.0  # S&P 500 historical average
        peg_fair_pe = max(eps_growth * 100, 10) if eps_growth > 0 else sector_avg_pe
        blended_fair_pe = round((peg_fair_pe + sector_avg_pe) / 2, 1)
        multiples_iv = round(blended_fair_pe * eps, 2) if eps > 0 else 0.0
        multiples_mos = round((1 - price / multiples_iv) * 100, 1) if multiples_iv > 0 and price > 0 else 0.0
        valuation_models.append({
            "name": "Relative Valuation",
            "method": "Multiples",
            "formula": "Blended Fair P/E × EPS",
            "intrinsic_value": multiples_iv,
            "margin_of_safety": multiples_mos,
            "inputs": {"Fair P/E": blended_fair_pe, "Current P/E": round(trailing_pe, 1), "EPS": round(eps, 2)},
            "verdict": "Undervalued" if multiples_mos > 0 else "Overvalued"
        })

        # Consensus intrinsic value (average of valid models)
        valid_ivs = [m['intrinsic_value'] for m in valuation_models if m['intrinsic_value'] > 0]
        consensus_iv = round(sum(valid_ivs) / len(valid_ivs), 2) if valid_ivs else 0.0
        consensus_mos = round((1 - price / consensus_iv) * 100, 1) if consensus_iv > 0 and price > 0 else 0.0

        return {
            "symbol": symbol,
            "name": info.get('longName') or info.get('shortName') or symbol,
            "summary": info.get('longBusinessSummary') or "No business summary available.",
            "sector": sector_name,
            "industry": industry_name,
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
            },
            "valuation_models": valuation_models,
            "consensus_valuation": {
                "intrinsic_value": consensus_iv,
                "margin_of_safety": consensus_mos,
                "models_used": len(valid_ivs),
                "verdict": "Undervalued" if consensus_mos > 0 else "Overvalued"
            }
        }

    except Exception:
        raise

@timed_cache(ttl_seconds=86400, soft_ttl_seconds=43200) # 24h hard, 12h soft (SWR)
def get_historical_trends(symbol: str, time_range: str = '5y'):
    try:
        from yahooquery import Ticker
        import pandas as pd
        
        t = Ticker(symbol)
        
        # Use quarterly frequency for 1Y, annual for longer ranges
        is_quarterly = time_range.lower() == '1y'
        freq = 'q' if is_quarterly else 'a'
        
        inc = t.income_statement(frequency=freq)
        cf = t.cash_flow(frequency=freq)
        vm = t.valuation_measures
        
        # Helper to convert df to list of dicts {date, value}
        def extract_trend(df, col_name, quarterly=False):
            if type(df) != pd.DataFrame or col_name not in df.columns:
                return []
            
            # Reset index to make 'asOfDate' a column if it's not
            if 'asOfDate' not in df.columns and df.index.name == 'asOfDate':
                df = df.reset_index()
                
            if 'asOfDate' not in df.columns:
                return []
                
            # Filter out NaNs
            valid = df.dropna(subset=[col_name, 'asOfDate']).copy()
            if valid.empty:
                return []
                
            # Format date — show quarter labels for quarterly, just year for annual
            dates = pd.to_datetime(valid['asOfDate'])
            if quarterly:
                valid['date'] = dates.dt.strftime('%Y-Q') + ((dates.dt.month - 1) // 3 + 1).astype(str)
            else:
                valid['date'] = dates.dt.strftime('%Y-%m-%d')
            
            valid['value'] = valid[col_name].astype(float)
            
            # Sort by actual date
            valid['_sort'] = dates
            valid = valid.sort_values('_sort')
            
            # Keep last N records based on time_range
            if quarterly:
                limit = 4  # 4 quarters for 1Y
            else:
                limit = 5
                if time_range.lower() == '3y': limit = 3
                elif time_range.lower() == 'max': limit = 20
            
            res = valid.tail(limit)
            return res[['date', 'value']].to_dict('records')
            
        pe_trend = extract_trend(vm, 'PeRatio', quarterly=is_quarterly)
        rev_trend = extract_trend(inc, 'TotalRevenue', quarterly=is_quarterly)
        eps_trend = extract_trend(inc, 'DilutedEPS', quarterly=is_quarterly)
        
        # Calculate Earnings Growth Trend (% change between periods)
        growth_trend = []
        if len(eps_trend) > 1:
            for i in range(1, len(eps_trend)):
                curr = eps_trend[i]['value']
                prev = eps_trend[i-1]['value']
                if prev != 0:
                    growth = ((curr - prev) / abs(prev)) * 100
                    growth_trend.append({
                        "date": eps_trend[i]['date'],
                        "value": round(growth, 2)
                    })
        
        # Free Cash Flow
        fcf_trend = extract_trend(cf, 'FreeCashFlow', quarterly=is_quarterly)
        
        return {
            "symbol": symbol,
            "pe_trend": pe_trend,
            "revenue_trend": rev_trend,
            "eps_trend": eps_trend,
            "growth_trend": growth_trend,
            "fcf_trend": fcf_trend,
            "frequency": "quarterly" if is_quarterly else "annual"
        }
    except Exception as e:
        return {"error": f"Trend fetch failed: {str(e)}"}
