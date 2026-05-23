"""
momentum.py — Momentum Investing & Trading Evaluation Engine
=============================================================
Scans US + Canadian master universe and scores each ticker on an 8-factor
momentum matrix (0–100). Returns ranked picks with configurable weights,
plus generates buy/watch/avoid signals.

Architecture
-------------
- Cache-only for hot path: reads price history from SQLite persistent cache.
  No yfinance calls during scoring — relies on prior data collection.
- Cached with @timed_cache (3600s hard, 1800s soft TTL).
- Configurable weights via dict param (allows frontend slider integration).

Zone Taxonomy
--------------
    STRONG_BUY:   score >= 80  — high-conviction momentum pick
    BUY:          score 65–79  — solid momentum setup
    WATCH:        score 50–64  — building momentum, monitor
    HOLD:         score 25–49  — weak or fading momentum
    AVOID:        score < 25   — negative momentum / risk
"""

import logging
import math

logger = logging.getLogger(__name__)

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple

from cache_utils import timed_cache


DEFAULT_WEIGHTS = {
    "roc_1m": 8,
    "rsi_dynamic": 8,
    "ema_10_proximity": 7,
    "volume_spike": 6,
    "price_above_ema_20": 6,
    "roc_6m": 10,
    "macd": 8,
    "sma_50_200": 9,
    "pct_off_52w_high": 8,
    "adx": 10,
    "di_strength": 5,
    "risk_penalty": -15,
}

CAN_TICKERS = [
    'TD', 'RY', 'BNS', 'BMO', 'CM', 'ENB', 'TRP', 'CNQ', 'SU', 'ATD', 'CSU',
    'SHOP', 'BCE', 'T', 'NA', 'CP', 'CNR', 'BAM', 'SLF', 'MFC', 'TRI', 'GIB.A',
    'DOL', 'POW', 'QSR', 'FTS', 'EMA', 'AEM', 'WPM', 'K', 'CCO', 'FM', 'TECK.B',
    'RCI.B', 'L', 'WN', 'MRU', 'SAP', 'BYD', 'AC', 'AQN', 'CAR.UN', 'REI.UN',
    'VFV', 'VCN', 'VUN', 'XQQ', 'XIU', 'XIC', 'ZSP', 'ZEB', 'HMMJ', 'HIVE',
    'TA', 'MG', 'NPI', 'ATD', 'FFH', 'GWO', 'MGA', 'OTEX', 'STLC', 'WCN',
]

NEO_CDRS = {
    'AMZN', 'AAPL', 'GOOG', 'GOOGL', 'MSFT', 'TSLA', 'NFLX', 'META', 'NVDA',
    'PFE', 'DIS', 'V', 'MA', 'PYPL', 'JPM', 'BAC', 'WMT', 'HD', 'COST',
    'PG', 'JNJ', 'KO', 'PEP', 'MCD', 'SBUX', 'NKE', 'INTC', 'AMD', 'IBM', 'ABNB',
}

CRYPTO_TICKERS = {'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT', 'LINK', 'MATIC'}


def _resolve_quote_symbol(ticker: str) -> str:
    t = ticker.upper()
    if t in NEO_CDRS:
        return f'{t}.NE'
    if t in CRYPTO_TICKERS:
        return f'{t}-CAD'
    if t in CAN_TICKERS or t.endswith('.TO') or t.endswith('.NE') or t.endswith('.V'):
        return t if ('.' in t) else f'{t}.TO'
    return t


def _build_universe() -> List[str]:
    from universe import get_master_universe
    symbols = set(get_master_universe())
    for t in CAN_TICKERS:
        symbols.add(t)
    return sorted(symbols)


def _fetch_prices(symbol: str, min_days: int = 400) -> Optional[pd.DataFrame]:
    from persistent_cache import get_price_history_cached
    try:
        query_sym = _resolve_quote_symbol(symbol)
        rows = get_price_history_cached(query_sym, min_days)
        if not rows or len(rows) < 50:
            rows = get_price_history_cached(symbol, min_days)
        if not rows or len(rows) < 50:
            return None
        df = pd.DataFrame(rows)
        if "close" not in df.columns:
            return None
        df = df.dropna(subset=["close"])
        if len(df) < 50:
            return None
        return df
    except Exception as exc:
        logger.debug("Error fetching prices for %s: %s", symbol, exc)
        return None


def _score_rsi_dynamic(rsi: Optional[float]) -> float:
    if rsi is None:
        return 0
    if 45 <= rsi <= 65:
        return 100
    if 40 <= rsi < 45 or 65 < rsi <= 70:
        return 70
    if 30 <= rsi < 40 or 70 < rsi <= 75:
        return 40
    if rsi < 30:
        return 10
    return 0


def _score_volume_spike(df: pd.DataFrame) -> float:
    if "volume" not in df.columns:
        return 0
    volumes = df["volume"].dropna()
    if len(volumes) < 20:
        return 0
    vol_5 = volumes.iloc[-5:].mean()
    vol_20 = volumes.iloc[-20:].mean()
    if vol_20 == 0:
        return 0
    ratio = vol_5 / vol_20
    return min(ratio / 3, 1.0) * 100


def _score_sma_50_200(price: float, sma_50: Optional[float], sma_200: Optional[float]) -> float:
    if sma_50 is None or sma_200 is None:
        return 0
    if sma_50 > sma_200 and price > sma_50:
        return 100
    if sma_50 > sma_200:
        return 70
    if price > sma_50 and price > sma_200:
        return 50
    if price > sma_200:
        return 30
    return 0


def _score_52w_proximity(price: float, df: pd.DataFrame) -> float:
    closes = df["close"].dropna()
    if len(closes) < 252:
        closes_all = closes
    else:
        closes_all = closes.iloc[-252:]
    high_52w = closes_all.max()
    if high_52w == 0:
        return 0
    pct = price / high_52w
    if pct >= 0.97:
        return 100
    if pct >= 0.90:
        return 70
    if pct >= 0.80:
        return 40
    return 10


def _compute_momentum_score(
    roc_1m: Optional[float],
    roc_6m: Optional[float],
    rsi: Optional[float],
    macd_bullish: bool,
    macd_histogram: Optional[float],
    price: float,
    sma_50: Optional[float],
    sma_200: Optional[float],
    adx: Optional[float],
    plus_di: Optional[float],
    minus_di: Optional[float],
    ema_10: Optional[float],
    ema_20: Optional[float],
    volume_score: float,
    df: pd.DataFrame,
    weights: Dict[str, float],
) -> Tuple[float, str, str, List[str]]:
    reasons = []

    short_term = 0.0
    med_term = 0.0
    trend = 0.0
    risk = 0.0
    active_weight = 0.0

    w = weights

    if roc_1m is not None:
        st = min(max(roc_1m, 0), 25) / 25 * 100
        short_term += st * (w["roc_1m"] / 100)
        active_weight += w["roc_1m"]

    if rsi is not None:
        rsi_score = _score_rsi_dynamic(rsi)
        short_term += rsi_score * (w["rsi_dynamic"] / 100)
        active_weight += w["rsi_dynamic"]

    if ema_10 is not None and price > 0:
        prox = max(0, 1 - abs(price / ema_10 - 1) * 5) * 100
        short_term += prox * (w["ema_10_proximity"] / 100)
        active_weight += w["ema_10_proximity"]

    if volume_score > 0:
        short_term += volume_score * (w["volume_spike"] / 100)
        active_weight += w["volume_spike"]

    if ema_20 is not None and price > ema_20:
        short_term += 100 * (w["price_above_ema_20"] / 100)
    if ema_20 is not None:
        active_weight += w["price_above_ema_20"]

    if roc_6m is not None:
        mt = min(max(roc_6m, 0), 50) / 50 * 100
        med_term += mt * (w["roc_6m"] / 100)
        active_weight += w["roc_6m"]

    if macd_bullish:
        bonus = 100
        if macd_histogram is not None and macd_histogram > 0:
            bonus = 100
        med_term += bonus * (w["macd"] / 100)
    active_weight += w["macd"]

    sma_score = _score_sma_50_200(price, sma_50, sma_200)
    med_term += sma_score * (w["sma_50_200"] / 100)
    if sma_50 is not None and sma_200 is not None:
        active_weight += w["sma_50_200"]

    prox_52w = _score_52w_proximity(price, df)
    med_term += prox_52w * (w["pct_off_52w_high"] / 100)
    active_weight += w["pct_off_52w_high"]

    if adx is not None:
        adx_score = max(0, (adx - 25) / 25 * 100)
        trend += adx_score * (w["adx"] / 100)
        active_weight += w["adx"]

    if plus_di is not None and minus_di is not None and (plus_di + minus_di) > 0:
        di_strength = max(0, (plus_di - minus_di) / (plus_di + minus_di)) * 100
        trend += di_strength * (w["di_strength"] / 100)
        active_weight += w["di_strength"]

    closes = df["close"].dropna()
    if len(closes) >= 126:
        high_6m = closes.iloc[-126:].max()
        low_6m = closes.iloc[-126:].min()
        if high_6m > 0:
            drawdown = (high_6m - low_6m) / high_6m * 100
            if drawdown > 20:
                risk += 100 * (abs(w["risk_penalty"]) / 100)

    if len(closes) >= 252:
        returns = closes.pct_change().dropna()
        if len(returns) > 0:
            vol = returns.std() * (252 ** 0.5)
            if vol > 0.60:
                risk += 100 * (abs(w["risk_penalty"]) / 100)

    max_penalty = abs(w["risk_penalty"])

    raw_score = short_term + med_term + trend
    penalty = risk
    if active_weight > 0:
        normalized = (raw_score / active_weight * 100) - (penalty / max_penalty * 100) if max_penalty > 0 else (raw_score / active_weight * 100)
    else:
        normalized = 0

    final_score = max(0, min(100, normalized))

    if final_score >= 80:
        signal = "STRONG_BUY"
        action = "High-Conviction Pick"
        reasons.append(f"Momentum Score {final_score:.0f}/100 — strong momentum across timeframes")
    elif final_score >= 65:
        signal = "BUY"
        action = "Accumulate"
        reasons.append(f"Momentum Score {final_score:.0f}/100 — solid momentum setup")
    elif final_score >= 50:
        signal = "WATCH"
        action = "Monitor"
        reasons.append(f"Momentum Score {final_score:.0f}/100 — building momentum")
    elif final_score >= 25:
        signal = "HOLD"
        action = "Hold / Wait"
        reasons.append(f"Momentum Score {final_score:.0f}/100 — weak or fading momentum")
    else:
        signal = "AVOID"
        action = "Avoid / Exit"
        reasons.append(f"Momentum Score {final_score:.0f}/100 — negative momentum")

    if adx is not None and adx > 25:
        reasons.append(f"ADX {adx:.1f} — strong trend")
    if macd_bullish:
        reasons.append("MACD bullish — positive crossover")
    if sma_50 is not None and sma_200 is not None and sma_50 > sma_200:
        reasons.append("Golden cross (SMA 50 > SMA 200)")

    return final_score, signal, action, reasons


def _compute_single_momentum(symbol: str, df: pd.DataFrame, weights: Dict[str, float]) -> Optional[Dict]:
    from indicators import calculate_rsi, calculate_roc, calculate_macd, calculate_adx, calculate_ema

    try:
        closes = df["close"].dropna()
        if len(closes) < 50:
            return None

        price = float(closes.iloc[-1])

        roc_1m = calculate_roc(closes, 21)
        roc_3m = calculate_roc(closes, 63)
        roc_6m = calculate_roc(closes, 126)
        roc_12m = calculate_roc(closes, 252)
        rsi = calculate_rsi(closes, 14)

        macd = calculate_macd(closes)
        macd_bullish = macd["macd"] is not None and macd["signal"] is not None and macd["macd"] > macd["signal"]

        sma_50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None
        sma_200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None

        ema_10 = calculate_ema(closes, 10)
        ema_20 = calculate_ema(closes, 20)

        adx_result = None
        if "high" in df.columns and "low" in df.columns:
            highs = df["high"].dropna()
            lows = df["low"].dropna()
            if len(highs) >= 28 and len(lows) >= 28:
                adx_result = calculate_adx(highs, lows, closes, 14)

        adx = adx_result["adx"] if adx_result else None
        plus_di = adx_result["plus_di"] if adx_result else None
        minus_di = adx_result["minus_di"] if adx_result else None

        volume_score = _score_volume_spike(df)

        score, signal, action, reasons = _compute_momentum_score(
            roc_1m, roc_6m, rsi, macd_bullish, macd.get("histogram"),
            price, sma_50, sma_200, adx, plus_di, minus_di,
            ema_10, ema_20, volume_score, df, weights,
        )

        return {
            "symbol": symbol,
            "momentum_score": round(score, 1),
            "signal": signal,
            "action": action,
            "reasons": reasons,
            "price": round(price, 2),
            "roc_1m": round(roc_1m, 2) if roc_1m is not None else None,
            "roc_3m": round(roc_3m, 2) if roc_3m is not None else None,
            "roc_6m": round(roc_6m, 2) if roc_6m is not None else None,
            "roc_12m": round(roc_12m, 2) if roc_12m is not None else None,
            "rsi_14": round(rsi, 1),
            "macd_bullish": macd_bullish,
            "macd_histogram": round(macd["histogram"], 3) if macd["histogram"] is not None else None,
            "sma_50": round(sma_50, 2) if sma_50 is not None else None,
            "sma_200": round(sma_200, 2) if sma_200 is not None else None,
            "golden_cross": bool(sma_50 is not None and sma_200 is not None and sma_50 > sma_200),
            "ema_10": round(ema_10, 2) if ema_10 is not None else None,
            "ema_20": round(ema_20, 2) if ema_20 is not None else None,
            "adx": round(adx, 1) if adx is not None else None,
            "plus_di": round(plus_di, 1) if plus_di is not None else None,
            "minus_di": round(minus_di, 1) if minus_di is not None else None,
            "volume_ratio": round(_score_volume_spike(df) / 100 * 3, 2),
            "pct_off_52w_high": None,
        }
    except Exception as exc:
        logger.debug("Failed to compute momentum for %s: %s", symbol, exc)
        return None


@timed_cache(ttl_seconds=3600, soft_ttl_seconds=1800)
def scan_momentum_picks(
    min_score: float = 0,
    limit: int = 50,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    Scan US + Canadian universe and return momentum-ranked picks.

    Parameters
    ----------
    min_score : float
        Minimum momentum score (0–100) to include.
    limit : int
        Maximum number of picks to return.
    weights : dict, optional
        Custom weight configuration. Uses DEFAULT_WEIGHTS if None.

    Returns
    -------
    list of dict
        Ranked momentum picks sorted by score descending.
    """
    w = weights if weights else DEFAULT_WEIGHTS.copy()
    symbols = _build_universe()

    results = []
    for symbol in symbols:
        df = _fetch_prices(symbol, 400)
        if df is None:
            continue

        result = _compute_single_momentum(symbol, df, w)
        if result is None:
            continue

        if result["momentum_score"] < min_score:
            continue

        closes = df["close"].dropna()
        if len(closes) >= 252:
            high_52w = closes.iloc[-252:].max()
            if high_52w > 0:
                result["pct_off_52w_high"] = round((result["price"] / high_52w - 1) * 100, 2)

        results.append(result)

    results.sort(key=lambda r: r["momentum_score"], reverse=True)
    return results[:limit]
