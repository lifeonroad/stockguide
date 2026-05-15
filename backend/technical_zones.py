"""
technical_zones.py — Technical Zone Scanner
=============================================
Scans the master universe and classifies each ticker into a granular
technical zone with actionable signals. Extends the legacy 3-zone system
(dip / institutional / public) to 6 actionable zones using SMA 9, SMA 50,
SMA 180, and RSI 14.

Zone Taxonomy (6 zones → 3 legacy groups)
------------------------------------------
    crash:             price < SMA 180  &  RSI <= 25      → STRONG_BUY  [dip]
    dip:               price < SMA 180  &  RSI > 25       → BUY          [dip]
    early_accumulation: SMA 180 <= price < SMA 50 & RSI < 40 → ACCUMULATE [institutional]
    institutional:     SMA 180 <= price < SMA 50 & RSI >= 40 → HOLD      [institutional]
    public:            price >= SMA 50 & price < SMA 9 & RSI <= 70 → HOLD [public]
    extended:          price >= SMA 50 & (price >= SMA 9 OR RSI > 70) → EXIT [public]

Architecture
-------------
- Cache-only: reads price history exclusively from SQLite persistent cache.
  No yfinance calls are made — the function relies on prior data collection
  (dip hunter, universe warming, or previous research lookups) having
  populated the DB. This avoids thread explosion from background refresh
  threads and keeps the scanner fast and stable even under rate limits.
- Cached with @timed_cache (1800s hard, 900s soft TTL).

Performance
-----------
- All data in SQLite: < 2s for 600 tickers.
- Partial data (some tickers missing): those are silently skipped.
"""

import logging

logger = logging.getLogger(__name__)

from cache_utils import timed_cache


def _classify_zone(close, sma_9, sma_50, sma_180, rsi):
    """
    Classify a ticker into the 6-zone system.

    Returns
    -------
    tuple of (zone: str, detailed_zone: str, signal: str, action: str, reasons: list)
        zone:           legacy 3-zone name for backward compatibility
        detailed_zone:  6-zone classification name
        signal:         STRONG_BUY / BUY / ACCUMULATE / HOLD / EXIT
        action:         human-readable action text
        reasons:        list of explanatory strings
    """
    if close is None:
        return "unknown", "unknown", "NO_DATA", "No Data", ["No price data available"]

    reasons = []

    if sma_180 is not None and close < sma_180:
        pct_below = round(((close - sma_180) / sma_180) * 100, 1)
        reasons.append(f"Price ${close:.2f} is {abs(pct_below):.1f}% below SMA 180 (${sma_180:.2f})")

        if rsi is not None and rsi <= 25:
            reasons.append(f"RSI {rsi:.1f} is deeply oversold — extreme panic")
            return "dip", "crash", "STRONG_BUY", "Aggressive Accumulate", reasons
        else:
            if rsi is not None and rsi < 40:
                reasons.append(f"RSI {rsi:.1f} is approaching oversold")
            return "dip", "dip", "BUY", "Accumulate", reasons

    if sma_50 is not None and close < sma_50:
        pct_below = round(((close - sma_50) / sma_50) * 100, 1)
        msg = f"Price ${close:.2f} is {abs(pct_below):.1f}% below SMA 50 (${sma_50:.2f})"
        if sma_180 is not None:
            msg += f" and above SMA 180 (${sma_180:.2f})"
        reasons.append(msg)

        if rsi is not None and rsi < 40:
            reasons.append(f"RSI {rsi:.1f} — early accumulation zone")
            return "institutional", "early_accumulation", "ACCUMULATE", "Start Position", reasons
        else:
            return "institutional", "institutional", "HOLD", "Hold", reasons

    if sma_50 is not None and close >= sma_50:
        pct_above = round(((close - sma_50) / sma_50) * 100, 1)
        reasons.append(f"Price ${close:.2f} is {pct_above:.1f}% above SMA 50 (${sma_50:.2f})")

        is_extended = False
        if sma_9 is not None and close >= sma_9:
            reasons.append(f"Price at or above SMA 9 (${sma_9:.2f}) — extended")
            is_extended = True
        if rsi is not None and rsi > 70:
            reasons.append(f"RSI {rsi:.1f} is overbought (>70)")
            is_extended = True

        if is_extended:
            return "public", "extended", "EXIT", "Take Profit / Exit", reasons
        else:
            return "public", "public", "HOLD", "Trim Partial", reasons

    if sma_180 is not None and close >= sma_180:
        return "public", "public", "HOLD", "Hold", ["Price above SMA 180"]
    return "unknown", "unknown", "NO_DATA", "No Data", ["Cannot classify — insufficient SMA data"]


def _pct_diff(val1, val2):
    if val1 is None or val2 is None or val2 == 0:
        return None
    return round(((val1 - val2) / val2) * 100, 2)


def _get_cached_price_data(symbol, min_days):
    """
    Fetch cached price history from SQLite only — no yfinance calls.
    Returns (closes_series, price, sma_9, sma_50, sma_180, rsi) or (None,)*6.
    """
    from indicators import calculate_rsi, calculate_sma
    from persistent_cache import get_price_history_cached

    try:
        rows = get_price_history_cached(symbol, min_days)
        if not rows or len(rows) < 50:
            return None, None, None, None, None, None

        import pandas as pd
        df = pd.DataFrame(rows)
        if "close" not in df.columns:
            return None, None, None, None, None, None

        closes = df["close"].dropna()
        if len(closes) < 50:
            return None, None, None, None, None, None

        price = float(closes.iloc[-1])
        sma_9 = calculate_sma(closes, 9)
        sma_50 = calculate_sma(closes, 50)
        sma_180 = calculate_sma(closes, 180)
        rsi = calculate_rsi(closes, 14)

        return closes, price, sma_9, sma_50, sma_180, rsi
    except Exception as exc:
        logger.debug("Error reading cached data for %s: %s", symbol, exc)
        return None, None, None, None, None, None


@timed_cache(ttl_seconds=1800, soft_ttl_seconds=900)
def scan_technical_zones(zone_filter="all", min_data_days=200):
    """
    Scan the master universe and classify tickers into technical zones.

    Uses ONLY cached SQLite data — no network calls. This means tickers
    without cached price history are silently skipped. Run the dip hunter
    or universe warming first to populate the cache.

    Parameters
    ----------
    zone_filter : str
        One of "all", "dip", "institutional", "public", or a detailed zone name.
        When "all", returns all classified tickers.
    min_data_days : int
        Minimum trading days of price history required to classify.

    Returns
    -------
    list of dict
        Each entry: {symbol, zone, detailed_zone, signal, action, reasons,
                     price, sma_9, sma_50, sma_180, rsi_14,
                     pct_to_sma_50, pct_to_sma_180}
        Sorted by signal strength (strongest buy signals first).
        Backward compatible: legacy `zone` field still present.
    """
    from universe import get_master_universe

    symbols = get_master_universe()

    detailed_zones_all = {"crash", "dip", "early_accumulation", "institutional", "public", "extended", "unknown"}
    legacy_zones = {"dip", "institutional", "public"}

    results = []
    for symbol in symbols:
        try:
            closes, price, sma_9, sma_50, sma_180, rsi = _get_cached_price_data(symbol, min_data_days)
            if closes is None:
                continue

            zone, detailed_zone, signal, action, reasons = _classify_zone(price, sma_9, sma_50, sma_180, rsi)
            if zone is None or zone == "unknown":
                continue

            results.append({
                "symbol": symbol,
                "zone": zone,
                "detailed_zone": detailed_zone,
                "signal": signal,
                "action": action,
                "reasons": reasons,
                "price": round(price, 2),
                "sma_9": round(sma_9, 2) if sma_9 is not None else None,
                "sma_50": round(sma_50, 2) if sma_50 is not None else None,
                "sma_180": round(sma_180, 2) if sma_180 is not None else None,
                "rsi_14": round(rsi, 1),
                "pct_to_sma_50": _pct_diff(price, sma_50),
                "pct_to_sma_180": _pct_diff(price, sma_180),
            })
        except Exception as exc:
            logger.debug("Failed to classify %s: %s", symbol, exc)
            continue

    signal_order = {"STRONG_BUY": 0, "BUY": 1, "ACCUMULATE": 2, "HOLD": 3, "EXIT": 4, "NO_DATA": 5}
    results.sort(key=lambda r: signal_order.get(r["signal"], 99))

    if zone_filter != "all":
        if zone_filter in legacy_zones:
            results = [r for r in results if r["zone"] == zone_filter]
        elif zone_filter in detailed_zones_all:
            results = [r for r in results if r["detailed_zone"] == zone_filter]
        else:
            results = [r for r in results if r["zone"] == zone_filter]

    return results
