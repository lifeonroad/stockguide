"""
cusip_utils.py — CUSIP to Ticker Mapping Utilities
=====================================================

Maps SEC 13F CUSIPs and issuer names to stock tickers.
Uses multiple strategies:
1. FMP API CUSIP lookup (if API key available)
2. Yahooquery search by name
3. Built-in common mappings for known holdings
"""

import os
import re
import logging
from typing import Dict, Optional, List, Any
from collections import OrderedDict

import requests

logger = logging.getLogger(__name__)

FMP_API_KEY = os.getenv("FMP_API_KEY", "")

COMMON_CUSIP_MAP: Dict[str, str] = {
    "037833100": "AAPL",
    "025816109": "AXP",
    "060505104": "BAC",
    "191216100": "KO",
    "166764100": "CVX",
    "615369105": "MCO",
    "674599105": "OXY",
    "500754106": "KHC",
    "02079K305": "GOOGL",
    "02079K107": "GOOG",
    "594918104": "MSFT",
    "458140100": "META",
    "023135106": "AMZN",
    "64110L106": "NVDA",
    "149123101": "PLTR",
    "717081103": "PFE",
    "406216101": "HAL",
    "60871R109": "MOH",
    "549498103": "LULU",
    "78408V101": "SLM",
    "01110V103": "BRKR",
    "H1467J104": "CB",
    "88160R101": "TSLA",
    "92826C839": "V",
    "57636Q104": "MA",
    "501044101": "KR",
    "829933100": "SIRI",
    "23918K108": "DVA",
    "002824100": "ABT",
    "00287Y109": "ABBV",
    "902494103": "UNH",
    "636718107": "JNJ",
    "46625H100": "JPM",
    "039483102": "BA",
    "191216100": "KO",
    "38076V101": "HD",
    "892324100": "WMT",
    "20030N101": "DIS",
    "007903107": "ADP",
    "16117L100": "COST",
    "91324P102": "LOW",
    "98986X109": "PYPL",
    "17275R102": "CSCO",
    "594918104": "MSFT",
    "68389X105": "ORCL",
    "88032Q109": "TXN",
    "15135U106": "NFLX",
    "30231G102": "EBX",
    "523771107": "QCOM",
    "171444109": "CAT",
    "543294106": "MRK",
    "169656105": "CMCSA",
    "478160104": "INTC",
    "871657100": "TMO",
    "251793107": "DHR",
    "693475105": "PEP",
    "92343V104": "UBER",
    "101137105": "LLY",
    "913903104": "VZ",
    "369604103": "HON",
    "253865106": "DE",
    "609207105": "LIN",
    "742718109": "RTX",
    "204214100": "EL",
    "500255101": "KMB",
    "98158L108": "WM",
}

NAME_TO_TICKER_MAP: Dict[str, str] = {
    "APPLE INC": "AAPL",
    "AMERICAN EXPRESS CO": "AXP",
    "BANK AMERICA CORP": "BAC",
    "COCA COLA CO": "KO",
    "CHEVRON CORP NEW": "CVX",
    "MOODYS CORP": "MCO",
    "OCCIDENTAL PETE CORP": "OXY",
    "KRAFT HEINZ CO": "KHC",
    "ALPHABET INC": "GOOGL",
    "MICROSOFT CORP": "MSFT",
    "META PLATFORMS INC": "META",
    "AMAZON COM INC": "AMZN",
    "NVIDIA CORP": "NVDA",
    "NVIDIA CORPORATION": "NVDA",
    "PALANTIR TECHNOLOGIES INC": "PLTR",
    "PFIZER INC": "PFE",
    "HALLIBURTON CO": "HAL",
    "LULULEMON ATHLETICA INC": "LULU",
    "MOLINA HEALTHCARE INC": "MOH",
    "SLM CORP": "SLM",
    "BRUKER CORP": "BRKR",
    "CHUBB LIMITED": "CB",
    "TESLA INC": "TSLA",
    "VISA INC": "V",
    "MASTERCARD INC": "MA",
    "MASTERCARD INCORPORATED": "MA",
    "KROGER CO": "KR",
    "SIRIUS XM HOLDINGS INC": "SIRI",
    "DAVITA INC": "DVA",
    "UBER TECHNOLOGIES INC": "UBER",
    "RESTAURANT BRANDS INTL INC": "QSR",
    "HOWARD HUGHES HOLDINGS INC": "HHC",
    "HILTON WORLDWIDE HLDGS INC": "HLT",
    "BROOKFIELD CORP": "BN",
    "SEAPORT ENTMT GROUP INC": "SEAR",
    "SEA LTD": "SE",
    "SELECT SECTOR SPDR TR": "XLF",
    "ISHARES INC": "IWM",
    "INVESCO EXCHANGE TRADED FD T": "QQQ",
    "NATERA INC": "NTRA",
    "INSMED INC": "INSM",
    "TEVA PHARMACEUTICAL INDS LTD": "TEVA",
    "WOODWARD INC": "WWD",
    "TAIWAN SEMICONDUCTOR MFG LTD": "TSM",
    "COUPANG INC": "CPNG",
    "NEW YORK TIMES CO": "NYT",
    "DOMINOS PIZZA INC": "DPZ",
    "DOMINOS PIZZA": "DPZ",
    "POOL CORP": "POOL",
    "AON PLC": "AON",
    "ATLANTA BRAVES HLDGS INC": "BATRA",
    "UNITEDHEALTH GROUP INC": "UNH",
    "REGENERON PHARMACEUTICALS": "REGN",
    "LAUDER ESTEE COS INC": "EL",
    "ESTEE LAUDER COMPANIES INC": "EL",
    "JD COM INC": "JD",
    "JD.COM INC": "JD",
    "LIBERTY MEDIA CORP": "LSXMK",
    "LIBERTY LIVE HOLDINGS INC": "LLYVA",
    "LIBERTY MEDIA CORP DEL": "LSXMA",
}


def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    
    name = name.upper().strip()
    
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    
    suffixes = [
        ' INC', ' CORP', ' CO', ' LTD', ' PLC', ' LLC', ' LP',
        ' HOLDINGS', ' HLDGS', ' GROUP', ' TECHNOLOGIES', ' PHARMACEUTICALS',
        ' INDUSTRIES', ' INTERNATIONAL', ' GLOBAL', ' SYSTEMS', ' SOLUTIONS',
        ' NEW', ' COM', ' COMN', ' CLASS A', ' CLASS B', ' CL A', ' CL B',
        ' SERIES A', ' SERIES B', ' SA', ' NV', ' DE', ' ORD',
        ' - THE', ' THE',
    ]
    
    for suffix in sorted(suffixes, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    
    return name.strip()


def get_ticker_from_cusip(cusip: str) -> Optional[str]:
    """
    Get ticker symbol from CUSIP.
    First checks built-in map, then tries FMP API if available.
    """
    if not cusip:
        return None
    
    cusip = cusip.strip().upper()
    
    if cusip in COMMON_CUSIP_MAP:
        return COMMON_CUSIP_MAP[cusip]
    
    if FMP_API_KEY:
        ticker = _fmp_cusip_lookup(cusip)
        if ticker:
            COMMON_CUSIP_MAP[cusip] = ticker
            return ticker
    
    return None


def get_ticker_from_name(name: str) -> Optional[str]:
    """
    Get ticker symbol from issuer name using fuzzy matching.
    """
    if not name:
        return None
    
    name_upper = name.upper().strip()
    
    if name_upper in NAME_TO_TICKER_MAP:
        return NAME_TO_TICKER_MAP[name_upper]
    
    normalized = normalize_name(name)
    
    for map_name, ticker in NAME_TO_TICKER_MAP.items():
        map_normalized = normalize_name(map_name)
        if normalized == map_normalized:
            return ticker
    
    for map_name, ticker in NAME_TO_TICKER_MAP.items():
        map_normalized = normalize_name(map_name)
        if normalized in map_normalized or map_normalized in normalized:
            return ticker
    
    for map_name, ticker in NAME_TO_TICKER_MAP.items():
        words = normalized.split()
        map_words = normalize_name(map_name).split()
        if len(words) >= 1 and len(map_words) >= 1:
            if words[0] == map_words[0]:
                common = set(words) & set(map_words)
                if len(common) >= min(2, len(words), len(map_words)):
                    return ticker
    
    return None


def get_ticker(name: str = "", cusip: str = "") -> Optional[str]:
    """
    Get ticker from either name or CUSIP (tries both).
    
    Args:
        name: Issuer name from 13F
        cusip: CUSIP from 13F
    
    Returns:
        Ticker symbol or None if not found
    """
    if cusip:
        ticker = get_ticker_from_cusip(cusip)
        if ticker:
            return ticker
    
    if name:
        ticker = get_ticker_from_name(name)
        if ticker:
            return ticker
    
    return None


def _fmp_cusip_lookup(cusip: str) -> Optional[str]:
    """Look up CUSIP using FMP API."""
    if not FMP_API_KEY:
        return None
    
    try:
        url = f"https://financialmodelingprep.com/api/v4/cusip/{cusip}?apikey={FMP_API_KEY}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                ticker = data[0].get("symbol")
                if ticker:
                    return ticker.upper()
            elif isinstance(data, dict):
                ticker = data.get("symbol")
                if ticker:
                    return ticker.upper()
        
        elif response.status_code == 402:
            logger.debug("FMP CUSIP endpoint returned 402 (subscription limited)")
        
    except Exception as e:
        logger.debug("FMP CUSIP lookup failed: %s", e)
    
    return None


def enhance_holding_with_ticker(holding: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add ticker symbol to a holding dict (modifies in-place).
    
    Args:
        holding: Dict with 'nameOfIssuer'/'name_of_issuer' and/or 'cusip'
    
    Returns:
        Same dict with 'ticker' field added (may be None)
    """
    name = holding.get('nameOfIssuer') or holding.get('name_of_issuer', '')
    cusip = holding.get('cusip', '')
    
    ticker = holding.get('ticker') or get_ticker(name=name, cusip=cusip)
    holding['ticker'] = ticker
    
    if ticker:
        holding['symbol'] = ticker
    else:
        holding['symbol'] = name[:8] if name else 'UNKNOWN'
    
    return holding


def enhance_holdings_with_tickers(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enhance multiple holdings with ticker symbols."""
    for holding in holdings:
        enhance_holding_with_ticker(holding)
    return holdings


def add_common_mapping(name: str, ticker: str, cusip: str = "") -> None:
    """Add a new name-to-ticker mapping (for runtime learning)."""
    if name:
        NAME_TO_TICKER_MAP[name.upper().strip()] = ticker.upper()
    if cusip:
        COMMON_CUSIP_MAP[cusip.upper().strip()] = ticker.upper()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_cases = [
        {"name": "APPLE INC", "cusip": "037833100"},
        {"name": "ALPHABET INC", "cusip": "02079K305"},
        {"name": "NVIDIA CORP", "cusip": "64110L106"},
        {"name": "BANK AMERICA CORP", "cusip": ""},
        {"name": "UNKNOWN COMPANY", "cusip": "000000000"},
    ]
    
    print("Testing CUSIP/ticker mapping:")
    print("-" * 60)
    
    for tc in test_cases:
        ticker = get_ticker(name=tc["name"], cusip=tc["cusip"])
        print(f'{tc["name"]:30} (CUSIP: {tc["cusip"]:11}) -> {ticker}')
