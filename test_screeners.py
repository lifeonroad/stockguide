import sys, os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import traceback
try:
    from screeners import _bulk_fundamentals
    tickers = ["AAPL"]
    out = _bulk_fundamentals(tickers)
    with open("test_out.txt", "w") as f:
        f.write(str(out))
except Exception as e:
    with open("test_out.txt", "w") as f:
        f.write(traceback.format_exc())
