
from fastapi import FastAPI, HTTPException
import os
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from market_data import get_buffett_indicator
from screener import get_industry_rankings, analyze_sector_fundamentals, get_sector_stocks, get_sector_meta
from screeners import get_screener_engine
from superinvestors_live import get_live_superinvestors, get_next_filing_info
from filing_calendar import get_filing_status

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

API_TIMEOUT = 60  # seconds (default for fast endpoints)
SLOW_API_TIMEOUT = 300  # 5 min for scans that download lots of data

async def _to_thread_with_timeout(fn, *args, timeout: float = API_TIMEOUT, **kwargs):
    """Run a blocking function in a thread with a timeout."""
    import functools
    wrapped = functools.partial(fn, *args, **kwargs)
    return await asyncio.wait_for(asyncio.to_thread(wrapped), timeout=timeout)

app = FastAPI(title="Rational Equity API")

# Fire background universe scoring immediately on startup
@app.on_event("startup")
async def _startup_background_tasks():
    """
    Kick off async background tasks as soon as the server is ready:
    1. Persistent DB warming (pre-populate SQLite with common symbols)
    2. Dynamic universe scoring (takes ~30-45s)
    3. Cache warming for critical paths (market-status, macro, industries)
    """
    import asyncio
    import threading
    import logging
    import time as time_module

    log = logging.getLogger(__name__)

    # Track startup phases in warming status
    try:
        from data_client import _set_warming
    except ImportError:
        _set_warming = None

    # Delay startup warming by 60s to allow the server to serve fast requests
    # before triggering yahoo API rate limits
    # Start continuous background DB updater immediately (daemon thread)
    try:
        from data_client import start_continuous_db_updater
        start_continuous_db_updater(interval_minutes=30)
        log.info("[WARMUP] Continuous DB updater scheduled (every 30 min)")
    except Exception as exc:
        log.warning("[WARMUP] Could not start continuous DB updater: %s", exc)

    # Start memory/cache maintenance background tasks
    try:
        from memory_watch import start_memory_watcher
        start_memory_watcher(check_interval_minutes=30)
        log.info("[WARMUP] Memory watcher started (check every 30 min)")
    except Exception as exc:
        log.warning("[WARMUP] Could not start memory watcher: %s", exc)

    try:
        from cache_utils import start_cache_pruner
        start_cache_pruner(interval_minutes=60)
        log.info("[WARMUP] Cache pruner started (every 60 min)")
    except Exception as exc:
        log.warning("[WARMUP] Could not start cache pruner: %s", exc)

    try:
        from rate_limiter import start_rate_limiter_cleanup
        start_rate_limiter_cleanup(interval_hours=12)
        log.info("[WARMUP] Rate limiter cleanup scheduled (every 12h)")
    except Exception as exc:
        log.warning("[WARMUP] Could not start rate limiter cleanup: %s", exc)

    async def _delayed_warming():
        await asyncio.sleep(60)

        # 1. Warm critical caches FIRST (sequential to avoid rate limiting)
        log.info("[WARMUP] Phase 1/4: Warming critical caches (sequential)...")
        if _set_warming:
            _set_warming(phase="warming_caches")
        try:
            from market_data import get_buffett_indicator
            await asyncio.to_thread(get_buffett_indicator)
            await asyncio.sleep(5)
        except Exception as e:
            log.debug("[WARMUP] Buffett indicator warmup failed: %s", e)
        try:
            from macro import get_macro_trends
            await asyncio.to_thread(get_macro_trends)
            await asyncio.sleep(5)
        except Exception as e:
            log.debug("[WARMUP] Macro trends warmup failed: %s", e)
        try:
            from screener import get_industry_rankings
            await asyncio.to_thread(get_industry_rankings)
            await asyncio.sleep(5)
        except Exception as e:
            log.debug("[WARMUP] Industry rankings warmup failed: %s", e)
        try:
            from data_client import get_data_source_status
            await asyncio.to_thread(get_data_source_status)
        except Exception as e:
            log.debug("[WARMUP] Data source status warmup failed: %s", e)

        # 2. Warm persistent DB (single-threaded, slow)
        log.info("[WARMUP] Phase 2/4: Warming persistent DB...")
        if _set_warming:
            _set_warming(phase="warming_db")
        try:
            from screener import SECTOR_STOCKS
            from dip_hunter import DIP_UNIVERSE
            from persistent_cache import init_db

            init_db()
            symbols = set()
            for tickers in SECTOR_STOCKS.values():
                symbols.update(tickers)
            for stocks in DIP_UNIVERSE.values():
                symbols.update(stocks)

            from data_client import warm_db_for_symbols
            warm_db_for_symbols(list(symbols))
            log.info("[DB WARMUP] Completed background warming for %d symbols", len(symbols))
        except Exception as exc:
            log.warning("[DB WARMUP] Failed: %s", exc)

        await asyncio.sleep(10)

        # 3. Dynamic universe scoring (delayed further)
        log.info("[WARMUP] Phase 3/4: Dynamic universe scoring...")
        if _set_warming:
            _set_warming(phase="scoring_universe")
        try:
            import dynamic_universe
            asyncio.create_task(dynamic_universe.background_score_all())
        except Exception as exc:
            log.warning("Could not start background scoring: %s", exc)
        await asyncio.sleep(10)

        # 4. Warm dip hunter cache (last, with longer delay)
        def warm_dip_hunter():
            try:
                from dip_hunter import scan_stock_dips
                log.info("[WARMUP] Starting dip hunter scan...")
                t0 = time_module.time()
                result = scan_stock_dips()
                elapsed = time_module.time() - t0
                log.info("[WARMUP] Dip hunter warmed: %d dips in %.0fs", len(result), elapsed)
                if _set_warming:
                    _set_warming(phase="idle", dip_hunter_done=True, dip_hunter_count=len(result))
            except Exception as exc:
                log.warning("[WARMUP] Dip hunter warm failed: %s", exc)
                if _set_warming:
                    _set_warming(phase="idle", dip_hunter_done=True)

        threading.Timer(30, warm_dip_hunter).start()

    asyncio.create_task(_delayed_warming())

# Enable CORS for frontend (if running separately, though we serve static now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Static Files (Frontend)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
async def read_index():
    response = FileResponse(os.path.join(FRONTEND_DIR, 'index.html'), headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })
    return response

@app.get("/api/market-status")
async def market_status():
    try:
        data = await asyncio.to_thread(get_buffett_indicator)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/industries/top")
async def top_industries():
    try:
        data = await asyncio.to_thread(get_industry_rankings)
        return {
            "rankings": data,
            "universe_meta": get_sector_meta(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from analyst import analyze_stock as analyze_stock_strategy
from macro import get_macro_trends
from cycle_analytics import get_cycle_intelligence
from dip_hunter import scan_etf_dips, scan_stock_dips, get_dip_summary

@app.get("/api/stocks/{industry}")
async def stock_picks(industry: str):
    try:
        data = await asyncio.to_thread(analyze_sector_fundamentals, industry)
        if "error" in data:
             raise HTTPException(status_code=404, detail=data['error'])
        data["universe_meta"] = get_sector_meta(industry)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analyze/{symbol}")
async def analyze_stock_endpoint(symbol: str, strategy: str = "buffett"):
    try:
        data = await asyncio.to_thread(analyze_stock_strategy, symbol, strategy)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data['error'])
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/macro")
async def macro_analysis():
    try:
        data = await asyncio.to_thread(get_macro_trends)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alpha/cycle")
async def alpha_cycle():
    try:
        data = await asyncio.to_thread(get_cycle_intelligence)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from economic import get_economic_indicators
from money_flow import get_money_flow_data
from news import get_market_news
from contrarian import get_contrarian_opportunities
from copycat import get_copycat_performance
from moonshots import MoonshotScanner
from screeners import ScreenerEngine
from updater import update_universe_file
from small_caps import get_small_cap_gems
from research import get_comprehensive_research, get_historical_trends, get_price_chart
from technical_zones import scan_technical_zones
from momentum import scan_momentum_picks
from international import InternationalScanner

@app.get("/api/economic-indicators")
async def economic_indicators():
    try:
        data = await asyncio.to_thread(get_economic_indicators)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/money-flow")
async def money_flow():
    try:
        data = await asyncio.to_thread(get_money_flow_data)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/small-caps")
async def small_caps(min_growth: float = 0.05, max_pe: float = 25.0, min_roe: float = 0.10):
    try:
        data = await _to_thread_with_timeout(get_small_cap_gems, min_growth=min_growth, max_pe=max_pe, min_roe=min_roe, timeout=SLOW_API_TIMEOUT)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Small caps scan timed out. Try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/international/picks")
async def international_picks():
    try:
        from international import InternationalScanner  # noqa: PLC0415
        scanner = InternationalScanner()
        data = await _to_thread_with_timeout(scanner.get_picks, timeout=SLOW_API_TIMEOUT)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="International scan timed out. Try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/{symbol}")
async def research(symbol: str, days: int = 252):
    try:
        data = await asyncio.to_thread(get_comprehensive_research, symbol, days)
        if isinstance(data, dict) and "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Data temporarily unavailable (rate limited). Please retry in a moment.")

@app.get("/api/research/trends/{symbol}")
async def research_trends(symbol: str, range: str = '5y'):
    try:
        data = await asyncio.to_thread(get_historical_trends, symbol, range)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/price-chart/{symbol}")
async def research_price_chart(symbol: str, days: int = 365):
    try:
        data = await asyncio.to_thread(get_price_chart, symbol, days)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/technical/zones")
async def technical_zones(zone: str = "all", min_data_days: int = 200):
    """Scan universe and classify tickers by technical zone (6-zone system with legacy 3-zone compat)."""
    valid_zones = {"all", "dip", "institutional", "public", "crash", "early_accumulation", "extended"}
    if zone not in valid_zones:
        raise HTTPException(status_code=400, detail=f"Invalid zone '{zone}'. Choose from: {', '.join(sorted(valid_zones))}")
    try:
        data = await _to_thread_with_timeout(
            scan_technical_zones, zone, min_data_days, timeout=SLOW_API_TIMEOUT
        )
        return {"results": data, "count": len(data), "zone": zone}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Technical zone scan timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/momentum")
async def momentum_picks(min_score: float = 0, limit: int = 50):
    """Scan universe and return momentum-ranked picks (0-100 score)."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    if min_score < 0 or min_score > 100:
        raise HTTPException(status_code=400, detail="min_score must be between 0 and 100")
    try:
        picks = await _to_thread_with_timeout(
            scan_momentum_picks, min_score, limit, timeout=SLOW_API_TIMEOUT
        )
        return {"picks": picks, "count": len(picks)}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Momentum scan timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/contrarian/opportunities")
async def contrarian_opportunities():
    try:
        data = await _to_thread_with_timeout(get_contrarian_opportunities, timeout=SLOW_API_TIMEOUT)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Contrarian scan timed out. Try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/news")
async def market_news():
    try:
        data = await asyncio.to_thread(get_market_news)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/superinvestors")
async def superinvestors_endpoint():
    try:
        investors = await _to_thread_with_timeout(get_live_superinvestors, timeout=SLOW_API_TIMEOUT)
        next_filing = await _to_thread_with_timeout(get_next_filing_info, timeout=SLOW_API_TIMEOUT)
        filing_status = await _to_thread_with_timeout(get_filing_status, timeout=SLOW_API_TIMEOUT)
        return {
            "investors": investors,
            "next_filing": next_filing,
            "filing_status": filing_status
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Superinvestors data fetch timed out. Try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/update-universe")
async def update_universe_endpoint():
    """Triggers the weekly scraper for S&P 500 / Nasdaq 100 universe +
    pre-warms the dynamic sector scoring cache on disk."""
    try:
        success = await asyncio.to_thread(update_universe_file)
        # Pre-warm dynamic sector rankings into per-sector disk cache
        try:
            from dynamic_universe import get_sector_stocks_cached, write_disk_cache  # noqa: PLC0415
            live_data = get_sector_stocks_cached(25)
            write_disk_cache(live_data)
        except Exception as cache_err:
            pass  # Non-fatal; disk cache is best-effort
        if success:
            return {"status": "success", "message": "Universe updated and sector cache refreshed"}
        else:
            raise HTTPException(status_code=500, detail="Universe update failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/copycat")
async def get_copycat():
    try:
        return await _to_thread_with_timeout(get_copycat_performance, timeout=SLOW_API_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Copycat data fetch timed out. Try again in a moment.")

@app.get("/api/moonshots")
async def get_moonshots():
    try:
        scanner = MoonshotScanner()
        return await _to_thread_with_timeout(scanner.get_moonshots, timeout=SLOW_API_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Moonshot scan timed out. Try again in a moment.")

@app.get("/api/screeners/{strategy_id}")
async def get_screeners(strategy_id: str):
    engine = get_screener_engine()
    try:
        stocks = await _to_thread_with_timeout(engine.run_screen, strategy_id, timeout=SLOW_API_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Screener {strategy_id} timed out.")
    return {
        "stocks": stocks,
        "universe_meta": get_sector_meta(),
    }

# Dip Hunter Endpoints
@app.get("/api/dip-hunter/etfs")
async def dip_hunter_etfs():
    """Get ETF dips with classifications"""
    try:
        data = await _to_thread_with_timeout(scan_etf_dips, timeout=SLOW_API_TIMEOUT)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="ETF dip scan timed out — try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dip-hunter/stocks")
async def dip_hunter_stocks(min_quality: int = 0):
    """Get quality stock dips with classifications"""
    try:
        data = await _to_thread_with_timeout(scan_stock_dips, min_quality, timeout=SLOW_API_TIMEOUT)
        return {
            "results": data,
            "universe_meta": get_sector_meta(),
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Dip scan timed out — try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dip-hunter/summary")
async def dip_hunter_summary():
    """Get dip market summary statistics"""
    try:
        data = await _to_thread_with_timeout(get_dip_summary, timeout=SLOW_API_TIMEOUT)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Dip summary timed out — try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/opportunities")
async def get_opportunities(min_quality: int = 0):
    """Get context-enriched investment opportunities with market regime"""
    try:
        from opportunity_engine import get_opportunities as _get_opportunities
        data = await asyncio.to_thread(_get_opportunities, min_quality)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Portfolio Management Endpoints
from portfolio import PortfolioManager
from portfolio_signals import compute_signals_for_portfolio
from pydantic import BaseModel
from fastapi import Depends
from functools import lru_cache

@lru_cache()
def get_portfolio_manager() -> PortfolioManager:
    """Dependency that returns singleton PortfolioManager instance."""
    return PortfolioManager()

class PortfolioCreate(BaseModel):
    name: str
    description: str = ""
    cash_usd: float = None
    cash_cad: float = None

class PositionCreate(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    purchase_date: str = None
    notes: str = ""
    category: str = "Stock"

class PositionUpdate(BaseModel):
    quantity: float = None
    avg_cost: float = None
    notes: str = None
    category: str = None

@app.get("/api/portfolios")
def list_portfolios(pm: PortfolioManager = Depends(get_portfolio_manager)):
    return pm.list_portfolios()

@app.post("/api/portfolios")
def create_portfolio(portfolio: PortfolioCreate, pm: PortfolioManager = Depends(get_portfolio_manager)):
    return pm.create_portfolio(portfolio.name, portfolio.description)

@app.get("/api/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    result = pm.get_portfolio(portfolio_id)
    if not result:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return result

@app.put("/api/portfolios/{portfolio_id}")
def update_portfolio(portfolio_id: str, portfolio: PortfolioCreate, pm: PortfolioManager = Depends(get_portfolio_manager)):
    success = pm.update_portfolio(
        portfolio_id,
        name=portfolio.name,
        description=portfolio.description,
        cash_usd=portfolio.cash_usd,
        cash_cad=portfolio.cash_cad,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"success": True}

from market_data import get_batch_quotes

@app.get("/api/quotes")
async def get_quotes(symbols: str):
    """
    Get batch quotes for comma-separated symbols.
    Example: /api/quotes?symbols=AAPL,MSFT,TSLA
    """
    if not symbols:
        return {}
    
    ticker_list = symbols.split(',')
    return await asyncio.to_thread(get_batch_quotes, ticker_list)

@app.delete("/api/portfolios/{portfolio_id}")
def delete_portfolio(portfolio_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    success = pm.delete_portfolio(portfolio_id)
    if not success:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"success": True}

@app.post("/api/portfolios/{portfolio_id}/positions")
def add_position(portfolio_id: str, position: PositionCreate, pm: PortfolioManager = Depends(get_portfolio_manager)):
    return pm.add_position(
        portfolio_id, 
        position.ticker, 
        position.quantity, 
        position.avg_cost,
        position.purchase_date,
        position.notes,
        position.category
    )

@app.put("/api/positions/{position_id}")
def update_position(position_id: str, position: PositionUpdate, pm: PortfolioManager = Depends(get_portfolio_manager)):
    success = pm.update_position(
        position_id,
        position.quantity,
        position.avg_cost,
        position.notes
    )
    if not success:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"success": True}

@app.delete("/api/positions/{position_id}")
def delete_position(position_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    success = pm.delete_position(position_id)
    if not success:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"success": True}

class TradeRequest(BaseModel):
    ticker: str
    type: str # BUY / SELL
    quantity: float
    price: float
    currency: str = "USD"
    notes: str = ""

@app.post("/api/portfolios/{portfolio_id}/trade")
def execute_trade(portfolio_id: str, trade: TradeRequest, pm: PortfolioManager = Depends(get_portfolio_manager)):
    result = pm.execute_trade(
        portfolio_id,
        trade.ticker,
        trade.type,
        trade.quantity,
        trade.price,
        trade.currency,
        trade.notes
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/api/portfolios/{portfolio_id}/history")
def get_trade_history(portfolio_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    return pm.get_trade_history(portfolio_id)

@app.post("/api/portfolios/{portfolio_id}/reset")
def reset_portfolio_endpoint(portfolio_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    success = pm.reset_portfolio(portfolio_id)
    if not success:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"success": True}

@app.get("/api/portfolios/{portfolio_id}/signals")
def get_portfolio_signals(portfolio_id: str, pm: PortfolioManager = Depends(get_portfolio_manager)):
    result = compute_signals_for_portfolio(portfolio_id, pm)
    if 'error' in result:
        raise HTTPException(status_code=404, detail=result['error'])
    return result

from cache_utils import clear_cache, get_cache_stats
from data_client import (
    set_defeatbeta_enabled, get_data_source_status, get_failed_tickers,
    permanently_skip_ticker, dismiss_invalid_ticker, get_universe_invalid_ticker_stats,
)
from persistent_cache import get_db_stats as _get_db_stats, clear_db as _clear_db
from memory_watch import get_memory_stats
import time as _time

# Scan progress tracker: {scan_name: {"started_at": float, "phase": str, "total": int, "current": int}}
_scan_progress: dict = {}

def report_scan_progress(scan_name: str, phase: str, total: int = 0, current: int = 0):
    """Report progress for a long-running scan."""
    _scan_progress[scan_name] = {
        "started_at": _scan_progress.get(scan_name, {}).get("started_at", _time.time()),
        "phase": phase,
        "total": total,
        "current": current,
        "elapsed_s": round(_time.time() - _scan_progress.get(scan_name, {}).get("started_at", _time.time()), 1),
    }

def clear_scan_progress(scan_name: str):
    """Remove completed scan from progress tracker."""
    _scan_progress.pop(scan_name, None)

@app.get("/api/admin/cache/stats")
def cache_stats():
    """Returns current cache, circuit breaker, and persistent DB statistics."""
    return {
        "memory_cache": get_cache_stats(),
        "persistent_db": _get_db_stats(),
        "failed_tickers": get_failed_tickers(),
    }

@app.get("/api/admin/failed-tickers")
def failed_tickers_endpoint():
    """Returns list of tickers known to be invalid/bad data."""
    return get_failed_tickers()

@app.get("/api/admin/invalid-tickers/universe-stats")
def invalid_tickers_universe_stats():
    """Shows which tickers in our universe are marked as invalid (for cleanup)."""
    return get_universe_invalid_ticker_stats()

@app.post("/api/admin/invalid-tickers/{symbol}/permanent-skip")
def mark_permanent_skip(symbol: str):
    """Mark a ticker to be PERMANENTLY skipped (never attempt to fetch again).
    
    Use this for tickers like 'DAY' that no longer exist or are consistently invalid.
    """
    return permanently_skip_ticker(symbol)

@app.post("/api/admin/invalid-tickers/{symbol}/dismiss")
def dismiss_ticker(symbol: str):
    """Dismiss/remove a ticker from the invalid list.
    
    Removes temporary failure, permanent skip, and DB tracking.
    """
    return dismiss_invalid_ticker(symbol)

@app.post("/api/admin/cache/clear")
def clear_all_cache():
    """Force clear all caches, circuit breakers, and persistent DB. Use for testing."""
    clear_cache()
    _clear_db()
    return {"status": "success", "message": "All caches, circuit breakers, and persistent DB cleared"}

@app.get("/api/scan/progress")
def scan_progress():
    """Returns progress of any currently running scans."""
    result = {}
    for name, info in _scan_progress.items():
        elapsed = _time.time() - info["started_at"]
        result[name] = {
            "phase": info["phase"],
            "total": info["total"],
            "current": info["current"],
            "elapsed_s": round(elapsed, 1),
            "pct": round(info["current"] / max(info["total"], 1) * 100) if info["total"] > 0 else None,
        }
    return result

@app.get("/api/admin/data-source")
def data_source_status():
    """Returns current data source configuration."""
    return get_data_source_status()

@app.post("/api/admin/data-source")
def data_source_toggle(body: dict):
    """
    Toggle data source at runtime.
    Body: {"enabled": true} for defeatbeta, {"enabled": false} for yfinance.
    Clears all caches on toggle.
    """
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="Missing 'enabled' field (true/false)")
    return set_defeatbeta_enabled(bool(enabled))

@app.get("/api/admin/warming-status")
def warming_status():
    """Returns status of background warming tasks (startup, continuous DB updater, etc.)."""
    try:
        from data_client import get_warming_status
        return get_warming_status()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/admin/memory-stats")
def memory_stats_endpoint():
    """
    Returns current memory usage statistics and leak detection info.
    Uses tracemalloc to track allocations and growth since server start.
    """
    return get_memory_stats()

@app.get("/api/admin/db-viewer")
def db_viewer():
    """Full DB snapshot for the admin DB viewer page."""
    try:
        from persistent_cache import get_db_viewer_data
        return get_db_viewer_data()
    except Exception as exc:
        return {"error": str(exc)}

@app.get("/admin/db-viewer")
async def admin_db_viewer_page():
    """Serve the DB viewer HTML page."""
    import os
    page_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'admin', 'db-viewer.html')
    if not os.path.exists(page_path):
        return {"error": "DB viewer page not found"}
    from fastapi.responses import FileResponse
    return FileResponse(page_path, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
    })

# Import Endpoints
from fastapi import UploadFile, File
import shutil
import tempfile
from pdf_parser import parse_wealthsimple_positions

@app.post("/api/import/pdf")
async def import_pdf(file: UploadFile = File(...)):
    # Save uploaded file momentarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        # Parse logic
        positions = parse_wealthsimple_positions(tmp_path)
        return positions
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.post("/api/import/csv")
async def import_csv(file: UploadFile = File(...)):
    """Parse an uploaded WealthSimple CSV file."""
    import csv
    import io
    try:
        content = await file.read()
        decoded = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        positions = []
        for row in reader:
            if not row or not row.get('Symbol'):
                continue
            try:
                ticker = row['Symbol'].strip()
                qty = float((row.get('Quantity') or '0').strip())
                if qty <= 0:
                    continue
                book_cad = float((row.get('Book Value (CAD)') or '0').strip().replace(',', ''))
                currency = (row.get('Market Price Currency') or 'USD').strip()
                avg_cost = book_cad / qty if qty > 0 else 0
                positions.append({
                    'ticker': ticker,
                    'quantity': qty,
                    'avg_cost': round(avg_cost, 2),
                    'currency': currency,
                    'account_type': row.get('Account Type', '').strip(),
                    'name': row.get('Name', '').strip(),
                    'notes': f'Imported from WealthSimple CSV ({currency})',
                })
            except (ValueError, KeyError, TypeError):
                continue
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/import/portfolio-files")
def list_portfolio_files():
    """List available portfolio files on the server."""
    try:
        from portfolio_parser import get_available_files
        files = get_available_files()
        return {"files": files}
    except Exception as e:
        return {"files": [], "error": str(e)}

@app.post("/api/import/from-server-files")
def import_from_server_files():
    """Import positions from server-side portfolio files."""
    try:
        from portfolio_parser import parse_all
        positions = parse_all()
        if not positions:
            raise HTTPException(status_code=404, detail="No portfolio files found or no positions could be parsed")
        return positions
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
