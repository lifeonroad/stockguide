import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from cache_utils import timed_cache

# Import rate limiting
from rate_limiter import get_rate_limiter

# Major Indices and Sector ETFs with Descriptions
SYMBOLS = {
    'SPY': {'name': 'S&P 500', 'desc': 'Track the 500 largest US companies. The "Market" barometor.'},
    'QQQ': {'name': 'Nasdaq 100', 'desc': 'Tech-heavy index. High growth, high volatility.'},
    'IWM': {'name': 'Russell 2000', 'desc': 'Small-cap companies. Sensitive to interest rates.'},
    'XLK': {'name': 'Technology', 'desc': 'Apple, Microsoft, Nvidia. The engine of modern growth.'},
    'XLF': {'name': 'Financials', 'desc': 'Banks and Insurance. Benefits from higher rates.'},
    'XLV': {'name': 'Healthcare', 'desc': 'Defensive sector. Hospitals and Pharma.'},
    'XLE': {'name': 'Energy', 'desc': 'Oil and Gas. Tied to commodity prices.'},
    'XLY': {'name': 'Consumer Disc', 'desc': 'Amazon, Tesla. Luxury and discretionary spending.'},
    'XLI': {'name': 'Industrials', 'desc': 'Manufacturing and Transport. Economic backbone.'},
    'XLP': {'name': 'Consumer Staples', 'desc': 'Food and Essentials. Defensive during recessions.'},
    'XLB': {'name': 'Materials', 'desc': 'Mining and Chemicals. Early cycle performance.'},
    'XLU': {'name': 'Utilities', 'desc': 'Power and Water. High yield, low growth.'},
    'XLRE': {'name': 'Real Estate', 'desc': 'REITs and Property. Highly sensitive to yields.'}
}

def calculate_cmf(df, period=10):
    """Calculates Chaikin Money Flow: Sum(MFV)/Sum(Volume)"""
    # Money Flow Multiplier = [(Close - Low) - (High - Close)] / (High - Low)
    # If High == Low, Multiplier is 0
    multiplier = np.where(df['High'] != df['Low'], 
                          ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low']), 
                          0)
    mfv = multiplier * df['Volume']
    cmf = mfv.rolling(window=period).sum() / df['Volume'].rolling(window=period).sum()
    return cmf

@timed_cache(ttl_seconds=3600, soft_ttl_seconds=2700)  # 1h hard, 45m soft (SWR)
def get_money_flow_data():
    """
    Analyzes institutional money flow using Chaikin Money Flow (CMF) 
    and Relative Volume (RVOL) over the last 10 days.
    """
    results = []
    
    # Try DB-first for price history (25d of data)
    from persistent_cache import get_price_history_cached, save_price_history
    from datetime import datetime, timedelta
    
    for symbol, meta in SYMBOLS.items():
        try:
            # DB-first: read cached history
            hist_rows = get_price_history_cached(symbol, days=30)
            
            if hist_rows and len(hist_rows) >= 20:
                import pandas as pd
                df = pd.DataFrame(hist_rows)
                df.set_index(pd.to_datetime(df['date']), inplace=True)
                df.sort_index(inplace=True)
                df.columns = [c.capitalize() for c in df.columns]
            else:
                # Check rate limiter before yfinance call
                limiter = get_rate_limiter()
                can_fetch, reason = limiter.can_fetch(symbol, "history")
                
                if not can_fetch:
                    print(f"[MoneyFlow] Rate limited for {symbol}: {reason}")
                    continue  # Skip this symbol, use next
                
                tickers = yf.Tickers(' '.join(SYMBOLS.keys()))
                ticker = tickers.tickers[symbol]
                df = ticker.history(period="25d")
                if len(df) < 20:
                    continue
                
                # Record fetch for rate limiting
                limiter.record_fetch(symbol, "history")
                
                # Save to DB for future use
                if len(df) >= 20:
                    rows = []
                    for idx, row in df.iterrows():
                        rows.append({
                            "date": idx.strftime("%Y-%m-%d"),
                            "open": float(row['Open']),
                            "high": float(row['High']),
                            "low": float(row['Low']),
                            "close": float(row['Close']),
                            "volume": float(row['Volume']),
                        })
                    save_price_history(symbol, rows)
            
            # Calculate CMF
            df['CMF'] = calculate_cmf(df)
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 1. Chaikin Money Flow (Institutional indicator)
            # CMF > 0 is accumulation, < 0 is distribution
            cmf_val = latest['CMF']
            
            # 2. Relative Volume (RVOL)
            avg_vol = df['Volume'].iloc[-10:-1].mean()
            rvol = latest['Volume'] / avg_vol
            
            # 3. Price Trend
            price_change_pct = ((latest['Close'] - prev['Close']) / prev['Close']) * 100
            
            # Logic: Combine CMF and Price Action for a score
            # Score 0-100. 50 is Neutral.
            # Industry Standard: CMF > 0.1 is strong accumulation. < -0.1 is strong distribution.
            
            score = 50 + (cmf_val * 200) # CMF is typically -0.5 to 0.5
            
            # Adjust by volume conviction
            if rvol > 1.5:
                # Amplify the score if volume is high
                if score > 50: score += 10
                else: score -= 10
            
            # Clamp score
            score = max(5, min(95, score))
            
            # Determine Sentiment
            if score > 65:
                sentiment = "Strong Accumulation" if rvol > 1.2 else "Accumulation"
            elif score < 35:
                sentiment = "Strong Distribution" if rvol > 1.2 else "Distribution"
            else:
                sentiment = "Neutral / Balancing"
                
            results.append({
                "symbol": symbol,
                "name": meta['name'],
                "description": meta['desc'],
                "price": round(latest['Close'], 2),
                "change_pct": round(price_change_pct, 2),
                "volume_ratio": round(rvol, 2),
                "cmf": round(cmf_val, 3),
                "sentiment": sentiment,
                "score": round(score),
                "status_color": "green" if score > 60 else ("red" if score < 40 else "gray")
            })
            
        except Exception as e:
            print(f"Error fetching money flow for {symbol}: {e}")
            continue
            
    # Sort by score (Bullish first)
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        "data": results,
        "last_updated": datetime.now().isoformat(),
        "notes": [
            "Chaikin Money Flow (CMF) measures institutional pressure by comparing where a stock closes relative to its daily range.",
            "High Conviction is signaled when high Volume (RVOL > 1.2) aligns with strong CMF (> 0.1).",
            "Strong Distribution on high volume often precedes a trend reversal or capitulation."
        ]
    }

if __name__ == "__main__":
    # Test
    data = get_money_flow_data()
    print(data)
