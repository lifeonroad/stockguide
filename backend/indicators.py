import pandas as pd
import numpy as np
import math
from typing import List, Dict, Optional, Tuple


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def calculate_sma(prices: pd.Series, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return float(prices.rolling(window=period).mean().iloc[-1])


def calculate_sma_array(prices: pd.Series, period: int) -> List[Optional[float]]:
    if len(prices) < period:
        return [None] * len(prices)
    sma = prices.rolling(window=period).mean()
    return [float(v) if not math.isnan(v) else None for v in sma]


def calculate_ema(prices: pd.Series, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return float(prices.ewm(span=period).mean().iloc[-1])


def get_price_history_for_indicators(symbol: str, min_days: int = 200) -> Optional[pd.DataFrame]:
    from data_client import get_price_history
    try:
        df = get_price_history(symbol, days=max(min_days, 252))
        if df is None or df.empty:
            return None
        # Use adjusted close for SMA calculations if present
        if 'adj_close' in df.columns:
            df['close'] = df['adj_close']
        elif 'adjclose' in df.columns:
            df['close'] = df['adjclose']
        elif 'Adj Close' in df.columns:
            df['close'] = df['Adj Close']
        elif 'close' not in df.columns:
            return None
        if 'date' in df.columns and 'report_date' not in df.columns:
            df = df.rename(columns={'date': 'report_date'})
        df = df.sort_values('report_date')
        return df
    except Exception:
        return None


def calculate_roc(prices: pd.Series, period: int = 21) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    current = float(prices.iloc[-1])
    prev = float(prices.iloc[-1 - period])
    if prev == 0:
        return None
    return ((current - prev) / prev) * 100


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    if len(prices) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return {
        "macd": float(macd_line.iloc[-1]),
        "signal": float(signal_line.iloc[-1]),
        "histogram": float(histogram.iloc[-1]),
    }


def calculate_adx(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> Dict:
    if len(highs) < period * 2 or len(lows) < period * 2 or len(closes) < period * 2:
        return {"adx": None, "plus_di": None, "minus_di": None}
    high = highs.astype(float)
    low = lows.astype(float)
    close = closes.astype(float)
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = ((plus_di - minus_di) / (plus_di + minus_di).replace(0, float('nan'))).abs() * 100
    adx = dx.rolling(window=period).mean()
    return {
        "adx": float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else None,
        "plus_di": float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else None,
        "minus_di": float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else None,
    }


def get_research_indicators(symbol: str) -> Dict:
    df = get_price_history_for_indicators(symbol, min_days=200)
    if df is None:
        return {"rsi": None, "sma_9": None, "sma_50": None, "sma_180": None}

    closes = df['close']
    result = {
        "rsi": round(calculate_rsi(closes, 14), 1),
        "sma_9": round(calculate_sma(closes, 9), 2) if calculate_sma(closes, 9) is not None else None,
        "sma_50": round(calculate_sma(closes, 50), 2) if calculate_sma(closes, 50) is not None else None,
        "sma_180": round(calculate_sma(closes, 180), 2) if calculate_sma(closes, 180) is not None else None,
    }

    sma_9_arr = calculate_sma_array(closes, 9)
    sma_50_arr = calculate_sma_array(closes, 50)
    sma_180_arr = calculate_sma_array(closes, 180)

    dates = df['report_date'].astype(str).tolist() if 'report_date' in df.columns else []
    prices = [round(float(c), 2) for c in closes]

    result["price_history"] = {
        "dates": dates,
        "prices": prices,
        "sma_9": [round(v, 2) if v is not None else None for v in sma_9_arr],
        "sma_50": [round(v, 2) if v is not None else None for v in sma_50_arr],
        "sma_180": [round(v, 2) if v is not None else None for v in sma_180_arr],
    }

    return result
