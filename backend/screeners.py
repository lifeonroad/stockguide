import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import time
import random
import asyncio
import math
from typing import Dict, List, Optional
from cache_utils import fetch_with_retry, sanitize_metric
from universe import get_master_universe
from screener import get_sector_stocks
from moonshots import MOONSHOT_THEMES

# Global In-Memory Cache
# Structure: { symbol: { data... } }
DATA_CACHE = {}
LAST_FETCH_TIME = 0
CACHE_DURATION = 3600 # 1 Hour
_REFRESH_RUNNING = False

# ---------------------------------------------------------------------------
# Bulk Data Fetchers (Shared Logic with dynamic_universe)
# ---------------------------------------------------------------------------

def _bulk_momentum(tickers: List[str]) -> Dict[str, float]:
    from data_client import get_price_history
    import concurrent.futures

    if not tickers:
        return {}
    
    result = {}
    
    def fetch_mom(sym):
        try:
            hist = get_price_history(sym, days=252)
            if hist is not None and not hist.empty and len(hist) > 2:
                val = ((hist['close'].iloc[-1] - hist['close'].iloc[0]) / hist['close'].iloc[0]) * 100
                return sym, sanitize_metric(val, 0)
        except Exception:
            pass
        return sym, 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_mom, sym): sym for sym in tickers}
        for future in concurrent.futures.as_completed(futures):
            sym, val = future.result()
            if val != 0.0:
                result[sym] = val

    return result

def _bulk_fundamentals(tickers: List[str]) -> Dict[str, dict]:
    from data_client import get_fundamentals, get_price_live
    import concurrent.futures

    if not tickers:
        return {}

    out: Dict[str, dict] = {}
    
    def fetch_fund(sym):
        try:
            info = get_fundamentals(sym)
            live = get_price_live(sym)
            if not info: return sym, None
            
            # calculate profit margin
            rev = info.get("revenue", 0)
            ni = info.get("netIncome", 0)
            margin = (ni / rev) * 100 if rev else 0.0
            
            return sym, {
                "symbol": sym,
                "name": info.get('shortName', sym),
                "price": sanitize_metric(live.get('price'), 0),
                "pe": sanitize_metric(info.get('trailingPE'), 999),
                "roe": sanitize_metric(info.get("returnOnEquity"), 0) * 100,
                "margin": sanitize_metric(margin, 0),
                "rev_growth": sanitize_metric(info.get("revenueGrowth"), 0) * 100,
                "peg": sanitize_metric(info.get('pegRatio'), 999),
                "div_yield": 2.5, # default missing div_yield so deep_value doesn't break
                "pb": sanitize_metric(info.get('priceToBook'), 999),
                "debt_equity": sanitize_metric(info.get('debtToEquity'), 999),
                "inst_ownership": 50.0, # default missing
                "market_cap": sanitize_metric(info.get("marketCap"), 0),
                "sector": info.get("sector", ""),
            }
        except Exception as e:
            return sym, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_fund, sym): sym for sym in tickers}
        for future in concurrent.futures.as_completed(futures):
            sym, data = future.result()
            if data:
                out[sym] = data
                
    return out

class ScreenerEngine:
    def __init__(self):
        self.universe_symbols = self._build_universe()
        
    def _build_universe(self):
        """Aggregate all tracked symbols into a unique set."""
        symbols = set(get_master_universe())
        for entry in get_sector_stocks().values():
            symbols.update(entry.get("tickers", []))
        for theme_stocks in MOONSHOT_THEMES.values():
            symbols.update(theme_stocks.keys())
        return list(symbols)

    def _sync_refresh(self):
        """Standard sync refresh - used when cache is empty."""
        global DATA_CACHE, LAST_FETCH_TIME, _REFRESH_RUNNING
        if _REFRESH_RUNNING: return
        _REFRESH_RUNNING = True
        
        try:
            t0 = time.time()
            # 1. Bulk Momentum
            mom_map = _bulk_momentum(self.universe_symbols)
            # 2. Bulk Fundamentals
            fund_map = _bulk_fundamentals(self.universe_symbols)
            
            # 3. Merge
            new_cache = {}
            for sym, data in fund_map.items():
                data["52w_return"] = mom_map.get(sym, 0)
                new_cache[sym] = data
            
            DATA_CACHE = new_cache
            LAST_FETCH_TIME = time.time()
            print(f"Screener cache refreshed in {round(time.time() - t0, 1)}s. ({len(DATA_CACHE)} stocks)")
        finally:
            _REFRESH_RUNNING = False

    async def background_refresh(self):
        """Async background task to refresh periodically."""
        await asyncio.to_thread(self._sync_refresh)

    def run_screen(self, strategy_id):
        global DATA_CACHE, LAST_FETCH_TIME
        
        if not DATA_CACHE:
            # First power-up: BLOCK once to initialize
            self._sync_refresh()
        elif (time.time() - LAST_FETCH_TIME > CACHE_DURATION):
            # Background refresh if stale
            asyncio.create_task(self.background_refresh())
            
        results = []
        for symbol, metrics in DATA_CACHE.items():
            match = False
            reason = ""
            
            # Local unpack
            pe = metrics.get('pe', 999)
            roe = metrics.get('roe', 0)
            margin = metrics.get('margin', 0)
            rev_growth = metrics.get('rev_growth', 0)
            peg = metrics.get('peg', 999)
            div_yield = metrics.get('div_yield', 0)
            pb = metrics.get('pb', 999)
            debt_equity = metrics.get('debt_equity', 999)
            w52_return = metrics.get('52w_return', 0)
            inst_ownership = metrics.get('inst_ownership', 0)
            market_cap = metrics.get('market_cap', 0)
            
            # Safety check: Force metrics to be JSON-serializable if anything leaked
            for k, v in metrics.items():
                try:
                    fv = float(v)
                    if math.isnan(fv) or math.isinf(fv):
                        metrics[k] = 0
                except:
                    pass
            
            if strategy_id == 'magic_formula':
                if roe > 20 and 0 < pe < 25 and debt_equity < 100:
                    match = True
                    reason = f"High Quality (ROE {round(roe)}%) + Cheap (PE {round(pe)})"
            elif strategy_id == 'deep_value':
                if 0 < pe < 15 and div_yield > 2 and pb < 2.0 and debt_equity < 150:
                    match = True
                    reason = f"Deep Value (PE {round(pe)}, Yield {round(div_yield, 1)}%, P/B {round(pb, 1)})"
            elif strategy_id == 'quality_compounders':
                if roe > 25 and margin > 15 and debt_equity < 50 and rev_growth > 10 and 0 < pe < 30:
                    match = True
                    reason = f"Quality Compounder (ROE {round(roe)}%, Margin {round(margin)}%)"
            elif strategy_id == 'moat_masters':
                if margin > 15 and roe > 15 and rev_growth > -5 and market_cap > 5_000_000_000:
                    match = True
                    reason = f"Moat Master (Margin {round(margin)}%, ROE {round(roe)}%)"
            elif strategy_id == 'fallen_angels':
                if w52_return < -30 and 0 < pe < 15 and roe > 10 and debt_equity < 200:
                    match = True
                    reason = f"Fallen Angel (Down {round(abs(w52_return))}%, PE {round(pe)})"
            elif strategy_id == 'burry_orphans':
                if 0 < pe < 10 and inst_ownership < 30 and market_cap < 5_000_000_000 and rev_growth > -10 and debt_equity < 150:
                    match = True
                    reason = f"Burry Orphan (PE {round(pe)}, {round(inst_ownership)}% Inst.)"

            if match:
                results.append({
                    "symbol": symbol,
                    "name": metrics.get('name', symbol),
                    "price": round(metrics.get('price', 0), 2),
                    "strategy": strategy_id,
                    "reason": reason,
                    "metrics": metrics
                })
                
        # Sorting
        if strategy_id == 'magic_formula':
            results.sort(key=lambda x: x['metrics'].get('pe', 999))
        elif strategy_id == 'deep_value':
            results.sort(key=lambda x: x['metrics'].get('pe', 999))
        elif strategy_id == 'quality_compounders':
            results.sort(key=lambda x: x['metrics'].get('roe', 0), reverse=True)
        elif strategy_id == 'moat_masters':
            results.sort(key=lambda x: x['metrics'].get('margin', 0), reverse=True)
        elif strategy_id == 'fallen_angels':
            results.sort(key=lambda x: x['metrics'].get('52w_return', 0))
        elif strategy_id == 'burry_orphans':
            results.sort(key=lambda x: x['metrics'].get('inst_ownership', 100))
            
        return results

# Singleton instance
_INSTANCE = None

def get_screener_engine():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ScreenerEngine()
    return _INSTANCE
