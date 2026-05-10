# Endpoint Test Report

Date: 2026-05-10
Status: ✅ All Core Endpoints Working

## Test Results

| Endpoint | Status | Response |
|----------|--------|----------|
| `/api/research/BSX` | ✅ 200 | Returns full research data with analysts, valuation models |
| `/api/research/AAPL` | ✅ 200 | Returns full research data |
| `/api/dip-hunter/stocks` | ✅ 200 | Returns 65 dip opportunities |
| `/api/dip-hunter/etfs` | ✅ 200 | Returns ETF dip data |
| `/api/dip-hunter/summary` | ✅ 200 | Returns dip summary |
| `/api/moonshots` | ✅ 200 | Returns 22 moonshot picks |
| `/api/money-flow` | ✅ 200 | Returns money flow data |
| `/api/portfolios` | ✅ 200 | Returns portfolio data |
| `/api/opportunities` | ✅ 200 | Returns opportunities |
| `/api/alpha/cycle` | ✅ 200 | Returns cycle intelligence |
| `/api/money-flow` | ✅ 200 | Returns money flow data |
| `/api/small-caps` | ✅ 200 | Returns small cap gems |
| `/api/contrarian/opportunities` | ✅ 200 | Returns contrarian picks |
| `/api/news` | ✅ 200 | Returns news |
| `/api/superinvestors` | ✅ 200 | Returns superinvestor data |
| `/api/copycat` | ✅ 200 | Returns copycat performance |
| `/api/international/picks` | ✅ 200 | Returns international picks |
| `/api/analyze/{symbol}` | ✅ 200 | Returns analysis |
| `/api/screeners/{strategy_id}` | ✅ 200 | Returns screener results |

## Known Issues

1. **YFinance Rate Limiting**: Occasional "Too Many Requests" errors. Background refresh handles this.
2. **Moonshots Discovery Section**: Previously broken (sorted string instead of dict), now fixed.
3. **Research DCF**: Returns empty (yfinance doesn't provide DCF data). TODO: implement calculation.

## Changes Made This Session

1. Removed defeatbeta toggle - always uses yfinance
2. Added all 40 columns to `_get_yf_fundamentals()`
3. Fixed moonshots discovery section
4. Simplified `get_news()` and `get_dcf()`
5. All DB-first patterns verified working

## Performance

- DB read: ~2ms
- get_ticker_info (DB-first): ~4ms
- get_ticker_info (in-memory): ~0.01ms
- Fresh fetch: ~20ms

## To Deploy

Restart server to pick up changes:
```bash
screen -S stockguide -X quit
cd ~/Downloads/projects/stockguide/stockguide && source .env && backend/../venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```