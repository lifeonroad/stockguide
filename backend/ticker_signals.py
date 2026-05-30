"""Entry/exit value suggestions for any ticker.
Combines technical levels, RSI, analyst targets, and 52w range into actionable zones.
"""
from data_client import get_ticker_info
from cache_utils import timed_cache
from indicators import get_research_indicators


def _safe(val, default=0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


@timed_cache(ttl_seconds=86400, soft_ttl_seconds=3600)
def get_ticker_signals(symbol: str) -> dict:
    symbol = symbol.upper()

    info = get_ticker_info(symbol)
    if not info:
        return {"symbol": symbol, "error": "No ticker data available"}

    price = _safe(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    wk_52_high = _safe(info.get("fiftyTwoWeekHigh"))
    wk_52_low = _safe(info.get("fiftyTwoWeekLow"))
    target_high = _safe(info.get("targetHighPrice") or info.get("targetPriceHigh"))
    target_low = _safe(info.get("targetLowPrice") or info.get("targetPriceLow"))
    target_mean = _safe(info.get("targetMeanPrice") or info.get("targetPriceMean"))
    eps = _safe(info.get("epsTrailingTwelveMonths") or info.get("trailingEps"))

    if not price:
        return {"symbol": symbol, "error": "No price data available"}

    indicators = get_research_indicators(symbol)
    rsi = indicators.get("rsi")
    sma_50 = _safe(indicators.get("sma_50"))
    sma_180 = _safe(indicators.get("sma_180"))

    entries = []
    exits = []
    signals = []

    # --- Support levels (entry zones) ---
    if wk_52_low and price > wk_52_low:
        pct_from_low = round((price - wk_52_low) / wk_52_low * 100, 1)
        distance = round((price - wk_52_low) / price * 100, 1)
        entries.append({"level": "52w Low", "price": round(wk_52_low, 2), "distance_pct": distance})
        if pct_from_low < 10:
            signals.append({"type": "entry", "strength": "strong", "source": "Near 52w Low"})
        elif pct_from_low < 20:
            signals.append({"type": "entry", "strength": "moderate", "source": "Near 52w Low"})

    if sma_180 and price < sma_180:
        entries.append({"level": "SMA 180", "price": round(sma_180, 2), "distance_pct": round((sma_180 - price) / price * 100, 1)})
        signals.append({"type": "entry", "strength": "moderate", "source": "Below SMA 180"})

    if sma_50 and price < sma_50:
        entries.append({"level": "SMA 50", "price": round(sma_50, 2), "distance_pct": round((sma_50 - price) / price * 100, 1)})

    if target_low and target_mean and price < target_low:
        entries.append({"level": "Analyst Low", "price": round(target_low, 2), "distance_pct": round((target_low - price) / price * 100, 1)})
        signals.append({"type": "entry", "strength": "moderate", "source": "Below Analyst Low"})

    if rsi is not None and rsi <= 35:
        entries.append({"level": "RSI", "price": round(price, 2), "distance_pct": 0, "note": f"RSI={rsi} oversold"})
        signals.append({"type": "entry", "strength": "strong" if rsi <= 25 else "moderate", "source": f"RSI={rsi}"})

    # --- Resistance levels (exit zones) ---
    if target_mean and price < target_mean:
        upside = round((target_mean - price) / price * 100, 1)
        exits.append({"level": "Analyst Target", "price": round(target_mean, 2), "distance_pct": upside})
        if upside < 5:
            signals.append({"type": "exit", "strength": "strong", "source": "Near Analyst Target"})

    if wk_52_high and price < wk_52_high:
        distance = round((wk_52_high - price) / price * 100, 1)
        exits.append({"level": "52w High", "price": round(wk_52_high, 2), "distance_pct": distance})
        if distance < 10:
            signals.append({"type": "exit", "strength": "strong", "source": "Near 52w High"})

    if rsi is not None and rsi >= 65:
        exits.append({"level": "RSI", "price": round(price, 2), "distance_pct": 0, "note": f"RSI={rsi} overbought"})
        signals.append({"type": "exit", "strength": "strong" if rsi >= 75 else "moderate", "source": f"RSI={rsi}"})

    if sma_50 and price > sma_50:
        exits.append({"level": "SMA 50", "price": round(sma_50, 2), "distance_pct": round((price - sma_50) / price * 100, 1)})

    # --- Overall ---
    entry_score = sum(3 if s["strength"] == "strong" else 1 for s in signals if s["type"] == "entry")
    exit_score = sum(3 if s["strength"] == "strong" else 1 for s in signals if s["type"] == "exit")

    if entry_score >= exit_score * 1.5:
        overall = {"signal": "Strong Buy", "score": entry_score - exit_score, "detail": "Multiple entry signals detected"}
    elif entry_score > exit_score:
        overall = {"signal": "Buy", "score": entry_score - exit_score, "detail": "Entry signals outweigh exit signals"}
    elif exit_score >= entry_score * 1.5:
        overall = {"signal": "Strong Sell", "score": exit_score - entry_score, "detail": "Multiple exit signals detected"}
    elif exit_score > entry_score:
        overall = {"signal": "Sell", "score": exit_score - entry_score, "detail": "Exit signals outweigh entry signals"}
    else:
        overall = {"signal": "Hold", "score": 0, "detail": "No strong signals"}

    best_entry = min((e["price"] for e in entries), default=None)
    best_exit = max((e["price"] for e in exits), default=None)
    risk_reward = None
    if best_entry and best_exit and price:
        risk = price - best_entry
        reward = best_exit - price
        if risk > 0:
            risk_reward = round(reward / risk, 2)

    return {
        "symbol": symbol,
        "current_price": round(price, 2),
        "rsi": rsi,
        "eps": eps,
        "entry_zone": sorted(entries, key=lambda e: e["price"]),
        "exit_zone": sorted(exits, key=lambda e: -e["price"]),
        "signals": signals,
        "overall": overall,
        "risk_reward_ratio": risk_reward,
        "entry_target": round(best_entry, 2) if best_entry else None,
        "exit_target": round(best_exit, 2) if best_exit else None,
    }
