# Momentum Investing & Trading Evaluation Engine

A quantitative momentum investing module that scans the US + Canadian master universe, scores each ticker on a multi-factor momentum matrix (0–100), and delivers ranked actionable picks. Built as a new tab in the existing stock analysis dashboard.

---

## Architecture Overview

```
┌─────────────────────┐
│  SQLite Persistent   │
│  Cache (price hist)  │
└────────┬────────────┘
         │ reads via get_price_history_cached()
         ▼
┌─────────────────────┐
│  momentum.py         │ ◄── @timed_cache (3600s hard / 1800s soft)
│  scan_momentum_picks │
│  _compute_single_mom │
│  _compute_momentum   │
│  _score_* helpers    │
└────────┬────────────┘
         │ returns List[Dict]
         ▼
┌─────────────────────┐
│  main.py             │
│  GET /api/momentum   │
│  ?min_score=0        │
│  &limit=50           │
│  &weights={...}      │
└────────┬────────────┘
         │ JSON response
         ▼
┌─────────────────────┐
│  Frontend Tab        │
│  momentum.js         │
│  momentum-view in    │
│  index.html          │
└─────────────────────┘
```

**Key principle:** Cache-only hot path. No yfinance calls during scoring. All price history is pre-loaded into SQLite by the existing data-orchestrator layer.

---

## Phase 1: Proof of Value — Backtesting & Evaluation Engine

A separate backtesting module validates whether momentum strategies actually generate alpha vs. the S&P 500 benchmark.

### 1.1 Backtest Setup

```python
# Pseudo-architecture for backtest module (backend/backtest_momentum.py)
# Uses vectorized pandas/numpy — no external backtesting library needed
# since we only evaluate discrete entry/exit rules, not order execution.

Inputs:
  - universe: List[str]  (same as scan_momentum_picks)
  - lookback: int        (days of history to test over, e.g. 756 for 3yr)
  - holding_periods: [5, 20, 63, 126]  (1wk, 1mo, 3mo, 6mo)
  - entry_threshold: int (momentum score >= X to trigger entry)
```

### 1.2 Metrics Calculated

#### Absolute vs. Benchmark Returns (CAGR)

```
CAGR_portfolio = (V_final / V_initial) ^ (252 / total_trading_days) - 1
CAGR_benchmark = (SPY_final / SPY_initial) ^ (252 / total_trading_days) - 1
Alpha = CAGR_portfolio - CAGR_benchmark
```

#### Risk-Adjusted Metrics

```
Sharpe Ratio  = (mean(R_p) - R_f) / std(R_p)    × sqrt(252)
Sortino Ratio = (mean(R_p) - R_f) / downside_std(R_p)  × sqrt(252)

where:
  R_p = daily portfolio returns
  R_f = risk-free rate (0.05 / 252)
  downside_std = std(R_p where R_p < 0)
```

#### Maximum Drawdown

```
MDD = min( V_t / peak(V_0..t) - 1 )  over entire backtest period
```

#### Win/Loss Ratio by Holding Period

```
For each holding period:
  entry_dates   = all dates where momentum_score >= threshold
  exit_prices   = price at entry_date + holding_period
  win  = count(exit_price > entry_price)
  loss = count(exit_price <= entry_price)
  win_rate = win / (win + loss)

  Also calculate:
    avg_win_pct  = mean( (exit - entry) / entry ) for winning trades
    avg_loss_pct = mean( (exit - entry) / entry ) for losing trades
    profit_factor = sum(wins) / abs(sum(losses))
```

### 1.3 Walk-Forward Validation

Split historical data into:
- **Training window** (e.g., first 60%): optimize parameter weights
- **Test window** (e.g., last 40%): evaluate out-of-sample performance

Run roll-forward: retrain every 6 months, test on next 6 months. Prevents overfitting.

### 1.4 Benchmark Comparison Output

```
╔══════════════════════╦══════════════╦══════════╦═══════════╗
║ Metric               ║ Momentum     ║ SPY       ║ Outperform║
╠══════════════════════╬══════════════╬══════════╬═══════════╣
║ CAGR (3yr)           ║ +18.4%       ║ +12.1%    ║ +6.3%     ║
║ Sharpe Ratio         ║ 1.12         ║ 0.78      ║ +0.34     ║
║ Sortino Ratio        ║ 1.65         ║ 1.02      ║ +0.63     ║
║ Max Drawdown         ║ -14.2%       ║ -18.7%    ║ -4.5%     ║
║ Win Rate (20d hold)  ║ 62%          ║ 54%       ║ +8%       ║
║ Win Rate (63d hold)  ║ 68%          ║ 58%       ║ +10%      ║
╚══════════════════════╩══════════════╩══════════╩═══════════╝
```

---

## Phase 2: Core Momentum Parameters & Pick Derivation

Each stock in the universe is scored on the following factors, grouped by timeframe.

### 2.1 Short-Term Momentum (Days to Weeks)

#### Rate of Change (ROC) — 21-day

```
ROC_21 = (close_today / close_21_days_ago - 1) × 100

Scoring:
  Clamped to [0, 50] range, then normalized to 0-100.
  ROC < 0%  → score = 0
  ROC ≥ 50% → score = 100
  Linear interpolation in between.
```

Formula in code (`momentum.py:197-199`):
```python
st = min(max(roc_1m, 0), 50) / 50 * 100
```

#### RSI Dynamic Scoring (14-period)

Rather than a simple overbought/oversold binary, RSI is scored on a **sweet-spot curve** optimized for continuation:

| RSI Range       | Score | Rationale                                    |
|-----------------|-------|----------------------------------------------|
| 45–65           | 100   | Ideal continuation zone — not overbought     |
| 40–45 or 65–70  | 70    | Edge of sweet spot — mildly extended         |
| 30–40 or 70–75  | 40    | Weakening momentum or extended               |
| < 30            | 10    | Oversold — momentum broken (not mean-rev)    |
| > 75            | 0     | Overbought — high reversal risk              |

Formula in code (`momentum.py:109-120`):
```python
_score_rsi_dynamic(rsi) → 0–100
```

#### Price vs. Short-Term EMAs (10-day & 20-day)

```
EMA_10 Proximity Score:
  prox = max(0, 1 - |price / ema_10 - 1| × 5) × 100
  
  If price is exactly at EMA-10:         score = 100
  If price is ±5% from EMA-10:           score = 75
  If price is ±10% from EMA-10:          score = 50
  If price is ±20% or more from EMA-10:  score = 0

EMA_20 Binary Score:
  price > EMA_20 → 100 points weighted
  price ≤ EMA_20 → 0
```

#### Volume Spike Detection

```
Volume Ratio = avg(volume_last_5_days) / avg(volume_last_20_days)

Score = min(ratio / 3, 1.0) × 100

Examples:
  ratio = 1.0 (no spike)  → score = 33
  ratio = 2.0 (2x avg)    → score = 67
  ratio = 3.0 (3x avg)    → score = 100
```

### 2.2 Medium to Long-Term Momentum (Months to a Year)

#### MACD Crossover

Configured as standard (12, 26, 9):
```
MACD Line = EMA_12(close) - EMA_26(close)
Signal Line = EMA_9(MACD Line)
Histogram = MACD Line - Signal Line

Bullish trigger:
  macd > signal  → bonus = 100
  histogram > 0  → confirmation (still 100)
```

#### Dual Moving Average Cross (50/200 SMA)

| Condition                                 | Score |
|-------------------------------------------|-------|
| SMA_50 > SMA_200 **and** price > SMA_50   | 100   |
| SMA_50 > SMA_200 (crossover, price below) | 70    |
| Price > SMA_50 **and** price > SMA_200    | 50    |
| Price > SMA_200 only                      | 30    |
| None of the above                         | 0     |

"Golden cross" bonus: flagged in reasons when SMA_50 crosses above SMA_200.

#### Proximity to 52-Week High

```
pct = price / 52_week_high

pct ≥ 0.97  → 100  (within 3% of high — consolidation near peak)
pct ≥ 0.90  → 70   (strong uptrend)
pct ≥ 0.80  → 40   (moderate recovery)
pct < 0.80  → 10   (far from high — weak)
```

### 2.3 Trend Strength Filtering

#### ADX (Average Directional Index) — 14-period

```
ADX Score = max(0, (adx - 25) / 25 × 100)

adx ≤ 25  → score = 0   (no trend / ranging)
adx = 50  → score = 100  (strong trend)
adx = 75  → score = 100+ (capped at 100)
```

ADX > 25 is the threshold filter — stocks below are not considered trending regardless of price movement.

#### Directional Indicator Strength

```
DI Strength = max(0, (+DI - -DI) / (+DI + -DI)) × 100

+DI > -DI → positive score (bullish trend)
-DI > +DI → score = 0 (bearish, filtered out)
```

### 2.4 Risk Penalty

Two penalty factors applied to the final raw score:

**Drawdown Penalty** (6-month lookback):
```
If (52-week high - 6-month low) / 52-week high > 20%:
    trigger full risk_penalty weight
```

**Volatility Penalty** (252-day annualized vol):
```
If annualized volatility > 60%:
    trigger full risk_penalty weight
```

These prevent momentum-chasing in highly volatile or deeply-drawndowned names.

---

## Phase 3: Scoring & Ranking System

### 3.1 Weight Configuration

Default weights (configurable by user via frontend sliders):

| Factor             | Weight | Category    |
|--------------------|--------|-------------|
| ROC (1-month)      | 8      | Short-Term  |
| RSI Dynamic        | 8      | Short-Term  |
| EMA-10 Proximity   | 7      | Short-Term  |
| Volume Spike       | 6      | Short-Term  |
| Price > EMA-20     | 6      | Short-Term  |
| ROC (6-month)      | 10     | Medium-Term |
| MACD               | 8      | Medium-Term |
| SMA 50/200         | 9      | Medium-Term |
| 52-Week High %     | 8      | Medium-Term |
| ADX                | 10     | Trend       |
| DI Strength        | 5      | Trend       |
| Risk Penalty       | -15    | Penalty     |
| **Total**          | **85** | _(excl penalty)_ |

### 3.2 Score Normalization Formula

```
raw_score = short_term_contributions + med_term_contributions + trend_contributions
total_weight = sum of all positive weights (= 85 in default config)
penalty = risk_penalty_triggered ? 100 : 0
max_penalty = abs(risk_penalty) = 15

normalized = (raw_score / total_weight × 100) - (penalty / max_penalty × 100)
final_score = clamp(normalized, 0, 100)
```

### 3.3 Zone Taxonomy

| Score Range | Signal       | Action              | Display Color |
|-------------|--------------|---------------------|---------------|
| 80–100      | STRONG_BUY   | High-Conviction Pick| 🟢 Green      |
| 65–79       | BUY          | Accumulate          | 🟢 Green      |
| 50–64       | WATCH        | Monitor             | 🟡 Yellow     |
| 25–49       | HOLD         | Hold / Wait         | 🟠 Orange     |
| 0–24        | AVOID        | Avoid / Exit        | 🔴 Red        |

### 3.4 Ranking Pipeline

```
_build_universe()         → ~400 US + Canadian symbols
_fetch_prices(symbol)     → DataFrame with OHLCV (min 50 days)
_compute_single_momentum  → Dict with score, signal, factors
  ├─ calculate_roc, rsi, macd, adx, ema
  ├─ _score_rsi_dynamic, _score_volume_spike
  ├─ _score_sma_50_200, _score_52w_proximity
  └─ _compute_momentum_score → raw + normalized
filter by min_score
sort by score descending
limit to top N
return picks
```

---

## Phase 4: Integration Architecture

### 4.1 JSON Response Format

```json
GET /api/momentum?min_score=0&limit=50

{
  "status": "ok",
  "timestamp": "2026-05-15T14:30:00Z",
  "total_scanned": 412,
  "total_qualified": 47,
  "config": {
    "min_score": 0,
    "limit": 50,
    "weights": { ... default weights ... }
  },
  "picks": [
    {
      "symbol": "NVDA",
      "momentum_score": 94.2,
      "signal": "STRONG_BUY",
      "action": "High-Conviction Pick",
      "price": 892.45,
      "roc_1m": 12.4,
      "roc_3m": 38.7,
      "roc_6m": 65.2,
      "roc_12m": 142.1,
      "rsi_14": 58.3,
      "macd_bullish": true,
      "macd_histogram": 2.345,
      "sma_50": 821.30,
      "sma_200": 645.10,
      "golden_cross": true,
      "ema_10": 878.50,
      "ema_20": 855.20,
      "adx": 38.5,
      "plus_di": 28.2,
      "minus_di": 12.1,
      "volume_ratio": 1.85,
      "pct_off_52w_high": -1.2,
      "reasons": [
        "Momentum Score 94/100 — strong momentum across timeframes",
        "ADX 38.5 — strong trend",
        "MACD bullish — positive crossover",
        "Golden cross (SMA 50 > SMA 200)"
      ]
    }
  ]
}
```

### 4.2 Frontend Integration Points

#### Navigation Tab (index.html)

Add button alongside existing tabs:
```html
<button id="tab-momentum" onclick="switchTab('momentum')"
    class="text-gray-400 hover:text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
    Momentum <span class="ml-1 text-xs">⚡</span>
</button>
```

#### View Container (index.html)

```html
<div id="momentum-view" class="hidden space-y-6">
    <!-- Weight Slider Panel -->
    <!-- Picks Table -->
    <!-- Detail Cards -->
</div>
```

#### Tab Router (app.js)

```javascript
const tabs = ['dashboard', 'superinvestors', ..., 'momentum', ...];
// ...
else if (tabName === 'momentum') loadMomentumData();
```

#### Frontend Component (frontend/js/components/momentum.js)

Exports `loadMomentumData()` which:
1. Calls `GET /api/momentum?min_score=0&limit=50`
2. Renders a ranked table with score, signal, price, key factors
3. Color-codes rows by signal zone (green/yellow/orange/red)
4. Shows reason chips per pick
5. Provides weight sliders to adjust factor emphasis in real-time
6. Includes a "Backtest" button to run historical validation

### 4.3 Caching Strategy

| Layer | Mechanism          | TTL                      |
|-------|--------------------|--------------------------|
| 1     | `@timed_cache`     | 3600s hard / 1800s soft  |
| 2     | SQLite price hist  | Per-ticker staleness     |
| 3     | Frontend SWR       | localStorage timestamp   |

The endpoint is cached server-side for 1 hour. The frontend can poll every 30 minutes during market hours, every 2 hours outside.

### 4.4 Endpoint Registration (main.py)

```python
# Import (module-level, line ~263):
from momentum import scan_momentum_picks

# Endpoint (after technical/zones, before contrarian):
@app.get("/api/momentum")
async def momentum_picks(min_score: float = 0, limit: int = 50):
    """Scan universe and return momentum-ranked picks (0-100 score)."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    if min_score < 0 or min_score > 100:
        raise HTTPException(status_code=400, detail="min_score must be between 0 and 100")
    try:
        picks = await _to_thread_with_timeout(
            scan_momentum_picks, min_score, limit, timeout=SLOW_API_TIMEOUT
        )
        return {"picks": picks, "count": len(picks)}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Momentum scan timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Appendix A: Technical Indicator Formulas

All implemented in `backend/indicators.py`.

**RSI (14):**
```
RSI = 100 - 100 / (1 + RS)
RS = avg_gain(14) / avg_loss(14)
```

**EMA:**
```
EMA_t = price_t × α + EMA_t-1 × (1 - α)
α = 2 / (period + 1)
```

**MACD (12, 26, 9):**
```
MACD Line = EMA_12 - EMA_26
Signal    = EMA_9(MACD Line)
Histogram = MACD Line - Signal
```

**ADX (14):**
```
TR = max(high - low, |high - prev_close|, |low - prev_close|)
+DM = high - prev_high  (if > -DM and > 0)
-DM = prev_low - low    (if > +DM and > 0)
+DI = 100 × EMA(+DM) / ATR
-DI = 100 × EMA(-DM) / ATR
DX  = 100 × |+DI - -DI| / (+DI + -DI)
ADX = EMA(DX)
```

---

## Appendix B: Files Modified / Created

| File | Action | Purpose |
|------|--------|---------|
| `backend/momentum.py` | **NEW** | Momentum scoring engine (8-factor matrix) |
| `backend/indicators.py` | Existing | RSI, ROC, MACD, ADX, EMA implementations |
| `backend/main.py` | Modified | Add `GET /api/momentum` endpoint |
| `backend/tests/comprehensive_test.py` | Modified | Add `test_momentum()` test case |
| `frontend/index.html` | Modified | Momentum tab button + view container |
| `frontend/app.js` | Modified | Tab routing + import `loadMomentumData` |
| `frontend/js/components/momentum.js` | **NEW** | Momentum UI component (table, sort, signals) |
| `docs/MOMENTUM_TAB.md` | **NEW** | This documentation |

---

## Appendix C: Backtesting Implementation (Vectorized)

```python
def backtest_momentum_strategy(
    prices: pd.DataFrame,      # MultiIndex (symbol, date) with 'close'
    entry_scores: pd.Series,   # MultiIndex (symbol, date) with score
    threshold: float = 65,
    holding_periods: List[int] = [20, 63],
    top_n: int = 10,
    benchmark: str = "SPY",
) -> Dict:
    """
    Vectorized backtest: rebalance daily into top-N momentum stocks,
    hold for `holding_period` days, then compare to benchmark.
    
    Returns dict of metrics per holding period.
    """
    ...
```

This is **not yet implemented** in the codebase — Phase 1 (backtesting) remains to be built as a separate module.
