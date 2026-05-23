# Rational Equity 📈

**Holistic Market Intelligence & Portfolio Dashboard.**
> "Price is what you pay. Value is what you get." — Warren Buffett

## 🚀 Overview
**Rational Equity** is a comprehensive market dashboard that helps retail investors analyze the market using proven strategies from superinvestors like **Warren Buffett**, **Michael Burry**, and **Peter Lynch**.

It features:
*   **Rational Compass**: Is the market Overvalued or Undervalued? (Buffett Indicator).
*   **Economic Indicators**: Live macro data (unemployment, inflation, Fed rates, GDP) from FRED API.
*   **Market News**: Aggregated financial headlines from Yahoo Finance, Reuters, MarketWatch.
*   **Macro Impact Analysis**: Real-time sector tailwinds/headwinds based on rates, oil, VIX.
*   **Holistic Verification**: Automated "Buy/Hold/Sell" verdicts based on fundamental data (ROE, Debt, Margins).
*   **Multi-Currency Portfolios**: Track USD and CAD assets with automatic currency handling.
*   **Superinvestor Radar**: Track 13F filings of top hedge funds.

## 🛠 Project Structure
The project is set up as a monolithic repo with separated concerns:

```text
repo/
├── backend/          # Python API (FastAPI) & Logic
│   ├── main.py       # Entry point
│   ├── analyst.py    # Strategy Logic
│   ├── economic.py   # FRED API integration
│   ├── news.py       # RSS feed aggregator
│   ├── macro.py      # Macro indicators & sector impacts
│   └── data/         # SQLite Database (Local only)
├── frontend/         # Static Assets (HTML/JS/CSS)
│   ├── index.html
│   └── app.js
├── .env              # Environment variables (API keys)
└── README.md
```

## ⚡ Quick Start

### 1. Prerequisites
*   Python 3.9+
*   `pip`

### 2. Installation
```bash
pip install fastapi "uvicorn[standard]" yfinance pandas requests feedparser python-dotenv
```

### 3. Environment Setup (Optional but Recommended)
Create a `.env` file in the project root to enable live economic data:

```bash
# .env
FRED_API_KEY=your_fred_api_key_here
```

**Get a free FRED API key**: https://fred.stlouisfed.org/docs/api/api_key.html

> **Note**: Without a FRED API key, the Economics tab will display demo data.

### 4. Running the Server

**Option A: Simplified launcher (recommended)**
```bash
python3 run.py
```
This automatically:
- Loads environment variables from `.env`
- Starts the backend server
- Opens your browser to the dashboard

**Option B: Manual**
```bash
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Access the Dashboard
Open your browser to:
[http://localhost:8000](http://localhost:8000)

## 📊 Features

### Economics Tab
- **Live Macro Indicators**: Unemployment, CPI inflation, Fed funds rate, GDP growth
- **Data Source**: Federal Reserve Economic Data (FRED) API
- **Update Frequency**: Daily (24-hour cache)

### News Tab
- **Aggregated Headlines**: Yahoo Finance, Reuters, MarketWatch
- **Update Frequency**: Hourly (1-hour cache)
- **Filter**: Market-relevant news only

### Macro Impact Column
Analyzes current macro conditions to determine sector tailwinds/headwinds:
- **Rising Rates** → Headwind for Tech/Real Estate, Tailwind for Financials
- **Rising Oil** → Tailwind for Energy, Headwind for Consumers
- **High VIX** → Tailwind for Defensive sectors (Healthcare, Staples)

## 🔒 Privacy & Data
*   **Local Storage**: All your portfolio data is stored in `backend/data/portfolios.db`.
*   **No Cloud Sync**: Your financial data never leaves your machine.
*   **Git Safe**: Database files and `.env` are `.gitignored`, so your secrets are safe from GitHub uploads.

## 🤖 Architecture
See [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) for deep technical details.
