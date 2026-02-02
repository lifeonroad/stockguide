# Rational Equity 📈

**Holistic Market Intelligence & Portfolio Dashboard.**
> "Price is what you pay. Value is what you get." — Warren Buffett

## 🚀 Overview
**Rational Equity** is a comprehensive market dashboard that helps retail investors analyze the market using proven strategies from superinvestors like **Warren Buffett**, **Michael Burry**, and **Peter Lynch**.

It features:
*   **Rational Compass**: Is the market Overvalued or Undervalued? (Buffett Indicator).
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
│   └── data/         # SQLite Database (Local only)
├── frontend/         # Static Assets (HTML/JS/CSS)
│   ├── index.html
│   └── app.js
└── README.md
```

## ⚡ Quick Start

### 1. Prerequisites
*   Python 3.9+
*   `pip`

### 2. Installation
```bash
cd backend
pip install fastapi "uvicorn[standard]" yfinance pandas requests
```

### 3. Running the Server
```bash
# Run from the backend/ directory
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the Dashboard
Open your browser to:
[http://localhost:8000](http://localhost:8000)

## 🔒 Privacy & Data
*   **Local Storage**: All your portfolio data is stored in `backend/data/portfolios.db`.
*   **No Cloud Sync**: Your financial data never leaves your machine.
*   **Git Safe**: The database file is `.gitignored`, so your secrets are safe from GitHub uploads.

## 🤖 Architecture
See [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) for deep technical details.
