# Dynamic Data Setup Guide

This application now supports **live data pipelines** to replace static lists with real-time information.

## Components

### 1. Dynamic Universe (`updater.py`)
**Purpose**: Keeps S&P 500 and Nasdaq 100 ticker lists fresh.

**How to Run**:
```bash
cd backend
python3 updater.py
```

**Schedule**: Run weekly or when you notice index changes.

**Dependencies**: `pandas`, `lxml` (for HTML parsing)
```bash
pip install pandas lxml
```

---

### 2. Live GDP (FRED API)
**Purpose**: Fetches real US GDP for the Buffett Indicator.

**Setup**:
1. Get a free API key from [FRED](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Set environment variable:
   ```bash
   export FRED_API_KEY="your_key_here"
   ```
3. Restart the server

**Fallback**: If no key is set, uses the hardcoded estimate ($28T).

---

### 3. Live 13F Data (FMP API)
**Purpose**: Fetches real-time hedge fund holdings.

**Setup**:
1. Get an API key from [Financial Modeling Prep](https://financialmodelingprep.com/developer/docs/)
   - Free tier: 250 requests/day
2. Set environment variable:
   ```bash
   export FMP_API_KEY="your_key_here"
   ```
3. Update `main.py` to use `superinvestors_live.get_live_superinvestors()` instead of the static version

**Fallback**: If no key is set, uses the curated static data.

---

## Quick Start (All Features)

```bash
# Install dependencies
pip install pandas lxml requests

# Set API keys (optional but recommended)
export FRED_API_KEY="your_fred_key"
export FMP_API_KEY="your_fmp_key"

# Update ticker universe
python3 updater.py

# Start server (will auto-use live GDP if key is set)
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Automation

### Cron Job for Weekly Universe Updates
```bash
# Edit crontab
crontab -e

# Add this line (runs every Sunday at 2 AM)
0 2 * * 0 cd /path/to/backend && python3 updater.py
```

---

## Verification

**Check if live data is active**:
- **GDP**: Look for "FRED API" in server logs when loading dashboard
- **13F**: Check if investor holdings show recent quarters
- **Universe**: Run `python3 -c "from universe import get_master_universe; print(len(get_master_universe()))"` - should show ~500+ tickers

---

## Cost Analysis

| Service | Free Tier | Cost if Exceeded |
|---------|-----------|------------------|
| FRED API | Unlimited | Always Free |
| FMP API | 250 req/day | $14/month for 750/day |
| Wikipedia Scraping | Unlimited | Always Free |

**Recommendation**: Start with free tier. Upgrade FMP only if you need real-time 13F updates.
