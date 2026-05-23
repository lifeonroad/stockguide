# StockGuide Refactoring Specification

> Transforming from ad-hoc network calls to a structured, DB-first architecture.

---

## Phase 1: Discovery & Taxonomy

**Objective:** Audit all network egress points and define a data hierarchy.

### Instructions
Trace all instances of:
- `yfinance`
- `google-finance-api`
- Raw `requests` / `aiohttp` calls

### Deliverable: Data Source Catalog

Categorize all data sources into three tiers:

| Category | Examples | Update Frequency | DB Behavior |
|----------|----------|------------------|-------------|
| **Static/Immutable** | Historical prices, past quarterly earnings (e.g., 2025 Q1 PE), sector info | Never | Permanent Store |
| **Semi-Dynamic** | Technical indicators (SMA 50/180), annual dividend yields | Every 2-3 days | Lazy Refresh (3-day TTL) |
| **Highly Dynamic** | Real-time price, RSI, intraday volume | On-demand | Cache for < 1 min |

---

## Phase 2: Schema Design for Extensibility

**Objective:** Transition from a flat storage model to a multi-tenant, intent-aware schema.

### 2.1 Database Architecture

Implement a **Global-Context-Specific** hierarchy:

```
┌─────────────────────────────────────────────────────────────┐
│                    Database Schema                          │
├─────────────────────────────────────────────────────────────┤
│  GLOBAL TABLE                                               │
│  Core ticker metadata (Company Name, Exchange, Sector)     │
├─────────────────────────────────────────────────────────────┤
│  TIME-SERIES TABLE                                         │
│  OHLCV data with last_updated timestamp and source tag       │
├─────────────────────────────────────────────────────────────┤
│  METADATA TABLE (Contextual)                               │
│  Attributes with Update TTL                                 │
│  Example: {                                                 │
│    "attribute": "PE_Ratio",                                │
│    "value": 15.4,                                          │
│    "update_logic": "Quarterly",                            │
│    "stale_after": "2026-07-01"                              │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Access Width** | Support bulk lookups (e.g., fetching 50 tickers' SMA in one query) |
| **JSONB Support** | Use NoSQL-style columns for "Calculated Indicators" — add new formulas without schema migrations |

---

## Phase 3: The "DB-First" API Implementation

**Objective:** Wrap all network logic in a **Data Provider Interface**.

### 3.1 The Fetch Logic Flow

Replace direct network calls with a **DataOrchestrator**:

```
                    DataOrchestrator Flow
                    ====================

    ┌─────────────────────────────────────────┐
    │  1. Check DB                           │
    │     Query for ticker + attribute       │
    └─────────────────┬─────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │  2. Evaluate Freshness                 │
    │     Compare last_updated vs TTL         │
    └─────────────────┬─────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
    ┌─────┴─────┐           ┌─────┴─────┐
    │   FRESH   │           │ STALE/MISS│
    └─────┬─────┘           └─────┬─────┘
          │                       │
          ▼                       ▼
    ┌─────────────┐       ┌─────────────────┐
    │ Return DB   │       │ 1. Log Cache   │
    │ Data        │       │    Miss         │
    │ (Instant)   │       │ 2. Return stale  │
    └─────────────┘       │    (if avail)    │
                         │ 3. Enqueue       │
                         │    for update    │
                         └─────────────────┘
```

### 3.2 Background Worker Strategy (The Updater)

The background process must be an **asynchronous loop** managing two queues:

| Queue | Priority | Source |
|-------|----------|--------|
| **High Priority** | On-Demand | User requests for missing tickers |
| **Low Priority** | Maintenance | Routine sweeps of stale entries (e.g., daily SMA updates) |

---

## Phase 4: AI-Driven Refresh Logic

**Objective:** Optimize bandwidth by assigning "Intelligence" to data types.

### Instructions to AI

For every data type, define an `update_strategy`:

| Data Type | Strategy | Rationale |
|-----------|----------|-----------|
| Static Data | `is_immutable = True` | Once stored, never re-fetch |
| 180-day SMA | `Lazy Refresh` (3-day TTL) | Large denominator — one day's price movement has marginal impact |
| High-beta stocks | Shortened TTLs | More volatile, needs more frequent updates |
| During earnings weeks | Shortened TTLs | High volatility period |
| "Wide Moat" stable assets | Extended TTLs | Less volatile, changes slowly |

### Volatility-Based Refresh Formula

```
Base TTL = 24 hours
Beta Adjustment = Base TTL / sqrt(Beta)
Earnings Adjustment = Base TTL / 2 (during earnings week)
```

---

## Phase 5: Implementation Summary

| Data Category | Update Frequency | Priority | DB Handling |
|--------------|------------------|----------|-------------|
| Historical PE/EPS | Once per Quarter | Low | Permanent Store |
| SMA (50/180) | Every 2-3 Days | Medium | Time-series Update |
| Real-time Price | On-Demand (Network) | Critical | Cache for < 1 min |
| Calculated Indicators | Local Recalc | N/A | Calculated in-engine from DB prices |

---

## Final Rule

> **All code refactoring must ensure that the `NetworkClient` is private, and the `DatabaseProvider` is the only public interface used by the application's business logic.**

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Application Layer                        │
│                  (Business Logic)                          │
└─────────────────────┬─────────────────────────────────────┘
                      │ Only public interface
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  DatabaseProvider                           │
│            (Public, Single Entry Point)                    │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │            DataOrchestrator                           │ │
│  │                                                      │ │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐  │ │
│  │  │ DB Check │→ │ Freshness│→ │ Return / Enqueue    │  │ │
│  │  └──────────┘  └──────────┘  └─────────────────────┘  │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────┬─────────────────────────────────────┘
                      │ Private (not exposed)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    NetworkClient                            │
│              (Private Implementation)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## TODO Checklist

- [x] **Phase 1:** Audit all network calls (`yfinance`, `requests`, `aiohttp`)
- [x] Identify duplicate/redundant fetches
- [x] **Phase 2:** Design enhanced schema with TTL metadata
- [x] Create SQL migration script
- [x] Define TTL constants in code (conservative: 30min floor, 48/day limit)
- [x] **Phase 3:** Create `DataOrchestrator` class
  - [x] Create `network_client.py` - private network layer with circuit breaker
  - [x] Create `rate_limiter.py` - rate limiting with cooldown
  - [x] Create `data_orchestrator.py` - main orchestrator with DB-first pattern
- [x] **Phase 3.5:** Update `data_client.py` to wrap orchestrator (backward compat)
  - [x] Rate limiting in `_background_refresh_ticker()`
  - [x] Rate limiting in `get_price_live()`
  - [x] Rate limiting in `_background_refresh_history()`
  - [x] Rate limiting in `warm_db_for_symbols()`
  - [x] Disable defeatbeta toggle (using yfinance only)
- [ ] **Phase 4:** Implement intelligent TTL logic (per-ticker volatility adjustment)
- [ ] **Phase 5:** Apply to all endpoints (screener, cycle_analytics, etc.)
- [ ] **Final:** Ensure `NetworkClient` is private, `DatabaseProvider` is public

**Phase 1 Output:** `docs/PHASE1_DATASOURCE_CATALOG.md`  
**Phase 2 Output:** `docs/PHASE2_SCHEMA_DESIGN.md`  
**Phase 3 Output:** `docs/PHASE3_DATA_ORCHESTRATOR.md`

**Implementation Files:**
- `backend/rate_limiter.py` - Thread-safe rate limiter (1800s floor, 48/day limit)
- `backend/network_client.py` - Private network layer with circuit breaker
- `backend/data_orchestrator.py` - Public interface (optional usage)
- `backend/data_client.py` - Updated with rate limiting throughout
- `backend/persistent_cache.py` - Updated TTL constants

**Tests Passed (2026-05-10):**
- `/` - HTML page loads
- `/api/admin/data-source` - Rate limiting status
- `/api/portfolios` - Returns portfolios
- `/api/admin/cache/stats` - 699 tickers, 128K price rows
- Rate limiter cooldown working (1800s after record_fetch)

**Phase 4:** Implement intelligent TTL logic (per-ticker volatility adjustment)
- [x] Add beta-based TTL adjustment
- [x] Add earnings week detection
- [x] Integrate into DataOrchestrator
- [x] Create `intelligent_ttl.py` module
- [x] Add `needs_refresh_intelligent()` to persistent_cache.py
- [x] Update `_background_refresh_ticker()` with priority-based delays
- [x] Test beta scaling (0.5→1.41x, 3.0→1.73x)

**Tests Passed (2026-05-10):**
- `/` - HTML page loads ✓
- `/api/admin/data-source` - Rate limiting status ✓
- `/api/portfolios` - Returns 3 portfolios ✓
- `/api/admin/cache/stats` - 699 tickers, 128K price rows ✓
- Intelligent TTL: Beta scaling working (TSLA=2418s, JNJ=5112s) ✓
- Refresh priorities: High beta=1, Low beta=3 ✓

**Phase 5:** Apply to all endpoints (screener, cycle_analytics, etc.)
- [ ] Update screener.py with rate limiting
- [ ] Update cycle_analytics.py with rate limiting
- [ ] Update money_flow.py with rate limiting
- [ ] Update macro.py with rate limiting
---

## PHASE 5 COMPLETE ✅

**Updated Modules with Rate Limiting:**
- `screener.py` - DB-first, throttle based on rate limit
- `cycle_analytics.py` - Cache check, skip if rate limited
- `money_flow.py` - Skip symbols if rate limited, save to DB
- `macro.py` - Warn if rate limited, log for monitoring

**Final Status (2026-05-10):**
- Database: 699 tickers, 128,277 price history rows
- Rate Limiting: 1800s floor, 48/day limit
- Intelligent TTL: Beta-based scaling (TSLA=900s, JNJ=1278s)
- All core endpoints: HTTP 200 OK

**Files Created:**
- `rate_limiter.py` - Thread-safe rate limiter
- `network_client.py` - Private network layer
- `data_orchestrator.py` - Public interface
- `intelligent_ttl.py` - Volatility-aware TTL

**Files Modified:**
- `data_client.py` - Rate limiting throughout
- `persistent_cache.py` - TTL constants + intelligent refresh
- `screener.py` - Rate limiting
- `cycle_analytics.py` - Rate limiting
- `money_flow.py` - Rate limiting
- `macro.py` - Rate limiting
