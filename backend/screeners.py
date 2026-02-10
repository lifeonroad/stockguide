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

def calculate_52w_return(ticker_obj):
    """Calculate 52-week return percentage"""
    try:
        hist = ticker_obj.history(period="1y")
        if len(hist) < 2:
            return 0
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        return ((end_price / start_price) - 1) * 100
    except Exception:
        return 0

def fetch_single_stock(symbol):
    """
    Worker function to fetch data for a single stock.
    Returns (symbol, data_dict) or None if error.
    """
    try:
        t = yf.Ticker(symbol)
        i = t.info
        
        # Calculate 52-week return
        w52_return = calculate_52w_return(t)
        
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
            "debt_equity": i.get('debtToEquity', 999),
            "52w_return": w52_return,  # NEW
            "inst_ownership": i.get('heldPercentInstitutions', 0) * 100,  # NEW
            "market_cap": i.get('marketCap', 0)  # NEW
        }
        return symbol, data
    except Exception as e:
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
        
        print(f"Refreshing Cache for {len(self.universe)} stocks...")
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
            pb = metrics['pb']
            debt_equity = metrics['debt_equity']
            w52_return = metrics['52w_return']
            inst_ownership = metrics['inst_ownership']
            market_cap = metrics['market_cap']
            
            if strategy_id == 'magic_formula':
                # Greenblatt: High ROE + Low PE + Manageable Debt
                # Refined: ROE > 20% (was 25), PE < 25, Debt/Equity < 100%
                if roe > 20 and 0 < pe < 25 and debt_equity < 100:
                    match = True
                    reason = f"High Quality (ROE {round(roe)}%) + Cheap (PE {round(pe)})"
                    
            elif strategy_id == 'deep_value':
                # Graham: Stricter PE, Higher Yield, Asset Backing
                # PE < 12, Yield > 3%, P/B < 1.5, Debt < 150%
                if 0 < pe < 12 and div_yield > 3 and pb < 1.5 and debt_equity < 150:
                    match = True
                    reason = f"Deep Value (PE {round(pe)}, Yield {round(div_yield, 1)}%, P/B {round(pb, 1)})"
                    
            elif strategy_id == 'quality_compounders':
                # Buffett: Wonderful businesses at reasonable prices
                # ROE > 25%, Margin > 15%, Debt < 50%, Growth > 10%, PE < 30
                if roe > 25 and margin > 15 and debt_equity < 50 and rev_growth > 10 and 0 < pe < 30:
                    match = True
                    reason = f"Quality Compounder (ROE {round(roe)}%, Margin {round(margin)}%)"
                    
            elif strategy_id == 'moat_masters':
                # Competitive Advantage: High margins + efficiency + stable
                # Margin > 20%, ROE > 20%, Growth > 0%, Market Cap > $10B
                if margin > 20 and roe > 20 and rev_growth > 0 and market_cap > 10_000_000_000:
                    match = True
                    reason = f"Moat Master (Margin {round(margin)}%, ROE {round(roe)}%)"
                    
            elif strategy_id == 'fallen_angels':
                # Contrarian: Quality businesses beaten down
                # 52w return < -30%, PE < 15, ROE > 10%, Debt < 200%
                if w52_return < -30 and 0 < pe < 15 and roe > 10 and debt_equity < 200:
                    match = True
                    reason = f"Fallen Angel (Down {round(abs(w52_return))}%, PE{round(pe)})"
                    
            elif strategy_id == 'burry_orphans':
                # Contrarian: Neglected by Wall Street
                # PE < 10, Inst. Own. < 30%, Market Cap < $5B, Growth > -10%, Debt < 150%
                if pe < 10 and inst_ownership < 30 and market_cap < 5_000_000_000 and rev_growth > -10 and debt_equity < 150:
                    match = True
                    reason = f"Burry Orphan (PE {round(pe)}, {round(inst_ownership)}% Inst.)"

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
        elif strategy_id == 'deep_value':
            results.sort(key=lambda x: x['metrics']['pe'])
        elif strategy_id == 'quality_compounders':
            results.sort(key=lambda x: x['metrics']['roe'], reverse=True)
        elif strategy_id == 'moat_masters':
            results.sort(key=lambda x: x['metrics']['margin'], reverse=True)
        elif strategy_id == 'fallen_angels':
            results.sort(key=lambda x: x['metrics']['52w_return'])  # Most beaten down first
        elif strategy_id == 'burry_orphans':
            results.sort(key=lambda x: x['metrics']['inst_ownership'])  # Least institutional first
            
        return results
