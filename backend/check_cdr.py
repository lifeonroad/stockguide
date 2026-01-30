import yfinance as yf

# List of potential CDRs or Canadian versions of US stocks
tickers = [
    "PFE.NE",  # Pfizer CDR (NEO Exchange)
    "AMZN.NE", # Amazon CDR
    "TSLA.NE", # Tesla CDR
    "PFE.TO",  # Unlikely, usually NEO for CDRs
    "PFE"      # US Stock
]

print("Fetching prices...")
data = yf.download(tickers, period="1d", group_by='ticker', threads=True)

for t in tickers:
    try:
        price = data[t]['Close'].iloc[-1]
        currency = "Unknown"
        # Try to get currency from info (slow, but useful for check)
        # info = yf.Ticker(t).fast_info
        # currency = info.currency
        print(f"{t}: {price:.2f}")
    except Exception as e:
        print(f"{t}: Failed ({e})")
