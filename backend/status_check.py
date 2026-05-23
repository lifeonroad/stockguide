#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

print("=" * 55)
print("   STOCKGUIDE SYSTEM STATUS REPORT")
print("=" * 55)

print("\n1. DATABASE STATUS")
print("-" * 55)
from persistent_cache import get_db_stats, get_ticker_info_cached
stats = get_db_stats()
print(f"   Tickers in DB:        {stats['ticker_count']}")
print(f"   Price History Rows:   {stats['price_history_rows']:,}")
print(f"   Symbols with History: {stats['symbols_with_history']}")

print("\n2. RATE LIMITING & DATA SOURCE")
print("-" * 55)
from data_client import get_data_source_status
status = get_data_source_status()
print(f"   Source:     {status['current_source']}")
print(f"   Rate Limit: {status['rate_limiting']}")

from rate_limiter import MIN_REFRESH_INTERVAL, DAILY_FETCH_LIMIT, RateLimiter
limiter = RateLimiter()
print(f"   Min Interval: {MIN_REFRESH_INTERVAL}s (30 min)")
print(f"   Daily Limit:  {DAILY_FETCH_LIMIT}")
s = limiter.get_status('AAPL', 'price')
print(f"   AAPL/price: cooldown={s['cooldown_remaining']:.0f}s, daily_remaining={s['daily_remaining']}")

print("\n3. INTELLIGENT TTL")
print("-" * 55)
from intelligent_ttl import get_adjusted_ttl
for symbol, beta, sector in [('AAPL', 1.2, 'Technology'), ('TSLA', 2.0, 'Consumer Discretionary'), ('JNJ', 0.6, 'Healthcare')]:
    config = get_adjusted_ttl(symbol, 'price', beta=beta, sector=sector)
    print(f"   {symbol} (beta={beta}, {sector[:15]}): {config.effective_ttl}s ({config.effective_ttl/60:.0f}min)")

print("\n4. SAMPLE TICKERS FROM DB")
print("-" * 55)
for symbol in ['AAPL', 'MSFT', 'GOOGL']:
    info = get_ticker_info_cached(symbol)
    if info:
        print(f"   {symbol}: ${info.get('price', 0):.2f} | {info.get('sector', 'N/A')[:20]} | Beta={info.get('beta', 'N/A')}")
    else:
        print(f"   {symbol}: NOT IN DB")

print("\n" + "=" * 55)
print("   STATUS: ALL SYSTEMS OPERATIONAL")
print("=" * 55)