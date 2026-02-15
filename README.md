# Rational Equity Dashboard 📊

A comprehensive stock analysis dashboard featuring dip hunting, superinvestor tracking, and economic indicators.

## Quick Start

### Single Command Launch

```bash
./start.sh
```

That's it! The script will:
- ✅ Create a virtual environment (if needed)
- ✅ Install all dependencies
- ✅ Launch the server
- ✅ Open your browser automatically

### Manual Setup (Alternative)

If you prefer manual control:

```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate it
source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
cd stockguide
python3 run.py
```

## Features

- 📈 **Market Dashboard** - Real-time market status and trends
- 🎯 **Dip Hunter** - Identifies quality stocks in dips (250+ ticker universe)
- 🔭 **Superinvestor Radar** - Track legendary investors
- 📊 **Pro Screeners** - Advanced stock screening tools
- 💼 **Portfolio** - Manage and track your investments

## Tech Stack

- **Backend**: FastAPI, Python 3.10+
- **Frontend**: Vanilla JS, TailwindCSS
- **Data**: yfinance, pandas

## Dashboard Access

Once running, visit: **http://localhost:8000**

## Troubleshooting

**Port already in use?**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

**Dependencies failing?**
```bash
# Upgrade pip first
pip install --upgrade pip
pip install -r requirements.txt
```
