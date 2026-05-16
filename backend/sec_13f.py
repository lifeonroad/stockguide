"""
sec_13f.py — SEC EDGAR 13F Filing Fetcher
===========================================

Direct SEC EDGAR API access for 13F-HR filings (free, no API key required).
Uses SEC's public data APIs: https://data.sec.gov/

Features:
- Fetch latest OR historical 13F filings
- Auto-detect value units (dollars vs thousands) via price-per-share calculation
- Store historical data in SQLite for change detection
- Compute quarter-over-quarter changes (buys/sells/increases/decreases)

SEC Requires:
- User-Agent header in format: "Company Name contact@email.com"
"""

import requests
import xml.etree.ElementTree as ET
import re
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Stockguide App contact@example.com")

from sec_13f_db import (
    ALL_INVESTOR_CIKS as _ALL_CIKS,
    init_13f_db,
    save_filing,
    get_filing,
    get_all_quarters,
    compute_changes,
)

INVESTOR_CIKS = {k: v["cik"] for k, v in _ALL_CIKS.items()}
INVESTOR_NAMES = {k: v["name"] for k, v in _ALL_CIKS.items()}
INVESTOR_FIRMS = {k: v["firm"] for k, v in _ALL_CIKS.items()}
INVESTOR_STYLES = {k: v["style"] for k, v in _ALL_CIKS.items()}


def _enhance_holdings(filing_or_holdings):
    """Add ticker symbols to holdings in-place (handles both dict and list)."""
    from cusip_utils import enhance_holdings_with_tickers
    if isinstance(filing_or_holdings, dict):
        holdings = filing_or_holdings.get('holdings', [])
        enhance_holdings_with_tickers(holdings)
    elif isinstance(filing_or_holdings, list):
        enhance_holdings_with_tickers(filing_or_holdings)


def _get_submissions_url(cik: str) -> str:
    """Get URL for submissions JSON for a CIK."""
    cik_padded = cik.zfill(10)
    return f"https://data.sec.gov/submissions/CIK{cik_padded}.json"


def _format_quarter(report_date: str) -> str:
    """Convert YYYY-MM-DD to 'Qn YYYY' format."""
    try:
        dt = datetime.strptime(report_date, "%Y-%m-%d")
        quarter = ((dt.month - 1) // 3) + 1
        return f"Q{quarter} {dt.year}"
    except:
        return report_date


def get_all_13f_filings(cik: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Get ALL recent 13F-HR filings for a CIK (for historical tracking).
    
    Args:
        cik: Investor CIK
        limit: Maximum number of filings to return (default 8 = 2 years of quarters)
    
    Returns:
        List of filing dicts, newest first
    """
    cik = cik.zfill(10)
    url = _get_submissions_url(cik)
    headers = {"User-Agent": SEC_USER_AGENT}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        recent = data.get("filings", {}).get("recent", {})
        form_types = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        report_dates = recent.get("reportDate", [])
        filing_dates = recent.get("filingDate", [])
        
        filings = []
        seen_quarters = set()
        
        for i, form_type in enumerate(form_types):
            if form_type in ["13F-HR", "13F-HR/A"]:
                accession = accession_numbers[i] if i < len(accession_numbers) else ""
                report_date = report_dates[i] if i < len(report_dates) else ""
                filing_date = filing_dates[i] if i < len(filing_dates) else ""
                quarter = _format_quarter(report_date) if report_date else ""
                
                if quarter and quarter in seen_quarters:
                    if form_type != "13F-HR/A":
                        continue
                
                seen_quarters.add(quarter)
                filings.append({
                    "accessionNumber": accession,
                    "reportDate": report_date,
                    "filingDate": filing_date,
                    "formType": form_type,
                    "cik": cik,
                    "quarter": quarter,
                })
                
                if len(filings) >= limit:
                    break
        
        logger.info("Found %d historical 13F filings for CIK %s", len(filings), cik)
        return filings
        
    except Exception as e:
        logger.error("Failed to get 13F filings for CIK %s: %s", cik, e)
        return []


def get_latest_13f_filing(cik: str) -> Optional[Dict[str, Any]]:
    """
    Get the most recent 13F-HR filing for a CIK.
    
    Returns:
        dict with 'accessionNumber', 'reportDate', 'filingDate', 'formType', 'quarter'
        or None if not found
    """
    filings = get_all_13f_filings(cik, limit=1)
    return filings[0] if filings else None


def _get_filing_index(cik: str, accession_number: str) -> List[Dict[str, Any]]:
    """
    Get list of files in a filing directory from SEC EDGAR index.json.
    Returns list of file info dicts with 'name', 'type', 'size'.
    """
    cik_stripped = cik.lstrip('0')
    accession_clean = accession_number.replace('-', '')
    
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_stripped}/{accession_clean}/index.json"
    
    try:
        headers = {"User-Agent": SEC_USER_AGENT}
        response = requests.get(index_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        files = data.get("directory", {}).get("item", [])
        return files if isinstance(files, list) else []
        
    except Exception as e:
        logger.error("Failed to get filing index for %s/%s: %s", cik, accession_number, e)
        return []


def _find_infotable_xml(cik: str, accession_number: str) -> Optional[str]:
    """
    Find the XML file that contains 13F holdings (infoTable).
    Returns the filename or None.
    """
    files = _get_filing_index(cik, accession_number)
    
    xml_files = [f.get("name", "") for f in files if f.get("name", "").endswith(".xml")]
    logger.debug("XML files in filing: %s", xml_files)
    
    cik_stripped = cik.lstrip('0')
    accession_clean = accession_number.replace('-', '')
    headers = {"User-Agent": SEC_USER_AGENT}
    
    for xml_name in xml_files:
        if xml_name == "primary_doc.xml":
            continue
        
        try:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik_stripped}/{accession_clean}/{xml_name}"
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text[:5000]
                if "<infoTable" in content or "<nameOfIssuer" in content:
                    logger.info("Found infoTable in %s", xml_name)
                    return xml_name
                    
        except Exception as e:
            logger.debug("Error checking %s: %s", xml_name, e)
            continue
    
    return None


def detect_value_multiplier(holdings: List[Dict[str, Any]]) -> int:
    """
    Detect if the value field is in dollars or thousands of dollars.
    
    SEC spec says value should be in thousands, but in practice:
    - Some filers (Berkshire) report in actual dollars
    - Some filers (Duquesne) report in thousands
    
    We detect by calculating implied price per share.
    If price < $1, value is likely in thousands (multiply by 1000).
    If price is reasonable ($1-$10,000), value is in dollars.
    
    Returns: 1 or 1000
    """
    if not holdings:
        return 1
    
    sample_prices = []
    for h in holdings[:20]:
        shares = h.get('_shares', 0)
        value = h.get('_value_raw', 0)
        
        if shares > 0 and value > 0:
            implied_price = value / shares
            sample_prices.append(implied_price)
    
    if not sample_prices:
        return 1
    
    median_price = sorted(sample_prices)[len(sample_prices) // 2]
    
    if median_price < 1.0:
        logger.debug("Detected value in thousands (median price: $%.4f), will multiply by 1000", median_price)
        return 1000
    else:
        logger.debug("Detected value in dollars (median price: $%.2f)", median_price)
        return 1


def parse_13f_holdings_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    Parse 13F holdings information table from XML format.
    Auto-detects if values are in dollars or thousands and normalizes to dollars.
    
    Returns list of holdings with normalized values.
    """
    raw_holdings = []
    
    try:
        xml_simple = re.sub(r'xmlns="[^"]+"', '', xml_content)
        xml_simple = re.sub(r'ns\d+:', '', xml_simple)
        
        root = ET.fromstring(xml_simple)
        
        for info_table in root.findall('.//infoTable'):
            holding = {}
            
            name_elem = info_table.find('nameOfIssuer')
            holding['nameOfIssuer'] = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            
            class_elem = info_table.find('titleOfClass')
            holding['titleOfClass'] = class_elem.text.strip() if class_elem is not None and class_elem.text else "COM"
            
            cusip_elem = info_table.find('cusip')
            holding['cusip'] = cusip_elem.text.strip() if cusip_elem is not None and cusip_elem.text else ""
            
            value_elem = info_table.find('value')
            try:
                value_raw = int(value_elem.text.strip()) if value_elem is not None and value_elem.text else 0
                holding['_value_raw'] = value_raw
            except (ValueError, TypeError):
                holding['_value_raw'] = 0
            
            shrs_elem = info_table.find('shrsOrPrnAmt')
            if shrs_elem is not None:
                ssh_elem = shrs_elem.find('sshPrnamt')
                try:
                    holding['_shares'] = int(ssh_elem.text.strip()) if ssh_elem is not None and ssh_elem.text else 0
                except (ValueError, TypeError):
                    holding['_shares'] = 0
                
                type_elem = shrs_elem.find('sshPrnamtType')
                holding['sshPrnamtType'] = type_elem.text.strip() if type_elem is not None and type_elem.text else "SH"
            else:
                holding['_shares'] = 0
                holding['sshPrnamtType'] = "SH"
            
            raw_holdings.append(holding)
            
    except Exception as e:
        logger.error("Failed to parse 13F XML: %s", e)
    
    multiplier = detect_value_multiplier(raw_holdings)
    
    normalized_holdings = []
    for h in raw_holdings:
        value_raw = h.get('_value_raw', 0)
        shares = h.get('_shares', 0)
        
        value_dollars = value_raw * multiplier
        
        normalized = {
            'nameOfIssuer': h.get('nameOfIssuer', ''),
            'titleOfClass': h.get('titleOfClass', 'COM'),
            'cusip': h.get('cusip', ''),
            'value_raw': value_raw,
            'value': value_dollars,
            'value_thousands': value_dollars / 1000.0,
            'value_millions': value_dollars / 1_000_000.0,
            'sshPrnamt': shares,
            'sshPrnamtType': h.get('sshPrnamtType', 'SH'),
            '_multiplier_used': multiplier,
        }
        normalized_holdings.append(normalized)
    
    logger.info("Normalized %d holdings with multiplier %d", len(normalized_holdings), multiplier)
    return normalized_holdings


def aggregate_holdings_by_cusip(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate multiple entries for the same CUSIP (same issuer can appear multiple times 
    with different 'otherManager' values).
    
    Returns consolidated list sorted by total value descending.
    """
    aggregated: Dict[str, Dict[str, Any]] = {}
    
    for h in holdings:
        cusip = h.get('cusip', '')
        if not cusip:
            continue
        
        if cusip in aggregated:
            aggregated[cusip]['value_raw'] += h.get('value_raw', 0)
            aggregated[cusip]['value'] += h.get('value', 0)
            aggregated[cusip]['value_thousands'] += h.get('value_thousands', 0.0)
            aggregated[cusip]['value_millions'] += h.get('value_millions', 0.0)
            aggregated[cusip]['sshPrnamt'] += h.get('sshPrnamt', 0)
        else:
            aggregated[cusip] = {
                'nameOfIssuer': h.get('nameOfIssuer', ''),
                'titleOfClass': h.get('titleOfClass', 'COM'),
                'cusip': cusip,
                'value_raw': h.get('value_raw', 0),
                'value': h.get('value', 0),
                'value_thousands': h.get('value_thousands', 0.0),
                'value_millions': h.get('value_millions', 0.0),
                'sshPrnamt': h.get('sshPrnamt', 0),
                'sshPrnamtType': h.get('sshPrnamtType', 'SH'),
            }
    
    result = list(aggregated.values())
    result.sort(key=lambda x: x.get('value', 0), reverse=True)
    
    total_value = sum(h.get('value', 0) for h in result)
    if total_value > 0:
        for h in result:
            h['_pct_of_portfolio'] = (h.get('value', 0) / total_value) * 100
    else:
        for h in result:
            h['_pct_of_portfolio'] = 0.0
    
    return result


def fetch_13f_holdings_by_accession(cik: str, accession_number: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch and parse 13F holdings for a specific filing (by accession number).
    
    Returns:
        List of aggregated holdings, or None if failed
    """
    cik_stripped = cik.lstrip('0')
    accession_clean = accession_number.replace('-', '')
    headers = {"User-Agent": SEC_USER_AGENT}
    
    infotable_filename = _find_infotable_xml(cik, accession_number)
    if not infotable_filename:
        logger.warning("Could not find infoTable XML for accession %s", accession_number)
        return None
    
    infotable_url = f"https://www.sec.gov/Archives/edgar/data/{cik_stripped}/{accession_clean}/{infotable_filename}"
    
    try:
        logger.info("Fetching holdings from: %s", infotable_url)
        response = requests.get(infotable_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        holdings = parse_13f_holdings_xml(response.text)
        holdings_aggregated = aggregate_holdings_by_cusip(holdings)
        
        return holdings_aggregated
    
    except Exception as e:
        logger.error("Failed to fetch/parse 13F holdings: %s", e)
        return None


def get_investor_13f_holdings(investor_id: str, quarter: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get 13F holdings for a specific investor.
    
    Args:
        investor_id: 'buffett', 'burry', 'druckenmiller', 'pabrai', etc.
        quarter: Optional specific quarter (e.g., 'Q4 2025'). If None, returns latest.
    
    Returns:
        dict with investor info and holdings, or None if failed
    """
    init_13f_db()
    
    cik = INVESTOR_CIKS.get(investor_id)
    if not cik:
        logger.error("Unknown investor ID: %s", investor_id)
        return None
    
    if quarter:
        cached = get_filing(investor_id, quarter)
        if cached:
            logger.info("Found cached filing for %s/%s", investor_id, quarter)
            _enhance_holdings(cached)
            return cached
    
    if quarter:
        all_filings = get_all_13f_filings(cik, limit=20)
        filing = next((f for f in all_filings if f.get('quarter') == quarter), None)
    else:
        filings = get_all_13f_filings(cik, limit=1)
        filing = filings[0] if filings else None
    
    if not filing:
        logger.warning("No 13F filing found for investor %s", investor_id)
        return None
    
    accession = filing.get('accessionNumber')
    quarter_result = filing.get('quarter')
    
    holdings = fetch_13f_holdings_by_accession(cik, accession)
    if not holdings:
        return None
    
    _enhance_holdings(holdings)
    
    filing_data = {
        'cik': cik,
        'accession_number': accession,
        'report_date': filing.get('reportDate'),
        'filing_date': filing.get('filingDate'),
    }
    
    save_filing(investor_id, quarter_result, filing_data, holdings)
    
    result = get_filing(investor_id, quarter_result)
    if result:
        _enhance_holdings(result)
    return result


def fetch_and_store_historical(investor_id: str, quarters: int = 4) -> int:
    """
    Fetch and store multiple historical quarters for an investor.
    
    Args:
        investor_id: Investor ID
        quarters: Number of recent quarters to fetch (default 4 = 1 year)
    
    Returns:
        Number of filings successfully stored
    """
    init_13f_db()
    
    cik = INVESTOR_CIKS.get(investor_id)
    if not cik:
        logger.error("Unknown investor ID: %s", investor_id)
        return 0
    
    existing_quarters = set(get_all_quarters(investor_id))
    logger.info("Already have %d quarters for %s: %s", len(existing_quarters), investor_id, existing_quarters)
    
    filings = get_all_13f_filings(cik, limit=quarters)
    stored = 0
    
    for filing in filings:
        quarter = filing.get('quarter')
        
        if quarter in existing_quarters:
            logger.info("Quarter %s already cached, skipping", quarter)
            continue
        
        accession = filing.get('accessionNumber')
        holdings = fetch_13f_holdings_by_accession(cik, accession)
        
        if holdings:
            filing_data = {
                'cik': cik,
                'accession_number': accession,
                'report_date': filing.get('reportDate'),
                'filing_date': filing.get('filingDate'),
            }
            save_filing(investor_id, quarter, filing_data, holdings)
            stored += 1
        
        time.sleep(0.5)
    
    return stored


def get_investor_with_changes(investor_id: str) -> Optional[Dict[str, Any]]:
    """
    Get investor data with computed quarter-over-quarter changes.
    
    Returns:
        dict with investor info, holdings, and computed changes
    """
    init_13f_db()
    
    latest = get_investor_13f_holdings(investor_id)
    if not latest:
        return None
    
    quarter = latest.get('quarter')
    changes = compute_changes(investor_id, quarter)
    
    result = dict(latest)
    result['changes'] = changes
    
    holdings = result.get('holdings', [])
    from cusip_utils import enhance_holdings_with_tickers, get_ticker as _lookup_ticker
    enhance_holdings_with_tickers(holdings)
    
    for h in holdings:
        if 'ticker' in h and h['ticker']:
            h['symbol'] = h['ticker']
        else:
            h['symbol'] = h.get('name_of_issuer', h.get('nameOfIssuer', 'Unknown'))[:8]
    
    for change_type, items in changes.items():
        for item in items:
            if not item.get('symbol') or len(item.get('symbol', '')) < 2:
                ticker = _lookup_ticker(cusip=item.get('cusip', ''), name=item.get('name', ''))
                if ticker:
                    item['symbol'] = ticker
    
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing SEC EDGAR 13F fetcher...")
    
    print("\n=== Fetching historical data for Warren Buffett ===")
    stored = fetch_and_store_historical('buffett', quarters=3)
    print(f"Stored {stored} new filings")
    
    print("\n=== Getting latest with changes ===")
    result = get_investor_with_changes('buffett')
    if result:
        print(f"Investor: {result.get('investor_id')}")
        print(f"Quarter: {result.get('quarter')}")
        print(f"Holdings: {result.get('holdings_count')}")
        
        changes = result.get('changes', {})
        if changes:
            print(f"\nChanges detected:")
            for change_type, items in changes.items():
                if items:
                    print(f"  {change_type.upper()}: {len(items)} positions")
                    for item in items[:3]:
                        print(f"    - {item.get('symbol')}: {item.get('name')}")
