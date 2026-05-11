# Phase 1: Data Source Catalog

> **Status:** In Progress  
> **Objective:** Audit all network egress points and categorize by freshness tier

---

## 1. Network Egress Points by Module

### 1.1 yfinance Calls

| File | Function | Data Retrieved | Current Caching |
|------|----------|----------------|-----------------|
| `data_client.py` | `_get_yq_info()` | Fundamentals (PE, EPS, margins, market cap) | DB-backed, `_db_ticker()` |
| `data_client.py` | `_get_yf_fundamentals()` | Full fundamentals dict | DB-backed |
| `dip_hunter.py` | `yf.download()` | Price history (1y daily) | DB-first, 126 tickers cached |
| `dip_hunter.py` | `Ticker().price` | Current price check | Per-ticker lookup |
| `cycle_analytics.py` | `yf.download()` | 1y daily OHLCV for rotation | DB cache check first |
| `money_flow.py` | `yf.Ticker()` | Money flow indicators | Unknown |
| `screener.py` | `yf.download()` + `Ticker().info` | Screener fundamentals | None |
| `research.py` | `Ticker()` deep data | Warren Buffett metrics | DB layer present |
| `screeners.py` | `yf.download()` | Multi-ticker screening | None |
| `opportunity_engine.py` | `yf.Ticker().info` | Opportunity scoring | Unknown |
| `macro.py` | `yf.download()` | ^TNX, CL=F, GLD, ^VIX | 1h hard cache, 45m soft |
| `market_data.py` | `yf.download()` | S&P 500, market cap estimation | 30m cache |
| `analyst.py` | `Ticker().analysis` | Analyst recommendations | Unknown |
| `superinvestors_live.py` | `yf.download()` | Sector rotation | 1h cache |

### 1.2 Yahooquery Calls

| File | Function | Data Retrieved | Context |
|------|----------|----------------|---------|
| `data_client.py` | `_get_yq_info()` | Price, financial_data, key_stats, summary_detail, asset_profile | Called by `_get_yf_fundamentals()` |
| `dip_hunter.py` | `Ticker()` | Fundamentals, price data | Backup fetch path |
| `screener.py` | `Ticker()` | Multi-dimensional screening | Bulk screening |
| `research.py` | `Ticker()` | Deep fundamentals | Buffett-style analysis |

### 1.3 requests/httpx Calls

| File | Function | API Endpoint | Data Retrieved |
|------|----------|--------------|----------------|
| `updater.py` | `requests.get()` | FRED API (`fred/series/observations`) | GDP, economic indicators |
| `superinvestors_live.py` | `requests.get()` | Whale tracking APIs | Institutional holdings |
| `market_data.py` | `requests.get()` | FRED API | US GDP (quarterly) |
| `economic.py` | `requests.get()` | FRED API | Economic data |
| `functional_test.py` | `requests.get()` | Internal API health checks | Test only |
| `comprehensive_test.py` | `requests.get()` | Endpoint validation | Test only |

---

## 2. Data Freshness Taxonomy

### 2.1 Static / Immutable Data (Never Refresh)

| Data Type | Source | Rationale |
|-----------|--------|-----------|
| Historical OHLCV (older than 1 month) | `price_history` table | Past prices never change |
| Quarterly earnings (past quarters) | `earnings_history` table | Historical data is permanent |
| Company business summary | `ticker_info` | Rarely changes |
| Sector/Industry classification | `ticker_info` | Structural, changes rarely |
| Long-term debt structure | Annual reports | Historical record |

**TTL:** `is_immutable = True`

---

### 2.2 Semi-Dynamic Data (3-7 Day TTL)

| Data Type | Source | Update Frequency | Rationale |
|-----------|--------|------------------|-----------|
| 50-day SMA | Calculated locally | Daily | Moving average, not critical |
| 180-day SMA | Calculated locally | Daily | Large denominator, marginal impact |
| Annual dividend yield | `yfinance.info` | Weekly | Dividend companies adjust quarterly |
| Sector allocation | Macro ETFs | Daily | Rotation is slow |
| Fundamental ratios (PE, PB, PS) | Quarterly reports | 3-5 days | Based on closing quarters |

**TTL:** `lazy_refresh = 3_days`

---

### 2.3 Highly Dynamic Data (1-60 Minute TTL)

| Data Type | Source | Update Frequency | Rationale |
|-----------|--------|------------------|-----------|
| Real-time price | `yfinance` / `yahooquery` | On-demand | User-facing, needs current |
| RSI (14-day) | Calculated from prices | 15 min | Uses recent closes |
| Intraday volume | `yfinance` | 5-15 min | Active trading signals |
| Market sentiment (VIX) | `macro.py` | 30 min | Market conditions |
| Money flow indicators | `money_flow.py` | 30 min | Recent volume patterns |
| Analyst recommendations | `analyst.py` | Hourly | News-driven |

**TTL:** `real_time = 1_minute` to `soft_refresh = 30_minutes`

---

## 3. Data Source Catalog Summary

| Module | Data Type | Freshness Tier | Current TTL | Refactor Target |
|--------|-----------|----------------|-------------|-----------------|
| `macro.py` | Treasury Yields | Semi-Dynamic | 1h hard, 45m soft | 30m |
| `macro.py` | VIX | Highly Dynamic | 1h hard, 45m soft | 15m |
| `macro.py` | Oil/Gold Futures | Semi-Dynamic | 1h hard, 45m soft | 30m |
| `market_data.py` | Market Cap | Semi-Dynamic | 30m | 15m |
| `market_data.py` | GDP | Static | None | `is_immutable` |
| `market_data.py` | Sector Performance | Semi-Dynamic | None | 1h |
| `dip_hunter.py` | Price History | Static | DB-first | `is_immutable` |
| `dip_hunter.py` | Current Price | Highly Dynamic | None | 1min cache |
| `dip_hunter.py` | Fundamentals | Semi-Dynamic | DB-first | 3-day TTL |
| `cycle_analytics.py` | Rotation Data | Semi-Dynamic | DB cache check | 1h |
| `screener.py` | Screening Data | Dynamic | None | 5min |
| `research.py` | Deep Fundamentals | Semi-Dynamic | DB layer | 3-day TTL |
| `screeners.py` | Multi-ticker | Dynamic | None | 5min |
| `money_flow.py` | Money Flow | Highly Dynamic | Unknown | 15min |
| `opportunity_engine.py` | Opportunities | Semi-Dynamic | Unknown | 1h |
| `analyst.py` | Recommendations | Highly Dynamic | Unknown | 30min |
| `superinvestors_live.py` | Whale Tracking | Semi-Dynamic | 1h | 1h |
| `updater.py` | Economic Data | Static | FRED native | `is_immutable` |
| `economic.py` | Economic Indicators | Semi-Dynamic | None | 1h |

---

## 4. Network Call Frequency Map

```
HIGH FREQUENCY (Every request)
├── screener.py - yfinance download (no cache)
├── screeners.py - yfinance download (no cache)
└── dip_hunter.py - current price check

MEDIUM FREQUENCY (Per session)
├── research.py - deep fundamentals (DB layer)
├── cycle_analytics.py - rotation data (DB check first)
└── opportunity_engine.py - opportunity scoring

LOW FREQUENCY (Daily)
├── macro.py - market indicators (1h cache)
├── market_data.py - sector data (30m cache)
└── superinvestors_live.py - whale tracking (1h cache)

ON-DEMAND (Per quarter)
├── earnings data - quarterly reports
├── long-term fundamentals - company structure
└── economic data - GDP (FRED API)
```

---

## 5. Phase 1 Completion Checklist

- [x] Audit `yfinance` imports
- [x] Audit `yahooquery` imports
- [x] Audit `requests` / `httpx` imports
- [x] Categorize data by freshness tier
- [x] Document current TTL behavior
- [x] Map frequency to modules
- [ ] Identify duplicate/redundant fetches
- [ ] Prioritize refactoring targets

---

## 6. Refactoring Priority Matrix

| Priority | Module | Reason | Impact |
|----------|--------|--------|--------|
| **P0** | `screener.py` | No caching, 50+ tickers per request | Rate limit risk |
| **P0** | `screeners.py` | No caching, bulk downloads | Rate limit risk |
| **P0** | `dip_hunter.py` | Already DB-first, extend pattern | Completed |
| **P1** | `cycle_analytics.py` | Add DB-first pattern | 10 tickers, 1y data |
| **P1** | `research.py` | Enhance DB layer | Deep analysis |
| **P2** | `macro.py` | Already cached, improve TTL logic | 4 tickers |
| **P2** | `market_data.py` | Enhance FRED caching | Quarterly GDP |
| **P3** | `money_flow.py` | Review and cache | Lower traffic |

---

*Next Action: Proceed to Phase 2 - Schema Design*