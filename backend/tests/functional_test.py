import requests
import sys
import json

BASE_URL = "http://0.0.0.0:8000/api"

def run_test(name, endpoint, check_fn=None):
    print(f"Testing {name} ({endpoint})...", end=" ")
    try:
        res = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        if res.status_code != 200:
            print(f"FAIL (Status {res.status_code})")
            return False
        
        data = res.json()
        if check_fn:
            if check_fn(data):
                print("PASS")
                return True
            else:
                print("FAIL (Content Check)")
                return False
        else:
            print("PASS")
            return True
    except Exception as e:
        print(f"FAIL (Exception: {e})")
        return False

def check_market_status(data):
    return "market_cap" in data and "gdp" in data and "ratio_percent" in data

def check_sector(data):
    return "top_stocks" in data and len(data["top_stocks"]) > 0 and "avg_pe" in data

def check_analysis(data):
    return data.get("symbol") == "AAPL" and "score" in data

def check_moonshots(data):
    return len(data) > 0 and "innovation_score" in data[0] and "theme" in data[0]

def check_screeners(data):
    # Should return a list, potentially empty but valid json
    return isinstance(data, list)

def check_copycat(data):
    return len(data) > 0 and "held_by" in data[0]

if __name__ == "__main__":
    tests = [
        ("Market Status", "/market-status", check_market_status),
        ("Sector: Technology", "/stocks/Technology", check_sector),
        ("Sector: Real Estate (New)", "/stocks/Real Estate", check_sector),
        ("Search: AAPL", "/analyze/AAPL?strategy=buffett", check_analysis),
        ("Moonshots", "/moonshots", check_moonshots),
        ("Screener: Magic Formula", "/screeners/magic_formula", check_screeners),
        ("Screener: Rule of 40", "/screeners/rule_of_40", check_screeners),
        ("Copycat Portfolio", "/copycat", check_copycat),
    ]

    passed = 0
    for name, endpoint, check in tests:
        if run_test(name, endpoint, check):
            passed += 1
            
    print(f"\nSummary: {passed}/{len(tests)} Tests Passed.")
    if passed == len(tests):
        sys.exit(0)
    else:
        sys.exit(1)
