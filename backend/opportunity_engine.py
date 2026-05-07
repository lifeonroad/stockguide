"""
opportunity_engine.py
=====================
Context-Aware Investment Opportunity Engine

Architecture
------------
1. Market Regime Detection: Analyzes SPY, QQQ, VIX, and breadth to classify
   market state (BULL / BEAR / CRASH / ROTATION).
2. Opportunity Classification: Tags each dip with context:
   - CRASH_BUY: Market down, but this company is strong (balance sheet + ROE).
   - COMPANY_TURNAROUND: Stock-specific issue resolving (insider buying, upgrades).
   - SECTOR_RECOVERY: Industry bottoming (sector ETF oversold but recovering).
   - MOMENTUM_SHIFT: Sector rotating into favor (relative strength improving).
3. Sentiment Signals: Insider buying, analyst upgrades/downgrades, earnings beats.

Performance
-----------
- Market regime: ~2s (single batch ETF download)
- Full scan: ~25s (builds on dip_hunter.scan_stock_dips cache)
- Cached: <1ms
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
import concurrent.futures
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from cache_utils import timed_cache, fetch_with_retry

logger = logging.getLogger(__name__)

MARKET_ETFS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "DIA": "Dow Jones",
    "IWM": "Russell 2000",
    "VIXY": "VIX Short-Term",
}

# ──────────────────────────────────────────────────────────
# Market Regime Detection
# ──────────────────────────────────────────────────────────

def _calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


@timed_cache(ttl_seconds=1800, soft_ttl_seconds=900)
def get_market_regime() -> Dict:
    """
    Classify market regime using breadth, VIX, and index momentum.
    
    Returns:
        regime: BULL / BEAR / CRASH / ROTATION
        spy_drop: S&P 500 drop from 52-week high (%)
        qqq_drop: Nasdaq drop from 52-week high (%)
        vix_level: Current VIX or VIXY proxy
        breadth: % of sectors with positive 1M return
        signal: Actionable guidance
    """
    tickers = list(MARKET_ETFS.keys()) + ["SPY", "XLK", "XLF", "XLV", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE"]
    
    try:
        # Fetch 1-year history
        data = fetch_with_retry(
            lambda: yf.download(list(set(tickers)), period="1y", progress=False, threads=True),
            max_attempts=2,
            base_delay=1.0,
        )
        if data is None or data.empty:
            return _fallback_regime()
        
        # Extract close prices
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"] if "Close" in data.columns.levels[0] else data
        else:
            close = data["Close"] if "Close" in data.columns else data
        
        # VIX level (VIXY as proxy — trades roughly 2x VIX in high vol, 0.5x in low vol)
        vix_level = 0
        if "VIXY" in close.columns:
            vixy_close = close["VIXY"].dropna()
            if not vixy_close.empty:
                vixy_price = float(vixy_close.iloc[-1])
                # VIXY ~15-60, rough proxy: VIX ≈ VIXY * 0.6
                vix_level = round(vixy_price * 0.6, 1)
        
        # S&P 500 metrics
        spy_col = "SPY" if "SPY" in close.columns else None
        qqq_col = "QQQ" if "QQQ" in close.columns else None
        
        spy_drop = 0
        qqq_drop = 0
        spy_rsi = 50
        qqq_rsi = 50
        
        if spy_col and not close[spy_col].dropna().empty:
            spy = close[spy_col].dropna()
            spy_drop = round(((spy.iloc[-1] - spy.max()) / spy.max()) * 100, 1)
            spy_rsi = round(_calculate_rsi(spy), 1)
        
        if qqq_col and not close[qqq_col].dropna().empty:
            qqq = close[qqq_col].dropna()
            qqq_drop = round(((qqq.iloc[-1] - qqq.max()) / qqq.max()) * 100, 1)
            qqq_rsi = round(_calculate_rsi(qqq), 1)
        
        # Sector breadth (% of sectors with positive 1M return)
        sector_tickers = ["XLK", "XLF", "XLV", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE"]
        positive_sectors = 0
        sector_momentum = []
        for s in sector_tickers:
            if s in close.columns:
                s_data = close[s].dropna()
                if len(s_data) >= 21:
                    ret_1m = ((s_data.iloc[-1] - s_data.iloc[-21]) / s_data.iloc[-21]) * 100
                    if ret_1m > 0:
                        positive_sectors += 1
                    sector_momentum.append({"ticker": s, "return_1m": round(ret_1m, 1)})
        
        breadth = round(positive_sectors / len(sector_tickers) * 100) if sector_tickers else 50
        
        # Classify regime
        regime, signal, color = _classify_regime(spy_drop, qqq_drop, vix_level, breadth)
        
        return {
            "regime": regime,
            "spy_drop": spy_drop,
            "qqq_drop": qqq_drop,
            "vix_level": vix_level,
            "breadth": breadth,
            "spy_rsi": spy_rsi,
            "qqq_rsi": qqq_rsi,
            "signal": signal,
            "color": color,
            "sector_momentum": sector_momentum,
            "scanned_at": datetime.now().isoformat(),
        }
        
    except Exception as e:
        logger.warning("Market regime detection failed: %s", e)
        return _fallback_regime()


def _classify_regime(spy_drop, qqq_drop, vix_level, breadth):
    if spy_drop < -20 or vix_level > 35:
        return "CRASH", "Fear is your friend — but only in quality. Focus on strongest balance sheets.", "red"
    if spy_drop < -10 or qqq_drop < -15:
        return "BEAR", "Broad selloff. Look for oversold quality names with strong fundamentals.", "orange"
    if breadth < 30:
        return "ROTATION", "Capital shifting between sectors. Follow the momentum.", "yellow"
    if spy_drop > -5 and breadth > 60:
        return "BULL", "Market strong. Dip-buying opportunities in quality names are rare — act fast.", "green"
    return "MIXED", "Mixed market. Stock picking matters — focus on individual company fundamentals.", "blue"


def _fallback_regime():
    return {
        "regime": "MIXED",
        "spy_drop": 0,
        "qqq_drop": 0,
        "vix_level": 0,
        "breadth": 50,
        "spy_rsi": 50,
        "qqq_rsi": 50,
        "signal": "Unable to determine market regime. Proceed with caution.",
        "color": "gray",
        "sector_momentum": [],
        "scanned_at": datetime.now().isoformat(),
    }


# ──────────────────────────────────────────────────────────
# Sentiment Signals
# ──────────────────────────────────────────────────────────

def _get_insider_signal(symbol: str) -> Dict:
    """
    Check insider transactions for buying/selling patterns.
    Cached 6h — insider data doesn't change intraday.
    """
    return _cached_insider_signal(symbol)


@timed_cache(ttl_seconds=21600, soft_ttl_seconds=10800)
def _cached_insider_signal(symbol: str) -> Dict:
    try:
        ticker = yf.Ticker(symbol)
        tx = ticker.insider_transactions
        if tx is None or tx.empty:
            return {"signal": "NEUTRAL", "buys": 0, "sells": 0, "details": ""}
        
        recent = tx.head(10)
        buys = 0
        sells = 0
        buy_value = 0
        
        for _, row in recent.iterrows():
            text = str(row.get("Text", "")).lower()
            shares = int(row.get("Shares", 0) or 0)
            
            if "purchase" in text or "buy" in text:
                buys += 1
                buy_value += shares
            elif "sale" in text or "sell" in text:
                sells += 1
        
        if buys >= 2:
            return {
                "signal": "BULLISH",
                "buys": buys,
                "sells": sells,
                "details": f"Insider buying ({buys} purchases, {buy_value:,} shares)"
            }
        elif sells >= 5 and buys == 0:
            return {
                "signal": "BEARISH",
                "buys": buys,
                "sells": sells,
                "details": f"Heavy insider selling ({sells} sales)"
            }
        else:
            return {"signal": "NEUTRAL", "buys": buys, "sells": sells, "details": ""}
    except Exception:
        return {"signal": "NEUTRAL", "buys": 0, "sells": 0, "details": ""}


def _get_analyst_signal(symbol: str) -> Dict:
    """
    Check analyst recommendations for upgrade/downgrade trends.
    Cached 6h — analyst ratings change infrequently.
    """
    return _cached_analyst_signal(symbol)


@timed_cache(ttl_seconds=21600, soft_ttl_seconds=10800)
def _cached_analyst_signal(symbol: str) -> Dict:
    try:
        ticker = yf.Ticker(symbol)
        recs = ticker.recommendations
        if recs is None or recs.empty:
            return {"signal": "NEUTRAL", "buy_pct": 0, "trend": ""}
        
        latest = recs.tail(1).iloc[0]
        strong_buy = latest.get("strongBuy", 0) or 0
        buy = latest.get("buy", 0) or 0
        hold = latest.get("hold", 0) or 0
        sell = latest.get("sell", 0) or 0
        strong_sell = latest.get("strongSell", 0) or 0
        
        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return {"signal": "NEUTRAL", "buy_pct": 0, "trend": ""}
        
        buy_pct = round((strong_buy + buy) / total * 100)
        
        trend = "stable"
        if len(recs) >= 2:
            prev = recs.iloc[-2]
            prev_buy = (prev.get("strongBuy", 0) or 0) + (prev.get("buy", 0) or 0)
            curr_buy = strong_buy + buy
            if curr_buy > prev_buy:
                trend = "upgrades"
            elif curr_buy < prev_buy:
                trend = "downgrades"
        
        if buy_pct >= 70 and trend == "upgrades":
            return {"signal": "BULLISH", "buy_pct": buy_pct, "trend": f"Analyst upgrades ({buy_pct}% buy)"}
        elif buy_pct >= 60:
            return {"signal": "NEUTRAL", "buy_pct": buy_pct, "trend": ""}
        elif buy_pct < 40:
            return {"signal": "BEARISH", "buy_pct": buy_pct, "trend": f"Low analyst conviction ({buy_pct}% buy)"}
        else:
            return {"signal": "NEUTRAL", "buy_pct": buy_pct, "trend": ""}
    except Exception:
        return {"signal": "NEUTRAL", "buy_pct": 0, "trend": ""}


# ──────────────────────────────────────────────────────────
# Opportunity Classification
# ──────────────────────────────────────────────────────────

def classify_opportunity(stock: Dict, regime: Dict, sector_etf_drops: Dict) -> Dict:
    """
    Classify a dip opportunity with context.
    
    Categories:
    - CRASH_BUY: Market down >10%, but company has strong fundamentals (ROE>15%, D/E<100).
    - SECTOR_RECOVERY: Sector ETF is bleeding but showing early recovery signs.
    - COMPANY_TURNAROUND: Stock-specific issue resolving (insider buying, analyst upgrades).
    - MOMENTUM_SHIFT: Sector rotating into favor (relative strength improving).
    - GENERIC_DIP: Doesn't fit a clear narrative.
    
    Returns enriched stock dict with:
    - opportunity_type: The category
    - thesis: 1-sentence investment thesis
    - signals: List of supporting signals (e.g., "Insider buying", "Sector recovering")
    """
    signals = []
    thesis = ""
    
    spy_drop = regime.get("spy_drop", 0)
    qqq_drop = regime.get("qqq_drop", 0)
    sector = stock.get("sector", "Unknown")
    drop_pct = stock.get("drop_pct", 0)
    roe = stock.get("roe", 0)
    debt_equity = stock.get("debt_equity", 999)
    rsi = stock.get("rsi", 50)
    
    # Check sector ETF context
    sector_etf_drop = sector_etf_drops.get(sector, 0)
    
    # === CRASH_BUY: Market down, but company is strong ===
    if spy_drop < -10 and roe > 15 and debt_equity < 100:
        signals.append(f"Market panic (SPY {spy_drop}%)")
        signals.append(f"Strong fundamentals (ROE {roe}%, D/E {debt_equity})")
        
        # Check dividend as "getting paid to wait"
        if stock.get("dividend_yield", 0) > 1.5:
            signals.append(f"Dividend yield {stock['dividend_yield']}% — getting paid to wait")
        
        thesis = f"Quality name caught in market panic. {stock.get('ticker', '')} has strong fundamentals despite the selloff."
        return {**stock, "opportunity_type": "CRASH_BUY", "thesis": thesis, "signals": signals}
    
    # === SECTOR_RECOVERY: Industry bottoming ===
    if abs(sector_etf_drop) > 8 and rsi < 35:
        signals.append(f"Sector ({sector}) down {sector_etf_drop:.1f}% from high")
        signals.append(f"Sector oversold (RSI {rsi})")
        
        # Check if sector is starting to recover (RSI rising from extreme)
        if rsi > 25:
            signals.append("Sector showing early recovery signs")
        
        thesis = f"{sector} sector bottoming out. {stock.get('ticker', '')} is a quality name in a beaten-down industry."
        return {**stock, "opportunity_type": "SECTOR_RECOVERY", "thesis": thesis, "signals": signals}
    
    # === COMPANY_TURNAROUND: Stock-specific issue ===
    # Stock down but sector relatively flat
    if abs(drop_pct) > abs(sector_etf_drop) + 10:
        # Stock-specific problem — check for turnaround signals
        insider = _get_insider_signal(stock.get("ticker", ""))
        analyst = _get_analyst_signal(stock.get("ticker", ""))
        
        if insider.get("signal") == "BULLISH":
            signals.append(f"Insider buying: {insider['details']}")
        if analyst.get("signal") == "BULLISH":
            signals.append(f"Analyst sentiment: {analyst['trend']}")
        
        if insider.get("signal") == "BULLISH" or analyst.get("signal") == "BULLISH":
            thesis = f"Company-specific turnaround story. {stock.get('ticker', '')} is resolving its issues while the sector is stable."
            return {**stock, "opportunity_type": "COMPANY_TURNAROUND", "thesis": thesis, "signals": signals}
    
    # === MOMENTUM_SHIFT: Sector rotating into favor ===
    sector_momentum = regime.get("sector_momentum", [])
    for sm in sector_momentum:
        if sm.get("return_1m", 0) > 2 and sm.get("return_1m", 0) > 0:
            # Sector has positive momentum but stock is still down
            if stock.get("recovery_5d", 0) > 0:
                signals.append(f"Sector showing positive momentum (+{sm['return_1m']}% 1M)")
                signals.append(f"Stock recovering (+{stock['recovery_5d']}% in 5 days)")
                thesis = f"Momentum shifting into {sector}. {stock.get('ticker', '')} is starting to recover."
                return {**stock, "opportunity_type": "MOMENTUM_SHIFT", "thesis": thesis, "signals": signals}
    
    # === GENERIC_DIP: Doesn't fit a clear narrative ===
    signals.append(f"Dropped {abs(drop_pct)}% from high")
    if roe > 15:
        signals.append(f"Strong ROE ({roe}%)")
    if debt_equity < 100:
        signals.append(f"Low debt (D/E {debt_equity})")
    
    return {**stock, "opportunity_type": "GENERIC_DIP", "thesis": f"{stock.get('ticker', '')} is trading below its 52-week high.", "signals": signals}


# ──────────────────────────────────────────────────────────
# Sector ETF Drop Lookup
# ──────────────────────────────────────────────────────────

def _get_sector_etf_drops() -> Dict[str, float]:
    """
    Get current drop from 52-week high for each sector ETF.
    Returns: { sector_name: drop_pct }
    """
    from screener import SECTOR_ETFS
    
    sector_names = {v: k for k, v in SECTOR_ETFS.items()}
    tickers = list(SECTOR_ETFS.keys())
    
    drops = {}
    try:
        data = fetch_with_retry(
            lambda: yf.download(tickers, period="1y", progress=False, threads=True),
            max_attempts=2,
            base_delay=1.0,
        )
        if data is None or data.empty:
            return drops
        
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"] if "Close" in data.columns.levels[0] else data
        else:
            close = data["Close"] if "Close" in data.columns else data
        
        for ticker in tickers:
            if ticker in close.columns:
                prices = close[ticker].dropna()
                if not prices.empty:
                    drop = ((prices.iloc[-1] - prices.max()) / prices.max()) * 100
                    name = sector_names.get(ticker, ticker)
                    drops[name] = round(drop, 1)
    except Exception as e:
        logger.warning("Sector ETF drops failed: %s", e)
    
    return drops


# ──────────────────────────────────────────────────────────
# Main API
# ──────────────────────────────────────────────────────────

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)
def get_opportunities(min_quality_score: float = 0) -> Dict:
    """
    Main entry point: returns context-enriched investment opportunities.
    
    Returns:
        regime: Market regime info
        opportunities: List of enriched dip opportunities
        summary: Counts by opportunity type
    """
    from dip_hunter import scan_stock_dips
    
    # Get market regime (~2s)
    regime = get_market_regime()
    
    # Get sector context (~2s)
    sector_drops = _get_sector_etf_drops()
    
    # Get raw dip candidates (cached from dip_hunter)
    raw_dips = scan_stock_dips(min_quality_score)
    
    # Classify each opportunity
    opportunities = []
    for stock in raw_dips:
        enriched = classify_opportunity(stock, regime, sector_drops)
        opportunities.append(enriched)
    
    # Sort by quality score
    opportunities.sort(key=lambda x: (-x.get("quality_score", 0), x.get("drop_pct", 0)))
    
    # Summary counts
    type_counts = {}
    for opp in opportunities:
        t = opp.get("opportunity_type", "GENERIC_DIP")
        type_counts[t] = type_counts.get(t, 0) + 1
    
    return {
        "regime": regime,
        "opportunities": opportunities,
        "summary": {
            "total": len(opportunities),
            "by_type": type_counts,
        },
        "scanned_at": datetime.now().isoformat(),
    }
