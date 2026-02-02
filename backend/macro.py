
import yfinance as yf
import pandas as pd
from cache_utils import timed_cache

# Sector Map for Macro Impacts
SECTOR_MAP = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Defense": "ITA" # Special mention, though not in our main ETF list yet, mapped to Industrials usually.
}

@timed_cache(ttl_seconds=3600)  # Cache for 1 hour
def get_macro_trends():
    """
    Fetches macro indicators and returns a 'Weather Report' for sectors.
    """
    # Tickers:
    # ^TNX: 10-Year Treasury Yield
    # CL=F: Crude Oil Futures
    # GC=F: Gold Futures
    # ^VIX: CBOE Volatility Index
    tickers = ["^TNX", "CL=F", "GC=F", "^VIX"]
    
    # Download data - returns multi-index DataFrame
    raw_data = yf.download(tickers, period="5d", progress=False)
    
    # Extract Close prices - handle multi-index structure
    if isinstance(raw_data.columns, pd.MultiIndex):
        # Multi-index: columns are like ('Close', 'CL=F')
        close_data = raw_data['Close']
    else:
        # Single ticker or already flattened
        close_data = raw_data
    
    # Calculate % change over last 5 days to determine "Trend"
    trends = {}
    
    for ticker in tickers:
        try:
            # Access the series for this ticker
            series = close_data[ticker] if ticker in close_data.columns else None
            
            if series is None or len(series) < 2:
                trends[ticker] = {"current": 0, "change_pct": 0, "direction": "Flat"}
                continue
            
            # Drop NaN values and get valid data
            series = series.dropna()
            
            if len(series) < 2:
                trends[ticker] = {"current": 0, "change_pct": 0, "direction": "Flat"}
                continue
                
            current = series.iloc[-1]
            start = series.iloc[0] # 5 days ago approx
            
            # Handle NaN, infinity, and zero values
            if pd.isna(current) or pd.isna(start) or start == 0 or not pd.isfinite(current) or not pd.isfinite(start):
                trends[ticker] = {"current": 0, "change_pct": 0, "direction": "Flat"}
                continue
            
            change = (current - start) / start
            
            # Ensure change is finite
            if not pd.isfinite(change):
                trends[ticker] = {"current": round(float(current), 2), "change_pct": 0, "direction": "Flat"}
                continue
            
            # Label
            if change > 0.01: direction = "Up" # Lower threshold for sensitivity (1%)
            elif change < -0.01: direction = "Down"
            else: direction = "Flat"
            
            trends[ticker] = {
                "current": round(float(current), 2),
                "change_pct": round(float(change * 100), 2),
                "direction": direction
            }
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            # Fallback
            trends[ticker] = {"current": 0, "change_pct": 0, "direction": "Flat"}

    # --- Heuristics Engine ---
    
    # 1. Interest Rates (^TNX)
    # Up: Bad for Tech, Real Estate, Utilities (Yield competition). Good for Financials (NIM).
    # Down: Good for Tech, Real Estate. Bad for Financials.
    rate_dir = trends["^TNX"]["direction"]
    
    # 2. Oil (CL=F)
    # Up: Good for Energy. Bad for Airlines/Transport/Consumer (Inflation tax).
    oil_dir = trends["CL=F"]["direction"]
    
    # 3. Fear/Geopolitics (^VIX + Gold)
    # VIX Up or Gold Up: Flight to safety. Good for Staples, Defense, Gold Miners.
    fear_level = "Normal"
    if trends["^VIX"]["current"] > 20 or trends["^VIX"]["direction"] == "Up":
        fear_level = "High"
        
    # Build Tailwinds/Headwinds Maps
    sector_impacts = {}
    
    for sector in SECTOR_MAP.keys():
        impact = "Neutral"
        reason = []
        
        # Rate Logic
        if sector in ["Technology", "Real Estate", "Utilities"]:
            if rate_dir == "Up": 
                impact = "Headwind"
                reason.append("Rising Rates hurt valuations")
            elif rate_dir == "Down": 
                impact = "Tailwind"
                reason.append("Falling Rates boost valuations")
                
        if sector == "Financials":
            if rate_dir == "Up": 
                impact = "Tailwind"
                reason.append("Higher Rates aid margins")
            elif rate_dir == "Down": 
                impact = "Headwind"
                reason.append("Lower Rates squeeze margins")
                
        # Oil Logic
        if sector == "Energy":
            if oil_dir == "Up": 
                impact = "Tailwind"
                reason.append("Rising Oil Prices")
            elif oil_dir == "Down": 
                impact = "Headwind"
                reason.append("Falling Oil Prices")
                
        if sector == "Consumer Discretionary":
            if oil_dir == "Up":
                # Only override if not already set by rates or if oil is major factor
                if impact != "Headwind":
                    impact = "Headwind"
                    reason.append("Energy costs squeeze consumers")

        # Fear Logic
        if sector in ["Consumer Staples", "Healthcare"]:
            if fear_level == "High":
                impact = "Tailwind"
                reason.append("Defensive rotation due to Volatility")
                
        sector_impacts[sector] = {
            "impact": impact,
            "reasons": reason
        }
        
    # Alias Mapping (Manual Fixes for yfinance variances)
    # Consumer Cyclical -> Consumer Discretionary
    if "Consumer Discretionary" in sector_impacts:
        sector_impacts["Consumer Cyclical"] = sector_impacts["Consumer Discretionary"]

    return {
        "indicators": {
            "rates": trends["^TNX"],
            "oil": trends["CL=F"],
            "gold": trends["GC=F"],
            "vix": trends["^VIX"]
        },
        "sector_impacts": sector_impacts
    }
