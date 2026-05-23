"""
sec_13f_db.py — 13F Historical Data Storage
=============================================

SQLite storage for 13F filings with quarter-over-quarter change detection.

Tables:
- sec_13f_filings: Metadata about each filing
- sec_13f_holdings: Individual holdings
- sec_13f_changes: Computed changes between quarters
"""

import sqlite3
import os
import json
import time
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("PERSISTENT_DB", os.path.join(os.path.dirname(__file__), "data", "stockguide.db"))

ALL_INVESTOR_CIKS: Dict[str, Dict[str, Optional[str]]] = {
    "buffett": {
        "cik": "0001067983",
        "name": "Warren Buffett",
        "firm": "Berkshire Hathaway",
        "style": "Quality / Long Term",
        "dataroma_code": "BRK",
    },
    "burry": {
        "cik": "0001649339",
        "name": "Michael Burry",
        "firm": "Scion Asset Management",
        "style": "Deep Value / Contrarian",
        "dataroma_code": "SAM",
    },
    "druckenmiller": {
        "cik": "0001536411",
        "name": "Stanley Druckenmiller",
        "firm": "Duquesne Family Office",
        "style": "Macro / Trend",
        "dataroma_code": None,
    },
    "pabrai": {
        "cik": "0001336528",
        "name": "Mohnish Pabrai",
        "firm": "Dalal Street LLC",
        "style": "Cloner / Deep Value",
        "dataroma_code": "PI",
    },
    "gates": {
        "cik": "0001166559",
        "name": "Bill & Melinda Gates Foundation",
        "firm": "Bill & Melinda Gates Foundation Trust",
        "style": "Long Term / Foundation",
        "dataroma_code": "GFT",
    },
    "einhorn": {
        "cik": "0001079114",
        "name": "David Einhorn",
        "firm": "Greenlight Capital",
        "style": "Value / Short Bias",
        "dataroma_code": "GLRE",
    },
    "jensen": {
        "cik": "0001106129",
        "name": "Jensen Investment Management",
        "firm": "Jensen Investment Management Inc",
        "style": "Quality Growth / Long Term",
        "dataroma_code": "JIM",
    },
    "aschenbrenner": {
        "cik": "0002045724",
        "name": "Leopold Aschenbrenner",
        "firm": "Situational Awareness LP",
        "style": "AGI-Focused / Long/Short Equity",
        "dataroma_code": None,
    },
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_13f_db():
    """Initialize 13F tables. Safe to call multiple times."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sec_13f_filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investor_id TEXT NOT NULL,
                cik TEXT NOT NULL,
                accession_number TEXT NOT NULL,
                quarter TEXT NOT NULL,
                report_date TEXT,
                filing_date TEXT,
                holdings_count INTEGER,
                total_value_raw INTEGER,
                total_value_millions REAL,
                fetched_at REAL NOT NULL,
                UNIQUE(investor_id, quarter)
            );
            
            CREATE TABLE IF NOT EXISTS sec_13f_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER NOT NULL,
                investor_id TEXT NOT NULL,
                quarter TEXT NOT NULL,
                name_of_issuer TEXT,
                title_of_class TEXT,
                cusip TEXT NOT NULL,
                ticker TEXT,
                value_raw INTEGER,
                value_millions REAL,
                shares INTEGER,
                shares_type TEXT,
                pct_of_portfolio REAL,
                FOREIGN KEY(filing_id) REFERENCES sec_13f_filings(id),
                UNIQUE(filing_id, cusip)
            );
            
            CREATE TABLE IF NOT EXISTS sec_13f_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investor_id TEXT NOT NULL,
                quarter TEXT NOT NULL,
                prev_quarter TEXT,
                cusip TEXT NOT NULL,
                ticker TEXT,
                name_of_issuer TEXT,
                change_type TEXT NOT NULL,
                prev_value_millions REAL,
                curr_value_millions REAL,
                value_change_millions REAL,
                value_change_pct REAL,
                prev_shares INTEGER,
                curr_shares INTEGER,
                shares_change INTEGER,
                shares_change_pct REAL,
                computed_at REAL NOT NULL,
                UNIQUE(investor_id, quarter, cusip)
            );
            
            CREATE INDEX IF NOT EXISTS idx_13f_filings_investor ON sec_13f_filings(investor_id);
            CREATE INDEX IF NOT EXISTS idx_13f_filings_quarter ON sec_13f_filings(quarter);
            CREATE INDEX IF NOT EXISTS idx_13f_holdings_investor ON sec_13f_holdings(investor_id);
            CREATE INDEX IF NOT EXISTS idx_13f_holdings_cusip ON sec_13f_holdings(cusip);
            CREATE INDEX IF NOT EXISTS idx_13f_changes_investor ON sec_13f_changes(investor_id);
            CREATE INDEX IF NOT EXISTS idx_13f_changes_type ON sec_13f_changes(change_type);
        """)
        conn.commit()
    finally:
        conn.close()


def save_filing(
    investor_id: str,
    quarter: str,
    filing_data: Dict[str, Any],
    holdings: List[Dict[str, Any]]
) -> int:
    """
    Save a 13F filing and its holdings to the database.
    
    Returns: filing_id
    """
    init_13f_db()
    
    from persistent_cache import db_write_lock
    
    cik = filing_data.get('cik', '')
    accession_number = filing_data.get('accession_number', '')
    report_date = filing_data.get('report_date')
    filing_date = filing_data.get('filing_date')
    holdings_count = len(holdings)
    total_value_raw = sum(h.get('value_raw', 0) for h in holdings)
    total_value_millions = total_value_raw / 1_000_000.0 if total_value_raw > 0 else 0.0
    fetched_at = time.time()
    
    rows = [(
        None, investor_id, quarter,
        h.get('nameOfIssuer', ''),
        h.get('titleOfClass', ''),
        h.get('cusip', ''),
        h.get('ticker', ''),
        h.get('value_raw', 0),
        h.get('value_millions', 0.0),
        h.get('sshPrnamt', 0),
        h.get('sshPrnamtType', ''),
        h.get('_pct_of_portfolio', 0.0) if '_pct_of_portfolio' in h else 0.0
    ) for h in holdings]
    
    with db_write_lock:
        conn = _get_conn()
        
        try:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO sec_13f_filings
                (investor_id, cik, accession_number, quarter, report_date, 
                 filing_date, holdings_count, total_value_raw, total_value_millions, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                investor_id, cik, accession_number, quarter, report_date,
                filing_date, holdings_count, total_value_raw, total_value_millions, fetched_at
            ))
            
            filing_id = cursor.lastrowid
            
            if filing_id == 0:
                row = conn.execute(
                    "SELECT id FROM sec_13f_filings WHERE investor_id = ? AND quarter = ?",
                    (investor_id, quarter)
                ).fetchone()
                if row:
                    filing_id = row['id']
                    conn.execute("DELETE FROM sec_13f_holdings WHERE filing_id = ?", (filing_id,))
            
            rows_with_id = [tuple([filing_id] + list(r[1:])) for r in rows]
            conn.executemany("""
                INSERT INTO sec_13f_holdings
                (filing_id, investor_id, quarter, name_of_issuer, title_of_class,
                 cusip, ticker, value_raw, value_millions, shares, shares_type, pct_of_portfolio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows_with_id)
            
            conn.commit()
            logger.info("Saved 13F filing for %s/%s with %d holdings (id=%d)",
                        investor_id, quarter, holdings_count, filing_id)
            return filing_id
            
        finally:
            conn.close()


def get_filing(investor_id: str, quarter: str) -> Optional[Dict[str, Any]]:
    """Get a specific filing with holdings."""
    init_13f_db()
    conn = _get_conn()
    
    try:
        filing_row = conn.execute("""
            SELECT * FROM sec_13f_filings WHERE investor_id = ? AND quarter = ?
        """, (investor_id, quarter)).fetchone()
        
        if not filing_row:
            return None
        
        filing = dict(filing_row)
        
        holdings_rows = conn.execute("""
            SELECT * FROM sec_13f_holdings WHERE filing_id = ? ORDER BY value_raw DESC
        """, (filing['id'],)).fetchall()
        
        filing['holdings'] = [dict(r) for r in holdings_rows]
        return filing
        
    finally:
        conn.close()


def get_all_quarters(investor_id: str) -> List[str]:
    """Get all quarters we have data for, sorted newest first."""
    init_13f_db()
    conn = _get_conn()
    
    try:
        rows = conn.execute("""
            SELECT quarter FROM sec_13f_filings 
            WHERE investor_id = ? ORDER BY report_date DESC
        """, (investor_id,)).fetchall()
        return [r['quarter'] for r in rows]
    finally:
        conn.close()


def get_prev_quarter(quarter: str) -> Optional[str]:
    """Get previous quarter (e.g., 'Q4 2025' -> 'Q3 2025', 'Q1 2025' -> 'Q4 2024')."""
    match = re.match(r'Q(\d)\s+(\d{4})', quarter)
    if not match:
        return None
    
    q = int(match.group(1))
    year = int(match.group(2))
    
    if q > 1:
        return f"Q{q-1} {year}"
    else:
        return f"Q4 {year-1}"


import re


def compute_changes(investor_id: str, curr_quarter: str) -> Dict[str, List[Dict]]:
    """
    Compute changes between current and previous quarter.
    
    Returns: {
        'new': [...],           # New positions
        'increased': [...],     # Increased positions
        'decreased': [...],     # Decreased positions
        'exited': [...],        # Sold out completely
        'held': [...]           # No significant change
    }
    """
    init_13f_db()
    
    curr_filing = get_filing(investor_id, curr_quarter)
    if not curr_filing:
        return {}
    
    prev_quarter = get_prev_quarter(curr_quarter)
    prev_filing = get_filing(investor_id, prev_quarter) if prev_quarter else None
    
    curr_holdings = {h['cusip']: h for h in curr_filing.get('holdings', [])}
    
    if not prev_filing:
        return {
            'new': [_format_change(c, 'NEW', None, c) for c in curr_holdings.values()],
            'increased': [],
            'decreased': [],
            'exited': [],
            'held': [],
        }
    
    prev_holdings = {h['cusip']: h for h in prev_filing.get('holdings', [])}
    
    new_positions = []
    increased = []
    decreased = []
    exited = []
    held = []
    
    for cusip, curr_h in curr_holdings.items():
        if cusip not in prev_holdings:
            new_positions.append(_format_change(curr_h, 'NEW', None, curr_h))
        else:
            prev_h = prev_holdings[cusip]
            change_type = _determine_change_type(prev_h, curr_h)
            if change_type == 'INCREASED':
                increased.append(_format_change(curr_h, 'INCREASED', prev_h, curr_h))
            elif change_type == 'DECREASED':
                decreased.append(_format_change(curr_h, 'DECREASED', prev_h, curr_h))
            else:
                held.append(_format_change(curr_h, 'HELD', prev_h, curr_h))
    
    for cusip, prev_h in prev_holdings.items():
        if cusip not in curr_holdings:
            exited.append(_format_change(prev_h, 'EXITED', prev_h, None))
    
    return {
        'new': sorted(new_positions, key=lambda x: x.get('curr_value_millions', 0), reverse=True),
        'increased': sorted(increased, key=lambda x: x.get('value_change_millions', 0), reverse=True),
        'decreased': sorted(decreased, key=lambda x: x.get('value_change_millions', 0)),
        'exited': sorted(exited, key=lambda x: x.get('prev_value_millions', 0), reverse=True),
        'held': sorted(held, key=lambda x: x.get('curr_value_millions', 0), reverse=True),
    }


def _format_change(holding: Dict, change_type: str, prev_h: Optional[Dict], curr_h: Optional[Dict]) -> Dict:
    """Format a change entry for UI consumption."""
    prev_val = prev_h.get('value_millions', 0) if prev_h else 0
    curr_val = curr_h.get('value_millions', 0) if curr_h else 0
    prev_shares = prev_h.get('shares', 0) if prev_h else 0
    curr_shares = curr_h.get('shares', 0) if curr_h else 0
    
    value_change = curr_val - prev_val
    shares_change = curr_shares - prev_shares
    
    value_change_pct = 0.0
    if prev_val > 0:
        value_change_pct = (value_change / prev_val) * 100
    elif curr_val > 0:
        value_change_pct = 100.0
    
    shares_change_pct = 0.0
    if prev_shares > 0:
        shares_change_pct = (shares_change / prev_shares) * 100
    elif curr_shares > 0:
        shares_change_pct = 100.0
    
    return {
        'symbol': holding.get('ticker', holding.get('name_of_issuer', '')[:8]),
        'name': holding.get('name_of_issuer', ''),
        'cusip': holding.get('cusip', ''),
        'change_type': change_type,
        'prev_value_millions': round(prev_val, 1),
        'curr_value_millions': round(curr_val, 1),
        'value_change_millions': round(value_change, 1),
        'value_change_pct': round(value_change_pct, 1),
        'prev_shares': prev_shares,
        'curr_shares': curr_shares,
        'shares_change': shares_change,
        'shares_change_pct': round(shares_change_pct, 1),
    }


def _determine_change_type(prev_h: Dict, curr_h: Dict) -> str:
    """Determine if position increased, decreased, or held."""
    prev_shares = prev_h.get('shares', 0)
    curr_shares = curr_h.get('shares', 0)
    
    if curr_shares > prev_shares * 1.05:
        return 'INCREASED'
    elif curr_shares < prev_shares * 0.95:
        return 'DECREASED'
    else:
        return 'HELD'


def get_all_investors_metadata() -> Dict[str, Dict]:
    """Get metadata for all tracked investors."""
    return ALL_INVESTOR_CIKS.copy()


def get_tracked_investor_ids() -> List[str]:
    """Get list of all tracked investor IDs."""
    return list(ALL_INVESTOR_CIKS.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing SEC 13F DB...")
    init_13f_db()
    print("DB initialized")
    
    print("\nAll tracked investors:")
    for inv_id, meta in get_all_investors_metadata().items():
        print(f"  {inv_id}: {meta['name']} ({meta['firm']}) - CIK {meta['cik']}")
