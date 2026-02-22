"""
cycle_analytics.py
==================
Market Cycle & Sector Rotation Intelligence.

Logic:
1. Sector Rotation: Analysis of GICS ETF performance across 1D, 1W, 1M, 6M.
2. Market Phase: Classifies cycle (Early, Mid, Late, Recession) using macro data.
3. Institutional Sentiment: Simple volume-weighted trend proxy.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from cache_utils import timed_cache, fetch_with_retry, sanitize_metric
from macro import get_macro_trends, SECTOR_MAP

# Invert SECTOR_MAP for easy name lookups
NAME_MAP = {v: k for k, v in SECTOR_MAP.items()}

# High-quality picks per sector for Alpha Intelligence
SECTOR_PICKS = {
    "Energy": ["XOM", "CVX", "COP"],
    "Materials": ["LIN", "SHW", "FCX"],
    "Health Care": ["LLY", "UNH", "JNJ"],
    "Financials": ["JPM", "BAC", "V"],
    "Technology": ["MSFT", "AAPL", "NVDA"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD"],
    "Consumer Staples": ["PG", "COST", "KO"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
    "Communication Services": ["GOOGL", "META", "NFLX"],
    "Industrials": ["CAT", "HON", "GE"]
}

@timed_cache(ttl_seconds=3600)
def get_cycle_intelligence():
    """
    Returns the comprehensive alpha report:
    - Rotation Heatmap Data
    - Cycle Phase Analysis
    - Institutional Flow Proxy
    """
    try:
        tickers = list(SECTOR_MAP.values())
        # SPY as baseline
        tickers.append("SPY")
        
        # Fetch 1-year history to calculate multi-timeframe returns
        data = fetch_with_retry(
            lambda: yf.download(tickers, period="1y", interval="1d", progress=False, threads=True),
            max_attempts=2
        )
        
        if data.empty:
            return {"error": "No data available"}
            
        # Extract Close prices - handle MultiIndex and single level index
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                close = data['Close']
            else:
                # Some versions of yfinance might have a different structure
                # Attempt to find a level that contains 'Close'
                close = data.xs('Close', axis=1, level=0) if 'Close' in data.columns.get_level_values(0) else data
        else:
            close = data['Close'] if 'Close' in data.columns else data
            
        # Calculate returns for different windows
        rotation = []
        for ticker in tickers:
            if ticker == "SPY": continue
            
            name = NAME_MAP.get(ticker, ticker)
            
            # Robust extraction of ticker column
            try:
                # Handle cases where ticker might be a column or part of a multi-index
                if ticker in close.columns:
                    ticker_df = close[ticker]
                else:
                    print(f"[CycleAnalytics] Warning: {ticker} not found in columns: {list(close.columns)}")
                    continue
            except Exception as e:
                print(f"[CycleAnalytics] Error accessing {ticker}: {e}")
                continue
                
            hist = ticker_df.dropna()
            
            if len(hist) < 21: # Lower requirement for visualization
                print(f"[CycleAnalytics] Warning: Not enough data for {ticker}")
                continue
            
            # Use iloc safely
            try:
                ret_1d = (hist.iloc[-1] / hist.iloc[-2] - 1) * 100 if len(hist) >= 2 else 0
                ret_1w = (hist.iloc[-1] / hist.iloc[-5] - 1) * 100 if len(hist) >= 5 else 0
                ret_1m = (hist.iloc[-1] / hist.iloc[-21] - 1) * 100 if len(hist) >= 21 else 0
                ret_6m = (hist.iloc[-1] / hist.iloc[-126] - 1) * 100 if len(hist) >= 126 else ret_1m
            except Exception as e:
                print(f"[CycleAnalytics] Math error for {ticker}: {e}")
                continue
            
            momentum_score = sanitize_metric((ret_1w * 0.4 + ret_1m * 0.6), 0)
            
            # Rating logic
            if momentum_score > 5: rating = "STRONG BUY"
            elif momentum_score > 2: rating = "BUY"
            elif momentum_score < -5: rating = "STRONG SELL"
            elif momentum_score < -2: rating = "SELL"
            else: rating = "HOLD"

            rotation.append({
                "ticker": ticker,
                "name": name,
                "returns": {
                    "1D": sanitize_metric(ret_1d, 0),
                    "1W": sanitize_metric(ret_1w, 0),
                    "1M": sanitize_metric(ret_1m, 0),
                    "6M": sanitize_metric(ret_6m, 0)
                },
                "momentum_score": momentum_score,
                "rating": rating,
                "top_picks": SECTOR_PICKS.get(name, [])
            })
            
        # Determine Cycle Phase (Heuristic based on Macro)
        macro = get_macro_trends()
        phase = _determine_phase(macro)
        
        # Sort rotation by 1-month returns (Standard "Rotation" view)
        rotation.sort(key=lambda x: x["returns"]["1M"], reverse=True)
        
        return {
            "phase": phase,
            "rotation": rotation,
            "scored_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"[CycleAnalytics] Error: {e}")
        return {"error": str(e)}

def _determine_phase(macro_data):
    """
    Classifies the current market cycle phase with actionable strategy hints.
    """
    indicators = macro_data.get("indicators", {})
    vix = indicators.get("vix", {}).get("current", 15)
    rates_dir = indicators.get("rates", {}).get("direction", "Flat")
    
    impacts = macro_data.get("sector_impacts", {})
    defensive_strength = sum(1 for s in ["Consumer Staples", "Healthcare", "Utilities"] 
                           if impacts.get(s, {}).get("impact") == "Tailwind")
    
    if vix > 30:
        return {
            "name": "Recession / Panic",
            "description": "High volatility, defensive flight. Cash is king.",
            "hint": "Focus on extreme liquidity and capital preservation. Look for deep value in 'essential' businesses.",
            "color": "red"
        }
    
    if defensive_strength >= 2 and rates_dir == "Up":
        return {
            "name": "Late Cycle",
            "description": "Rising rates, inflation sensitive. Defensive rotation active.",
            "hint": "Overweight Energy and Materials. S&P 500 performance usually narrows here—stick to quality balance sheets.",
            "color": "orange"
        }
    
    if rates_dir == "Down":
        return {
            "name": "Early Cycle",
            "description": "Recovery mode, low rates, cyclical outperformance.",
            "hint": "Aggressive rotation into Small Caps and Technology. Financials benefit from steepening yield curves.",
            "color": "green"
        }
        
    return {
        "name": "Mid Cycle",
        "description": "Growth moderating. Broad participation, stock picking matters.",
        "hint": "Focus on 'Growth at a Reasonable Price' (GARP). Big Tech often leads, but look for breakout Industrials.",
        "color": "blue"
    }

if __name__ == "__main__":
    import json
    print(json.dumps(get_cycle_intelligence(), indent=2))
