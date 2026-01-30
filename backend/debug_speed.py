import yfinance as yf
import time
import requests

TICKERS = ["AAPL", "MSFT", "INVALID_XYZ", "GOOGL"]

def test_download():
    print(f"--- Testing yf.download for {len(TICKERS)} tickers ---")
    start = time.time()
    try:
        data = yf.download(TICKERS, period="1d", group_by='ticker', threads=True, progress=False)
        # Parse logic
        count = 0
        for t in TICKERS:
            try:
                if t in data.columns.levels[0]:
                    _ = data[t]['Close'].iloc[-1]
                    count += 1
            except:
                pass
        duration = time.time() - start
        print(f"Download took {duration:.4f}s. Got {count} prices.")
    except Exception as e:
        print(f"Download failed: {e}")

def test_fast_info():
    print(f"--- Testing Tickers.fast_info for {len(TICKERS)} tickers ---")
    start = time.time()
    try:
        tickers = yf.Tickers(" ".join(TICKERS))
        count = 0
        for t in TICKERS:
            try:
                # accessing fast_info triggers the fetch for that ticker? 
                # or is it prefetched? Tickers usually lazily instantiates.
                # parallel access is key.
                _ = tickers.tickers[t].fast_info['last_price']
                count += 1
            except Exception as e:
                # print(e)
                pass
        duration = time.time() - start
        print(f"Fast_info took {duration:.4f}s. Got {count} prices.")
    except Exception as e:
        print(f"Fast_info failed: {e}")
        
if __name__ == "__main__":
    test_download()
    test_fast_info()
