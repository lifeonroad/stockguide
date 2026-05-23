# Rational Equity Dashboard 📊

A self-hosted stock analysis SPA — FastAPI backend + vanilla JS frontend — aggregating data from Yahoo Finance, SEC EDGAR 13F filings, and Dataroma superinvestor portfolios.

## Quick Start

```bash
./start.sh
```

Or manually:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd stockguide && python3 run.py
```

Open **http://localhost:8000**

## Features

### 📈 Market Dashboard
- Real-time market status, Buffett indicator, macro trends
- Economic indicators (FRED), money flow analysis, news
- Market cycle analytics and technical support/resistance zones

### 🎯 Dip Hunter & Opportunities
- Multi-factor dip detection across 250+ ticker universe
- Market regime context-aware dip classification
- Per-sector dynamic universe scoring (18.5s scan)

### 🔭 Superinvestor Tracking
- **Superinvestors Tab** — Live 13F data from SEC EDGAR (free API)
- Detail modal with sector breakdown, QoQ changes, top moves
- Dataroma.com integration for ~82 tracked managers

### 👥 Guru Consensus
- Grand Portfolio aggregating all tracked superinvestors' holdings
- Views: Holdings, Qtr Buys/Sells, 6mo Buys/Sells, Sector allocation
- 6-month comparison column on quarter views
- **Consensus Picks** — Composite scoring (0-100) ranking stocks by sustained buying, ownership breadth, net manager activity, 52w low proximity, and portfolio weight

### 📊 Guru Flow Analytics
- Most Widely Held, Most Bought/Sold by manager count
- New Positions, Single-Manager Heavy Bets (>30% portfolio)
- Near 52w Low opportunities, Sector Rotation (net buying vs selling)
- Sustained Buying signals (quarter + 6-month confirmation)
- Sortable columns on all tables

### 📋 Copycat Portfolio
- Multi-manager overlap detection
- Filter by signal type (new buys, conviction up, exits, trims)
- Live from SEC EDGAR 13F filings

### 📊 Pro Screeners & Strategies
- Deep value, growth at reasonable price, Buffet/Burry/Lynch analysis
- Momentum investing (8-factor scoring engine)
- Moonshots (3/5/10 year horizon), Small Caps, International picks
- Contrarian opportunities, Inflation busters

### 💼 Portfolio Management
- CRUD portfolios with positions
- PDF/CSV import (WealthSimple format)
- Performance tracking

## Data Sources

| Source | Data | Cache TTL |
|---|---|---|
| Yahoo Finance / yahooquery | Price, fundamentals, analysis | Per-ticker rate limited (48/day) |
| SEC EDGAR | 13F filings (free, no API key) | Quarterly |
| Dataroma.com | Superinvestor portfolios, grand portfolio, activity | 720h (quarterly) |
| FRED | Economic indicators | Per-endpoint |

## Architecture

```
5-tier caching: Business Logic → DataOrchestrator → SQLite → RateLimiter → NetworkClient
```

- **timed_cache** — In-memory SWR with circuit breaker
- **SQLite persistent cache** — WAL mode, 3 tables, per-type staleness
- **RateLimiter** — 30min between fetches, 48/day per ticker
- **IntelligentTTL** — Adaptive by beta, earnings, market hours

## Deploy

Render.com free tier (1 worker, 4 threads, 120s timeout):
```bash
git push origin deploy
```

See `DEPLOYMENT.md` for details.

## Configuration

```bash
DEFEATBETA_ENABLED=0 python3 run.py   # yfinance/yahooquery only
DEFEATBETA_ENABLED=1 python3 run.py   # defeatbeta proxy (default)
```

## Troubleshooting

**Stale frontend?** Hard refresh `Ctrl+Shift+R`. JS version in `index.html` (`?v=N`).

**Port in use?** `lsof -ti:8000 | xargs kill -9`

**Yahoo rate limits after restart?** Wait 60s — background warming runs staggered.
