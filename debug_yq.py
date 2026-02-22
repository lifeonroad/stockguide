
import yfinance as yf
from yahooquery import Ticker as YQTicker
import pandas as pd
import time

tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN']

print(f"Testing yfinance download for {tickers}...")
try:
    data = yf.download(tickers, period="5d", progress=False)
    print(f"yfinance download success! Columns: {data.columns}")
except Exception as e:
    print(f"yfinance download failed: {e}")

print(f"\nTesting yahooquery for {tickers}...")
try:
    yq = YQTicker(tickers, asynchronous=True, max_workers=5)
    summary = yq.summary_detail
    print(f"yahooquery summary_detail keys: {list(summary.keys()) if isinstance(summary, dict) else 'Not a dict'}")
    if isinstance(summary, dict) and 'AAPL' in summary:
        print(f"AAPL summary: {summary['AAPL']}")
    else:
        print(f"AAPL missing from summary. Response type: {type(summary)}")
        print(f"Full response: {summary}")
except Exception as e:
    print(f"yahooquery failed: {e}")
