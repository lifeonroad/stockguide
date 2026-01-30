#!/usr/bin/env python3
"""
Comprehensive Test Suite for Dynamic Data Features
Tests all endpoints and dynamic data components
"""

import requests
import sys
import time

BASE_URL = "http://0.0.0.0:8000/api"

def test_market_status():
    """Test Buffett Indicator with dynamic GDP"""
    print("Testing Market Status (Buffett Indicator)...", end=" ")
    try:
        res = requests.get(f"{BASE_URL}/market-status", timeout=10)
        if res.status_code != 200:
            print(f"FAIL (Status {res.status_code})")
            return False
        
        data = res.json()
        required_fields = ["market_cap", "gdp", "ratio_percent", "rating"]
        if all(field in data for field in required_fields):
            print(f"PASS (GDP: ${data['gdp']/1e12:.1f}T, Ratio: {data['ratio_percent']}%)")
            return True
        else:
            print("FAIL (Missing fields)")
            return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

def test_screeners():
    """Test all screener strategies"""
    strategies = ['magic_formula', 'rule_of_40', 'lynch', 'deep_value']
    passed = 0
    
    for strategy in strategies:
        print(f"Testing Screener: {strategy}...", end=" ")
        try:
            res = requests.get(f"{BASE_URL}/screeners/{strategy}", timeout=30)
            if res.status_code == 200:
                data = res.json()
                print(f"PASS ({len(data)} matches)")
                passed += 1
            else:
                print(f"FAIL (Status {res.status_code})")
        except Exception as e:
            print(f"FAIL ({e})")
    
    return passed == len(strategies)

def test_moonshots():
    """Test Futuristic Bets endpoint"""
    print("Testing Moonshots...", end=" ")
    try:
        res = requests.get(f"{BASE_URL}/moonshots", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if len(data) > 0 and 'innovation_score' in data[0]:
                print(f"PASS ({len(data)} stocks)")
                return True
        print("FAIL")
        return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

def test_sector_analysis():
    """Test sector analysis endpoints"""
    sectors = ["Technology", "Healthcare", "Energy"]
    passed = 0
    
    for sector in sectors:
        print(f"Testing Sector: {sector}...", end=" ")
        try:
            res = requests.get(f"{BASE_URL}/stocks/{sector}", timeout=15)
            if res.status_code == 200:
                data = res.json()
                if "top_stocks" in data and len(data["top_stocks"]) > 0:
                    print(f"PASS ({len(data['top_stocks'])} picks)")
                    passed += 1
                else:
                    print("FAIL (No stocks)")
            else:
                print(f"FAIL (Status {res.status_code})")
        except Exception as e:
            print(f"FAIL ({e})")
    
    return passed == len(sectors)

def test_stock_search():
    """Test individual stock analysis"""
    symbols = ["AAPL", "MSFT"]
    passed = 0
    
    for symbol in symbols:
        print(f"Testing Search: {symbol}...", end=" ")
        try:
            res = requests.get(f"{BASE_URL}/analyze/{symbol}?strategy=buffett", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if "symbol" in data and data["symbol"] == symbol:
                    print("PASS")
                    passed += 1
                else:
                    print("FAIL (Wrong data)")
            else:
                print(f"FAIL (Status {res.status_code})")
        except Exception as e:
            print(f"FAIL ({e})")
    
    return passed == len(symbols)

def test_updater_script():
    """Test the universe updater (without actually running it)"""
    print("Checking updater.py exists...", end=" ")
    try:
        with open('updater.py', 'r') as f:
            content = f.read()
            if 'fetch_sp500_tickers' in content and 'fetch_nasdaq100_tickers' in content:
                print("PASS")
                return True
        print("FAIL")
        return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

def main():
    print("=" * 60)
    print("COMPREHENSIVE TEST SUITE - Dynamic Data Features")
    print("=" * 60)
    print()
    
    tests = [
        ("Market Status (Dynamic GDP)", test_market_status),
        ("Screeners (Cached Performance)", test_screeners),
        ("Moonshots", test_moonshots),
        ("Sector Analysis", test_sector_analysis),
        ("Stock Search", test_stock_search),
        ("Universe Updater", test_updater_script)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        result = test_func()
        results.append((name, result))
        time.sleep(0.5)  # Brief pause between test groups
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} | {name}")
    
    print("-" * 60)
    print(f"Total: {passed}/{total} test groups passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All tests passed! Application is fully functional.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test group(s) failed. Review errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
