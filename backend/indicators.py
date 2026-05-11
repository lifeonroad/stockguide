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
        if 'close' not in df.columns:
            return None
        if 'date' in df.columns and 'report_date' not in df.columns:
            df = df.rename(columns={'date': 'report_date'})
        df = df.sort_values('report_date')
        return df
    except Exception:
        return None


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
