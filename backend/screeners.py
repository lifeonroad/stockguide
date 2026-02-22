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
    """Download 1-year monthly prices for ALL tickers in ONE yfinance request."""
    if not tickers:
        return {}
    try:
        raw = yf.download(
            " ".join(tickers),
            period="1y",
            interval="1mo",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        result: Dict[str, float] = {}
        for sym in tickers:
            try:
                if len(tickers) == 1:
                    col = raw["Close"]
                else:
                    col = raw[sym]["Close"]
                if len(col) >= 2:
                    val = ((col.iloc[-1] - col.iloc[0]) / col.iloc[0]) * 100
                    result[sym] = sanitize_metric(val, 0)
            except Exception:
                pass
        return result
    except Exception:
        return {}

def _bulk_fundamentals(tickers: List[str]) -> Dict[str, dict]:
    """Use yahooquery (async mode) for fast bulk metrics."""
    try:
        from yahooquery import Ticker as YQTicker
        yq = YQTicker(tickers, asynchronous=True, max_workers=10, validate=False)

        summary = yq.summary_detail
        fin_data = yq.financial_data
        key_stats = yq.key_stats
        profile = yq.asset_profile

        out: Dict[str, dict] = {}
        for sym in tickers:
            try:
                sd = summary.get(sym, {}) if isinstance(summary, dict) else {}
                fd = fin_data.get(sym, {}) if isinstance(fin_data, dict) else {}
                ks = key_stats.get(sym, {}) if isinstance(key_stats, dict) else {}
                ap = profile.get(sym, {}) if isinstance(profile, dict) else {}

                if isinstance(sd, str) or isinstance(fd, str):
                    continue

                out[sym] = {
                    "symbol": sym,
                    "name": sd.get('shortName', sym),
                    "price": sanitize_metric(sd.get('currentPrice') or sd.get('previousClose'), 0),
                    "pe": sanitize_metric(sd.get('trailingPE'), 999),
                    "roe": sanitize_metric(fd.get("returnOnEquity"), 0) * 100,
                    "margin": sanitize_metric(fd.get("profitMargins"), 0) * 100,
                    "rev_growth": sanitize_metric(fd.get("revenueGrowth"), 0) * 100,
                    "peg": sanitize_metric(ks.get('pegRatio'), 999),
                    "div_yield": sanitize_metric(sd.get('dividendYield'), 0) * 100,
                    "pb": sanitize_metric(ks.get('priceToBook'), 999),
                    "debt_equity": sanitize_metric(fd.get('debtToEquity'), 999),
                    "inst_ownership": sanitize_metric(ks.get('heldPercentInstitutions'), 0) * 100,
                    "market_cap": sanitize_metric(ks.get("enterpriseValue") or sd.get("marketCap"), 0),
                    "sector": ap.get("sector", ""),
                }
            except Exception:
                pass
        return out
    except Exception:
        return {}

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
