import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import time
from universe import get_master_universe
from screener import SECTOR_STOCKS
from moonshots import MOONSHOT_THEMES

# Global In-Memory Cache
# Structure: { symbol: { data... } }
DATA_CACHE = {}
LAST_FETCH_TIME = 0
CACHE_DURATION = 3600 # 1 Hour

def fetch_single_stock(symbol):
    """
    Worker function to fetch data for a single stock.
    Returns (symbol, data_dict) or None if error.
    """
    try:
        t = yf.Ticker(symbol)
        i = t.info
        
        # Extract only what we need to minimize memory footprint
        data = {
            "symbol": symbol,
            "name": i.get('shortName', symbol),
            "price": i.get('currentPrice', 0),
            "pe": i.get('trailingPE', 999),
            "roe": i.get('returnOnEquity', 0) * 100, # %
            "margin": i.get('profitMargins', 0) * 100, # %
            "rev_growth": i.get('revenueGrowth', 0) * 100, # %
            "peg": i.get('pegRatio', 999),
            "div_yield": i.get('dividendYield', 0) * 100, # %
            "pb": i.get('priceToBook', 999),
            "debt_equity": i.get('debtToEquity', 999)
        }
        return symbol, data
    except Exception:
        return symbol, None

class ScreenerEngine:
    def __init__(self):
        self.universe = self._build_universe()
        
    def _build_universe(self):
        """Aggregate all tracked symbols into a unique set."""
        symbols = set(get_master_universe())
        
        # Add Sector Stocks (ensure coverage)
        for sector_list in SECTOR_STOCKS.values():
            symbols.update(sector_list)
            
        # Add Moonshots
        for theme_stocks in MOONSHOT_THEMES.values():
            symbols.update(theme_stocks.keys())
            
        return list(symbols)

    def _refresh_cache(self):
        """
        Fetches data for the entire universe using Threading.
        Updates DATA_CACHE.
        """
        global DATA_CACHE, LAST_FETCH_TIME
        
        print(f"Refeshing Cache for {len(self.universe)} stocks...")
        start_time = time.time()
        
        # Parallel Fetching
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Map returns an iterator of results in order
            results = list(executor.map(fetch_single_stock, self.universe))
            
        # Process results
        valid_count = 0
        for symbol, data in results:
            if data:
                DATA_CACHE[symbol] = data
                valid_count += 1
                
        LAST_FETCH_TIME = time.time()
        print(f"Cache refreshed in {round(time.time() - start_time, 2)}s. Loaded {valid_count} stocks.")

    def run_screen(self, strategy_id):
        """
        Runs the specified strategy.
        Uses cached data if available and fresh.
        """
        global DATA_CACHE, LAST_FETCH_TIME
        
        # Check Cache
        if not DATA_CACHE or (time.time() - LAST_FETCH_TIME > CACHE_DURATION):
            self._refresh_cache()
            
        results = []
        
        # Filter Logic (runs instantly on memory)
        for symbol, metrics in DATA_CACHE.items():
            match = False
            reason = ""
            
            # Unpack for readability
            pe = metrics['pe']
            roe = metrics['roe']
            margin = metrics['margin']
            rev_growth = metrics['rev_growth']
            peg = metrics['peg']
            div_yield = metrics['div_yield']
            debt_equity = metrics['debt_equity']
            
            if strategy_id == 'magic_formula':
                # Greenblatt: High ROE (>25) + Low PE (<25)
                # Adjusted for current market conditions
                if roe > 25 and 0 < pe < 25:
                    match = True
                    reason = f"High Quality (ROE {round(roe)}%) + Cheap (PE {round(pe)})"
                    
            elif strategy_id == 'rule_of_40':
                # SaaS: Growth + Margin > 40
                score = rev_growth + margin
                if score >= 40 and rev_growth > 10:
                    match = True
                    reason = f"Rule of 40 Score: {round(score)}"
                    
            elif strategy_id == 'lynch':
                # GARP: PEG < 1.0 (Strict) or < 1.2 (Relaxed)
                if 0 < peg < 1.2:
                    match = True
                    reason = f"Undervalued Growth (PEG {peg})"
                    
            elif strategy_id == 'deep_value':
                # Graham: PE < 15 + Yield > 2%
                if 0 < pe < 15 and div_yield > 2:
                    match = True
                    reason = f"Deep Value (PE {round(pe)}, Yield {round(div_yield)}%)"

            if match:
                results.append({
                    "symbol": metrics['symbol'],
                    "name": metrics['name'],
                    "price": round(metrics['price'], 2),
                    "strategy": strategy_id,
                    "reason": reason,
                    "metrics": metrics
                })
                
        # Sort Results
        if strategy_id == 'magic_formula':
            results.sort(key=lambda x: x['metrics']['pe'])
        elif strategy_id == 'rule_of_40':
            results.sort(key=lambda x: (x['metrics']['rev_growth'] + x['metrics']['margin']), reverse=True)
        elif strategy_id == 'lynch':
            results.sort(key=lambda x: x['metrics']['peg'])
        elif strategy_id == 'deep_value':
            results.sort(key=lambda x: x['metrics']['pe'])
            
        return results
