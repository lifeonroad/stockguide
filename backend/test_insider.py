import yfinance as yf
import pandas as pd

try:
    ticker = yf.Ticker("MSFT")
    # Try different potential endpoints
    print("--- Transactions ---")
    trans = ticker.insider_transactions
    if trans is not None:
        print(trans.head())
        print(trans.columns)
    else:
        print("No transactions found.")

    print("\n--- Purchases ---")
    purch = ticker.insider_purchases
    if purch is not None:
        print(purch.head())
    else:
        print("No purchases found.")

except Exception as e:
    print(e)
