
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

app = FastAPI(title="Rational Equity API")

# Fire background universe scoring immediately on startup
@app.on_event("startup")
async def _startup_background_tasks():
    """
    Kick off async background tasks as soon as the server is ready:
    1. Dynamic universe scoring (takes ~30-45s)
    2. Cache warming for critical paths (market-status, macro, industries)
    """
    try:
        import dynamic_universe  # noqa: PLC0415
        asyncio.create_task(dynamic_universe.background_score_all())
    except Exception as exc:
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning("Could not start background scoring: %s", exc)

    # Warm critical caches so first user gets instant data
    async def _warm_caches():
        import logging
        log = logging.getLogger(__name__)
        log.info("[WARMUP] Starting cache warming for critical paths...")
        tasks = []
        try:
            from market_data import get_buffett_indicator
            tasks.append(asyncio.to_thread(get_buffett_indicator))
        except Exception: pass
        try:
            from macro import get_macro_trends
            tasks.append(asyncio.to_thread(get_macro_trends))
        except Exception: pass
        try:
            from screener import get_industry_rankings
            tasks.append(asyncio.to_thread(get_industry_rankings))
        except Exception: pass
        try:
            from filing_calendar import get_filing_status
            tasks.append(asyncio.to_thread(get_filing_status))
        except Exception: pass
        try:
            from data_client import get_data_source_status
            tasks.append(asyncio.to_thread(get_data_source_status))
        except Exception: pass

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = sum(1 for r in results if not isinstance(r, Exception))
            log.info("[WARMUP] Completed: %d/%d caches warmed successfully", success, len(results))

        # Warm dip hunter cache in background (delayed to not compete with startup)
        def warm_dip_hunter():
            try:
                from dip_hunter import scan_stock_dips
                log.info("[WARMUP] Starting dip hunter scan (first run, ~2-5 min)...")
                t0 = __import__('time').time()
                result = scan_stock_dips()
                elapsed = __import__('time').time() - t0
                log.info("[WARMUP] Dip hunter warmed: %d dips in %.0fs", len(result), elapsed)
            except Exception as exc:
                log.warning("[WARMUP] Dip hunter warm failed: %s", exc)

        import threading
        threading.Timer(10, warm_dip_hunter).start()

    asyncio.create_task(_warm_caches())

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
from research import get_comprehensive_research, get_historical_trends
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
        data = await asyncio.to_thread(get_small_cap_gems, min_growth=min_growth, max_pe=max_pe, min_roe=min_roe)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/international/picks")
async def international_picks():
    try:
        scanner = InternationalScanner()
        data = await asyncio.to_thread(scanner.get_picks)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/research/{symbol}")
async def research(symbol: str):
    try:
        data = await asyncio.to_thread(get_comprehensive_research, symbol)
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

@app.get("/api/contrarian/opportunities")
async def contrarian_opportunities():
    try:
        data = await asyncio.to_thread(get_contrarian_opportunities)
        return data
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
        investors = await asyncio.to_thread(get_live_superinvestors)
        next_filing = await asyncio.to_thread(get_next_filing_info)
        filing_status = await asyncio.to_thread(get_filing_status)
        return {
            "investors": investors,
            "next_filing": next_filing,
            "filing_status": filing_status
        }
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
    return await asyncio.to_thread(get_copycat_performance)

@app.get("/api/moonshots")
async def get_moonshots():
    scanner = MoonshotScanner()
    return await asyncio.to_thread(scanner.get_moonshots)

@app.get("/api/screeners/{strategy_id}")
async def get_screeners(strategy_id: str):
    engine = get_screener_engine()
    stocks = await asyncio.to_thread(engine.run_screen, strategy_id)
    return {
        "stocks": stocks,
        "universe_meta": get_sector_meta(),
    }

# Dip Hunter Endpoints
@app.get("/api/dip-hunter/etfs")
async def dip_hunter_etfs():
    """Get ETF dips with classifications"""
    try:
        data = await asyncio.to_thread(scan_etf_dips)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dip-hunter/stocks")
async def dip_hunter_stocks(min_quality: int = 0):
    """Get quality stock dips with classifications"""
    try:
        data = await asyncio.to_thread(scan_stock_dips, min_quality)
        return {
            "results": data,
            "universe_meta": get_sector_meta(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dip-hunter/summary")
async def dip_hunter_summary():
    """Get dip market summary statistics"""
    try:
        data = await asyncio.to_thread(get_dip_summary)
        return data
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
    success = pm.update_portfolio(portfolio_id, portfolio.name, portfolio.description)
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

from cache_utils import clear_cache, get_cache_stats
from data_client import set_defeatbeta_enabled, get_data_source_status

@app.get("/api/admin/cache/stats")
def cache_stats():
    """Returns current cache and circuit breaker statistics."""
    return get_cache_stats()

@app.post("/api/admin/cache/clear")
def clear_all_cache():
    """Force clear all caches and circuit breakers. Use for testing."""
    clear_cache()
    return {"status": "success", "message": "All caches and circuit breakers cleared"}

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

# Import Endpoints
from fastapi import UploadFile, File
import shutil
import tempfile
import os
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
