
from data_client import get_ticker_info, get_price_history
from macro import get_macro_trends, SECTOR_MAP
from cache_utils import fetch_with_retry
import math

class BaseStrategy:
    def __init__(self, symbol):
        self.symbol = symbol.upper()
        try:
            self.info = get_ticker_info(symbol)
        except Exception:
            self.info = {}
        self._has_data = 'trailingPE' in self.info or 'currentPrice' in self.info
        self.reasons = []
        self.score = 0
        self.rating = "HOLD"
        self.verdict_color = "text-gray-400"
        
    def sanitize(self, val, default=0):
        """Ensure value is a finite number for JSON safety."""
        if val is None: return default
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return default
        return val

    def get_metric(self, key, default=0):
        val = self.info.get(key, default)
        return self.sanitize(val, default)

    def analyze_macro(self):
        """Shared Macro Analysis Logic"""
        try:
            macro_data = get_macro_trends()
            stock_sector = self.info.get('sector', 'Unknown')
            
            # Fuzzy match
            if stock_sector in macro_data['sector_impacts']:
                 matched_impact = macro_data['sector_impacts'][stock_sector]
            else:
                matched_impact = None
                for key in macro_data['sector_impacts'].keys():
                    if key.lower() in stock_sector.lower():
                        matched_impact = macro_data['sector_impacts'][key]
                        break
            
            if matched_impact:
                direction = matched_impact.get('impact', 'Neutral')
                macro_reasons = matched_impact.get('reasons', [])
                if direction == 'Tailwind':
                    self.score += 1
                    self.reasons.append(f"🚀 Macro Tailwind: {stock_sector} benefiting from {', '.join(macro_reasons).lower()}.")
                elif direction == 'Headwind':
                    self.score -= 1
                    self.reasons.append(f"🌬️ Macro Headwind: {stock_sector} facing pressure from {', '.join(macro_reasons).lower()}.")
                else:
                    self.reasons.append(f"⚖️ Macro Neutral: {stock_sector} is relatively stable.")
        except Exception as e:
            print(f"Macro error: {e}")

    def analyze_insider_activity(self):
        """
        Analyzes recent insider transactions (last 10).
        Looking for BUYS (High Confidence).
        Note: Sells are less meaningful (liquidity), but Cluster Sales are bad.
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(self.symbol)
            tx = ticker.insider_transactions
            if tx is None or tx.empty:
                return "Neutral (No Data)"
            
            # Sort by date descending (usually comes sorted, but ensure)
            # The DataFrame index is usually 0, 1... or Date. yfinance is erratic.
            # We'll just take the top 10 rows assuming they are recent.
            recent = tx.head(10)
            
            buys = 0
            sells = 0
            
            for index, row in recent.iterrows():
                # 'Text' column usually contains 'Sale', 'Purchase', 'Option Exercise'
                text = str(row.get('Text', '')).lower()
                
                if 'purchase' in text or 'buy' in text:
                    buys += 1
                elif 'sale' in text or 'sell' in text:
                    sells += 1
            
            if buys >= 2:
                self.score += 1
                self.reasons.append(f"🟢 Insider Buying Detected ({buys} recent purchases). Strong confidence signal.")
                return "BULLISH"
            elif sells >= 4 and buys == 0:
                # Don't penalize score too much for selling unless heavy, just warn
                self.reasons.append(f"⚠️ Heavy Insider Selling ({sells} recent sales).")
                return "BEARISH"
            else:
                return "NEUTRAL"
                
        except Exception as e:
            # print(f"Insider error: {e}") # Silence for production
            return "Neutral (Error)"

    def calculate_implied_growth(self, current_price, eps, discount_rate=0.09):
        """
        Reverse DCF: Solves for 'g' (Implied Growth Rate).
        Uses simplified Gordon Growth Model: Price = EPS * (1+g) / (r - g)
        Rearranged: g = (Price * r - EPS) / (Price + EPS)
        
        Note: This assumes the market expects this growth PERPETUALLY, which is a stress test.
        For a 2-stage model proxy, we generally assume terminal growth is 3% and solve for near-term growth,
        but for MVP, this single-stage proxy is a powerful 'sanity check'.
        """
        if current_price <= 0 or eps <= 0: return 0
        
        try:
            # Using r=9% (Equity Risk Premium)
            # g = (P*r - EPS) / (P + EPS)
            # This is an approximation for 'What constant growth justifies this price?'
            # A more aggressive checking might use PEG, but Reverse DCF is clearer.
            
            numerator = (current_price * discount_rate) - eps
            denominator = current_price + eps
            implied_g = numerator / denominator
            
            return implied_g
        except:
            return 0

    def run(self):
        raise NotImplementedError

class BuffettStrategy(BaseStrategy):
    """
    Warren Buffett: Quality, Moat, Fair Value.
    Long Only focus.
    """
    def run(self):
        if not self._has_data: return {"error": "Symbol not found", "symbol": self.symbol}
        
        # Metrics
        price = self.get_metric('currentPrice')
        eps = self.get_metric('trailingEps')
        pe = self.get_metric('trailingPE', 99)
        roe = self.get_metric('returnOnEquity')
        de = self.get_metric('debtToEquity')
        
        # 1. Macro
        self.analyze_macro()
        insider_signal = self.analyze_insider_activity()
        
        # 2. Moat (ROE)
        if roe > 0.15:
            self.reasons.append(f"✅ High ROE ({round(roe*100, 1)}%) indicates a durable moat.")
            self.score += 2
        elif roe > 0.10:
             self.reasons.append(f"⚠️ Moderate ROE ({round(roe*100, 1)}%).")
        else:
             self.reasons.append(f"❌ Low ROE ({round(roe*100, 1)}%). Capital inefficient.")
             self.score -= 1
             
        # 3. Safety (Debt)
        if de < 50:
            self.reasons.append("✅ Conservative financing (Debt/Equity < 0.5).")
            self.score += 1
        elif de > 100:
             self.reasons.append("❌ High debt load.")
             self.score -= 1

        # 4. Valuation (IV)
        # Simplified IV logic from forecasting.py
        payout = self.get_metric('payoutRatio', 0)
        if payout is None: payout = 0
        retention = 1 - payout
        growth = min(roe * retention, 0.15) if roe > 0 else 0
        future_eps = eps * ((1 + growth) ** 5) if eps > 0 else 0
        future_pe = min(max(pe, 10), 25)
        future_price = future_eps * future_pe
        iv = future_price / (1.1 ** 5)
        
        if price < iv:
            self.reasons.append("✅ Undervalued relative to intrinsic value.")
            self.score += 2
        elif price > iv * 1.2:
            self.reasons.append("❌ Overvalued based on growth projections.")
            self.score -= 1

        # Reverse DCF Check
        implied_g = self.calculate_implied_growth(price, eps)
        
        if implied_g > 0.15: 
             self.reasons.append(f"⚠️ Market expects extreme growth ({round(implied_g*100, 1)}%). High expectations bar.")
        elif implied_g < 0:
             self.reasons.append(f"📉 Market pricing in decline ({round(implied_g*100, 1)}%). Low bar to hurdle.")

        # Verdict
        if self.score >= 4: self.rating = "STRONG BUY"
        elif self.score >= 2: self.rating = "BUY"
        elif self.score >= 0: self.rating = "HOLD"
        else: self.rating = "SELL"
        
        return self._format_output(price, iv, future_price, growth, roe, de, implied_g, insider_signal)

    def _format_output(self, price, iv, target, growth, roe, de, implied_g, insider_signal="Neutral"):
        return {
            "symbol": self.symbol,
            "name": self.info.get('shortName'),
            "strategy": "Warren Buffett",
            "rating": self.rating,
            "score": self.score,
            "reasons": self.reasons,
            "current_price": self.sanitize(round(self.sanitize(price), 2)),
            "intrinsic_value": self.sanitize(round(self.sanitize(iv), 2)),
            "target_price_5yr": self.sanitize(round(self.sanitize(target), 2)),
            "projected_growth_rate": self.sanitize(round(self.sanitize(growth) * 100, 1)),
            "implied_growth_rate": self.sanitize(round(self.sanitize(implied_g) * 100, 1)),
            "metrics": {"roe": self.sanitize(round(self.sanitize(roe)*100,1)), "debt_to_equity": self.sanitize(de)},
            "insider_signal": insider_signal
        }

class BurryStrategy(BaseStrategy):
    """
    Michael Burry: Deep Value, Contrarian, Big Short.
    Looks for hidden disasters (Shorts) or hidden gems (Deep Value).
    """
    def run(self):
        if not self._has_data: return {"error": "Symbol not found", "symbol": self.symbol}
        
        price = self.get_metric('currentPrice')
        ev_ebitda = self.get_metric('enterpriseToEbitda', 0)
        pb = self.get_metric('priceToBook')
        fcf = self.get_metric('freeCashflow') # Raw number
        mkt_cap = self.get_metric('marketCap')
        de = self.get_metric('debtToEquity')
        short_ratio = self.get_metric('shortRatio', 0) # Days to cover
        
        # 1. Macro (Burry cares deeply about macro)
        self.analyze_macro()
        
        # 2. Deep Value (Long Case)
        fcf_yield = (fcf / mkt_cap) if mkt_cap else 0
        
        if ev_ebitda > 0 and ev_ebitda < 8:
            self.reasons.append(f"✅ Deep Value: EV/EBITDA of {round(ev_ebitda, 1)} is very cheap.")
            self.score += 2
        
        if fcf_yield > 0.10:
             self.reasons.append(f"✅ Cash Cow: Free Cash Flow Yield is {round(fcf_yield*100, 1)}%.")
             self.score += 2
        
        # 3. Short Case (Distress)
        if de > 200:
             self.reasons.append(f"📉 High Leverage: Debt/Equity of {de}% is risky.")
             self.score -= 2 # Burry hates bad debt
             
        if pb > 10:
             self.reasons.append(f"📉 Bubble Valuation: Price/Book of {round(pb, 1)} is extreme.")
             self.score -= 1
             
        if ev_ebitda > 30:
             self.reasons.append(f"📉 Overhyped: EV/EBITDA > 30.")
             self.score -= 1
             
        # Verdict Logic
        if self.score >= 3: self.rating = "AGGRESSIVE BUY"
        elif self.score <= -3: self.rating = "The Big SHORT"
        elif self.score <= -1: self.rating = "AVOID / WEAK"
        else: self.rating = "WATCH"
        
        # Mocking IV for Burry (He doesn't do simple DCF, but we need fields for the UI)
        # We'll use a conservative book value multiplier or FCF multiple
        iv = (fcf * 10 / self.info.get('sharesOutstanding', 1)) if fcf > 0 else 0
        
        return {
            "symbol": self.symbol,
            "name": self.info.get('shortName'),
            "strategy": "Michael Burry",
            "rating": self.rating,
            "score": self.score,
            "reasons": self.reasons,
            "current_price": self.sanitize(round(self.sanitize(price), 2)),
            "intrinsic_value": self.sanitize(round(self.sanitize(iv), 2)), # Using FCF x 10 proxy
            "target_price_5yr": self.sanitize(round(self.sanitize(iv), 2)), # Using Fair Value (FCF x 10) as target
            "projected_growth_rate": 0,
            "metrics": {
                "ev_ebitda": self.sanitize(round(self.sanitize(ev_ebitda), 2)), 
                "fcf_yield": self.sanitize(round(self.sanitize(fcf_yield)*100, 1)), 
                "short_float": self.sanitize(round(self.sanitize(short_ratio), 2)), 
                "debt_to_equity": self.sanitize(de)
            }
        }

class LynchStrategy(BaseStrategy):
    """
    Peter Lynch: GARP (Growth At Reasonable Price).
    PEG Ratio, Inventory Check.
    """
    def run(self):
        if not self._has_data: return {"error": "Symbol not found", "symbol": self.symbol}
        
        price = self.get_metric('currentPrice')
        peg = self.get_metric('pegRatio', 0)
        # Inventory not easily available in yfinance 'info', need 'balance sheet' access which is slower.
        # We will skip inventory check for MVP or check Revenue Growth vs Earnings Growth as proxy.
        rev_growth = self.get_metric('revenueGrowth', 0)
        earn_growth = self.get_metric('earningsGrowth', 0)
        
        self.analyze_macro()
        
        # PEG Ratio
        if peg > 0 and peg < 1.0:
            self.reasons.append(f"✅ PEG Ratio of {peg} suggests undervalued growth.")
            self.score += 2
        elif peg < 0:
            self.reasons.append(f"⚠️ Negative PEG (Earnings/Growth issues).")
            self.score -= 1
        elif peg > 2.0:
             self.reasons.append(f"❌ PEG Ratio of {peg} is too expensive.")
             self.score -= 1
             
        # Growth Check
        if earn_growth > 0.20:
             self.reasons.append(f"🚀 Fast Grower: Earnings up {round(earn_growth*100,1)}%.")
             self.score += 1
             
        # Lynch Verdict
        if self.score >= 3: self.rating = "BUY (Multibagger?)"
        elif self.score >= 1: self.rating = "HOLD"
        else: self.rating = "PASS"
        
        iv = 0 # Lynch aims for multiples, not specific DCF IV usually.
        
        return {
            "symbol": self.symbol,
            "name": self.info.get('shortName'),
            "strategy": "Peter Lynch",
            "rating": self.rating,
            "score": self.score,
            "reasons": self.reasons,
            "current_price": self.sanitize(round(self.sanitize(price), 2)),
            "intrinsic_value": 0,
            "target_price_5yr": self.sanitize(round(self.sanitize(price * ((1+earn_growth)**5)), 2)), # Simple projection
            "projected_growth_rate": self.sanitize(round(self.sanitize(earn_growth) * 100, 1)),
            "metrics": {"peg": self.sanitize(peg), "earnings_growth": self.sanitize(round(self.sanitize(earn_growth)*100, 1))}
        }

def analyze_stock(symbol, strategy_name='buffett'):
    strategies = {
        'buffett': BuffettStrategy,
        'burry': BurryStrategy,
        'lynch': LynchStrategy
    }
    
    cls = strategies.get(strategy_name.lower(), BuffettStrategy)
    result = cls(symbol).run()
    
    if isinstance(result, dict) and "error" not in result:
        try:
            from indicators import calculate_rsi, get_price_history_for_indicators
            df = get_price_history_for_indicators(symbol, min_days=30)
            if df is not None and not df.empty and 'close' in df.columns:
                result["rsi_14"] = round(calculate_rsi(df['close'], 14), 1)
            else:
                result["rsi_14"] = None
        except Exception:
            result["rsi_14"] = None
    
    return result
