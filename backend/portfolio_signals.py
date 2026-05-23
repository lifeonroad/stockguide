"""
Portfolio Signals — technical analysis signals for portfolio positions.
Computes SMA/RSI/zones per position using cached price history (no network calls).
"""

import logging
import math
import threading
import numpy as np
from typing import List, Dict, Optional
from persistent_cache import get_price_history_cached, get_ticker_info_cached

log = logging.getLogger(__name__)

# Known NEO CDRs (Canadian Depositary Receipts) — trade in CAD on NEO exchange
NEO_CDRS = {
    'AMZN', 'AAPL', 'GOOG', 'GOOGL', 'MSFT', 'TSLA', 'NFLX', 'META', 'NVDA',
    'PFE', 'DIS', 'V', 'MA', 'PYPL', 'JPM', 'BAC', 'WMT', 'HD', 'COST',
    'PG', 'JNJ', 'KO', 'PEP', 'MCD', 'SBUX', 'NKE', 'INTC', 'AMD', 'IBM', 'ABNB'
}

# Known TSX stocks
TSX_STOCKS = {
    'TD', 'RY', 'BNS', 'BMO', 'CM', 'ENB', 'TRP', 'CNQ', 'SU', 'ATD', 'CSU',
    'SHOP', 'BCE', 'T', 'NA', 'CP', 'CNR', 'BAM', 'SLF', 'MFC', 'TRI', 'GIB.A',
    'DOL', 'POW', 'QSR', 'FTS', 'EMA', 'AEM', 'WPM', 'K', 'CCO', 'FM', 'TECK.B',
    'RCI.B', 'L', 'WN', 'MRU', 'SAP', 'BYD', 'AC', 'AQN', 'CAR.UN', 'REI.UN',
    'VFV', 'VCN', 'VUN', 'XQQ', 'XIU', 'XIC', 'ZSP', 'ZEB', 'HMMJ', 'HIVE', 'BTCC', 'KILO',
    'TA', 'MG', 'NPI'
}

# Crypto tickers that need -CAD suffix
CRYPTO_TICKERS = {'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT', 'LINK', 'MATIC'}


def _resolve_quote_symbol(ticker: str, currency: str = 'USD') -> str:
    """Resolve a ticker to its Yahoo Finance quote symbol (mirrors frontend logic)."""
    t = ticker.upper()
    is_cad = currency == 'CAD'

    if '.' in t:
        return t

    if is_cad:
        if t in NEO_CDRS:
            return f'{t}.NE'
        if t in TSX_STOCKS:
            return f'{t}.TO'
        if t in CRYPTO_TICKERS:
            return f'{t}-CAD'

    return t


def compute_signals_for_portfolio(portfolio_id: str, pm) -> Dict:
    """
    Compute technical analysis signals for all positions in a portfolio.
    Uses cached price history — no network calls.
    Background-warms any tickers missing from cache.
    """
    portfolio = pm.get_portfolio(portfolio_id)
    if not portfolio:
        return {'error': 'Portfolio not found'}

    positions = portfolio.get('positions', [])
    results = []
    needs_warm = []

    for pos in positions:
        ticker = pos.get('ticker', '').upper()
        currency = pos.get('currency', 'USD')
        quantity = pos.get('quantity', 0)
        avg_cost = pos.get('avg_cost', 0)

        if not ticker or quantity <= 0:
            continue

        query_symbol = _resolve_quote_symbol(ticker, currency)

        info = get_ticker_info_cached(ticker)
        if not info:
            info = get_ticker_info_cached(query_symbol)

        if info and info.get('price'):
            current_price = info['price']
        else:
            needs_warm.append(ticker)
            if query_symbol != ticker:
                needs_warm.append(query_symbol)
            continue

        history = get_price_history_cached(query_symbol, 500)
        if not history:
            history = get_price_history_cached(ticker, 500)

        if not history or len(history) < 15:
            needs_warm.append(ticker)
            if query_symbol != ticker:
                needs_warm.append(query_symbol)

        try:
            signal = _compute_single_signal(ticker, query_symbol)
            if signal:
                signal['quantity'] = quantity
                signal['avg_cost'] = avg_cost
                signal['currency'] = currency
                signal['cost_basis'] = quantity * avg_cost
                signal['position_value'] = quantity * signal['current_price']
                results.append(signal)
        except Exception as e:
            log.warning('Signal computation failed for %s: %s', ticker, e)
            results.append({
                'ticker': ticker,
                'currency': currency,
                'signal': 'NO_DATA',
                'zone': 'unknown',
                'error': str(e),
            })

    if needs_warm:
        _warm_background(list(set(needs_warm)))

    summary = _compute_summary(results)

    results = [_clean_nans(s) for s in results]
    return {'signals': results, 'summary': summary}


def _warm_background(symbols: List[str]):
    """Warm cache for symbols in a background daemon thread (no network in request)."""
    if not symbols:
        return
    try:
        from data_client import warm_db_for_symbols
        def _worker():
            log.info('Background warming %d portfolio tickers...', len(symbols))
            warm_db_for_symbols(symbols)
            log.info('Background warming complete for %d tickers', len(symbols))
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    except ImportError as e:
        log.warning('Could not import warm_db_for_symbols: %s', e)


def _clean_nans(d: dict) -> dict:
    """Replace numpy NaN/Inf with None for JSON serialization."""
    cleaned = {}
    for k, v in d.items():
        if isinstance(v, dict):
            cleaned[k] = _clean_nans(v)
        elif isinstance(v, (np.floating, float)) and (math.isnan(v) or math.isinf(v)):
            cleaned[k] = None
        elif isinstance(v, np.floating):
            cleaned[k] = float(v) if not (math.isnan(v) or math.isinf(v)) else None
        else:
            cleaned[k] = v
    return cleaned


def _compute_single_signal(ticker: str, query_symbol: str) -> Optional[Dict]:
    """Compute SMA/RSI/zone for one position using ONLY cached DB data (no network)."""

    info = get_ticker_info_cached(ticker)
    if not info:
        info = get_ticker_info_cached(query_symbol)
    current_price = (info or {}).get('price')

    if not current_price:
        return None

    history = get_price_history_cached(query_symbol, 500)
    if not history:
        history = get_price_history_cached(ticker, 500)

    sma_9_val = _calc_sma(history, 9)
    sma_50_val = _calc_sma(history, 50)
    sma_200_val = _calc_sma(history, 200)
    rsi_14 = _calc_rsi(history, 14)

    zone, detailed_zone, signal, action, reasons = _classify_zone(current_price, sma_9_val, sma_50_val, sma_200_val, rsi_14)

    volume_ratio = _get_volume_ratio(ticker, query_symbol)
    if volume_ratio is not None and volume_ratio > 2.0:
        reasons.append(f'Volume {volume_ratio:.1f}x average — unusual activity')

    return {
        'ticker': ticker,
        'current_price': round(current_price, 2),
        'sma_9': sma_9_val,
        'sma_50': sma_50_val,
        'sma_200': sma_200_val,
        'rsi_14': rsi_14,
        'zone': zone,
        'detailed_zone': detailed_zone,
        'signal': signal,
        'action': action,
        'volume_ratio': round(volume_ratio, 2) if volume_ratio else None,
        'reasons': reasons,
    }


def _calc_sma(history, period: int) -> Optional[float]:
    """Calculate SMA from cached history. No network calls."""
    if not history or len(history) < period:
        return None
    closes = [h.get('close') for h in history[-period:] if h.get('close')]
    if len(closes) < period:
        return None
    return round(sum(closes) / period, 2)


def _calc_rsi(history, period: int = 14) -> Optional[float]:
    """Calculate RSI from cached history. No network calls."""
    if not history or len(history) < period + 1:
        return None
    closes = [h['close'] for h in history if h.get('close') is not None]
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)



def _classify_zone(price: float, sma_9: Optional[float], sma_50: Optional[float],
                   sma_200: Optional[float], rsi_14: Optional[float]):
    """
    Classify price zone into the 6-zone system.

    Returns (zone, detailed_zone, signal, action, reasons).
        zone:           legacy 3-zone name for backward compatibility
        detailed_zone:  crash / dip / early_accumulation / institutional / public / extended
        signal:         STRONG_BUY / BUY / ACCUMULATE / HOLD / EXIT / NO_DATA
        action:         human-readable action text
        reasons:        list of explanatory strings
    """
    reasons = []
    zone = 'unknown'
    detailed_zone = 'unknown'
    signal = 'HOLD'
    action = 'Hold'

    if sma_50 is not None and sma_200 is not None:
        if price < sma_200:
            zone = 'dip'
            reasons.append(f'Price ${price:.2f} below SMA-200 (${sma_200:.2f})')
            if rsi_14 is not None and rsi_14 <= 25:
                detailed_zone = 'crash'
                signal = 'STRONG_BUY'
                action = 'Aggressive Accumulate'
                reasons.append(f'RSI {rsi_14} — deeply oversold, extreme panic')
            else:
                detailed_zone = 'dip'
                signal = 'BUY'
                action = 'Accumulate'
                if rsi_14 is not None and rsi_14 < 40:
                    reasons.append(f'RSI {rsi_14} — approaching oversold')
        elif price < sma_50:
            zone = 'institutional'
            reasons.append(f'Price ${price:.2f} between SMA-50 (${sma_50:.2f}) and SMA-200 (${sma_200:.2f})')
            if rsi_14 is not None and rsi_14 < 40:
                detailed_zone = 'early_accumulation'
                signal = 'ACCUMULATE'
                action = 'Start Position'
                reasons.append(f'RSI {rsi_14} — early accumulation zone')
            else:
                detailed_zone = 'institutional'
                signal = 'HOLD'
                action = 'Hold'
        else:
            zone = 'public'
            reasons.append(f'Price ${price:.2f} above SMA-50 (${sma_50:.2f})')
            is_extended = False
            if sma_9 is not None and price >= sma_9:
                reasons.append(f'Price at or above SMA-9 (${sma_9:.2f}) — extended')
                is_extended = True
            if rsi_14 is not None and rsi_14 > 70:
                reasons.append(f'RSI {rsi_14} — overbought')
                is_extended = True
            if is_extended:
                detailed_zone = 'extended'
                signal = 'EXIT'
                action = 'Take Profit / Exit'
            else:
                detailed_zone = 'public'
                signal = 'HOLD'
                action = 'Trim Partial'
    elif sma_50 is not None:
        if price > sma_50:
            zone = 'public'
            detailed_zone = 'public'
            signal = 'HOLD'
            action = 'Trim Partial'
            reasons.append(f'Price above SMA-50 (${sma_50:.2f})')
        else:
            zone = 'institutional'
            detailed_zone = 'institutional'
            signal = 'HOLD'
            action = 'Hold'
            reasons.append(f'Price below SMA-50 (${sma_50:.2f})')
    else:
        zone = 'no_data'
        detailed_zone = 'unknown'
        signal = 'NO_DATA'
        action = 'No Data'
        reasons.append('Insufficient price history for SMA calculation')

    return zone, detailed_zone, signal, action, reasons


def _get_volume_ratio(ticker: str, query_symbol: str) -> Optional[float]:
    """Compare recent avg volume to the stored avg_volume."""
    info = get_ticker_info_cached(ticker)
    if not info:
        info = get_ticker_info_cached(query_symbol)
    if not info:
        return None
    avg_vol = info.get('avg_volume')
    if not avg_vol or avg_vol <= 0:
        return None

    history = get_price_history_cached(query_symbol, 20)
    if history and len(history) >= 5:
        recent = sum(h.get('volume', 0) or 0 for h in history[-5:]) / 5
        if recent > 0:
            return recent / avg_vol

    return None


def _compute_summary(signals: List[Dict]) -> Dict:
    summary = {
        'total': len(signals),
        'strong_buy': 0,
        'accumulate': 0,
        'hold': 0,
        'exit': 0,
        'no_data': 0,
    }
    for s in signals:
        sig = s.get('signal', 'NO_DATA').lower()
        if sig in summary:
            summary[sig] += 1
        else:
            summary['no_data'] += 1
    return summary
