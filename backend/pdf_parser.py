"""
WealthSimple PDF Parser
Analyzes WealthSimple portfolio statements and extracts position data
"""

import sys
import os
# Add user site-packages to path just in case
sys.path.append(os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))

import pdfplumber
import re
from typing import List, Dict

def analyze_wealthsimple_pdf(pdf_path: str) -> Dict:
    """
    Analyze a WealthSimple PDF to understand its structure.
    Returns extracted text and tables for inspection.
    """
    with pdfplumber.open(pdf_path) as pdf:
        analysis = {
            'num_pages': len(pdf.pages),
            'pages': []
        }
        
        for i, page in enumerate(pdf.pages):
            page_data = {
                'page_num': i + 1,
                'text': page.extract_text(),
                'tables': page.extract_tables()
            }
            analysis['pages'].append(page_data)
        
        return analysis

def parse_wealthsimple_positions(pdf_path: str) -> List[Dict]:
    """
    Parse WealthSimple PDF and extract portfolio positions.
    Returns list of positions with ticker, quantity, etc.
    """
    positions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Use text-based extraction for all pages
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            
            for line in lines:
                # Skip header lines/irrelevant info
                if "Portfolio Assets" in line or "Symbol" in line:
                    continue
                    
                # Pattern: 
                # Name Ticker Qty1 Qty2 Price Currency Value Cost
                # Example: Vanguard S&P 500 Index ETF VFV 12.8013 12.8013 $166.62 CAD $2,132.95 $1,937.13
                
                try:
                    # Look for the pattern: Ticker followed by two numbers
                    # Example: VFV 12.8013 12.8013
                    # Ticker can be 1-5 chars, maybe containing dot (like BRK.B)
                    match = re.search(r'\s([A-Z]{1,5}\.?[A-Z]{0,2})\s+(\d+\.\d{4})\s+(\d+\.\d{4})', line)
                    
                    if match:
                        ticker = match.group(1)
                        quantity = float(match.group(2))
                        
                        # Now try to find the cost (last dollar amount)
                        # Clean line of currency codes to avoid confusion
                        clean_line = line.replace('CAD', '').replace('USD', '')
                        
                        # Find all dollar amounts
                        amounts = re.findall(r'\$?([\d,]+\.\d{2})', clean_line)
                        
                        if len(amounts) >= 1:
                            # Typically: Price, Market Value, Book Cost
                            # If we have multiple, the last one is usually Book Cost
                            # If only 2 (Price, Value), we might be missing cost?
                            # WealthSimple format usually has Price, Value, Cost
                            cost_total = float(amounts[-1].replace(',', ''))
                            avg_cost = cost_total / quantity if quantity > 0 else 0
                        else:
                            avg_cost = 0
                        
                        # Determine currency from original line
                        currency = 'USD' if 'USD' in line else 'CAD'
                        
                        # Ignore non-stock items if they appear
                        if ticker in ['CASH', 'TOTAL', 'BAL']:
                            continue
                            
                        positions.append({
                            'ticker': ticker,
                            'quantity': quantity,
                            'avg_cost': avg_cost,
                            'currency': currency,
                            'notes': f'Imported from WealthSimple ({currency})'
                        })
                except Exception as e:
                    # Silently skip parse errors for non-position lines
                    continue
    
    return positions

if __name__ == "__main__":
    # Test the parser
    pdf_path = "portfolios/WealthSimple/portfoliows.pdf"
    
    print("Analyzing WealthSimple PDF...")
    analysis = analyze_wealthsimple_pdf(pdf_path)
    
    print(f"\nFound {analysis['num_pages']} pages")
    
    for page_data in analysis['pages']:
        print(f"\n=== Page {page_data['page_num']} ===")
        print("\nText Preview:")
        print(page_data['text'][:500] if page_data['text'] else "No text found")
        
        if page_data['tables']:
            print(f"\nFound {len(page_data['tables'])} tables")
            for i, table in enumerate(page_data['tables']):
                print(f"\nTable {i+1}:")
                if table and len(table) > 0:
                    print(f"Headers: {table[0]}")
                    print(f"Rows: {len(table) - 1}")
    
    print("\n" + "="*50)
    print("Attempting to parse positions...")
    positions = parse_wealthsimple_positions(pdf_path)
    
    print(f"\nExtracted {len(positions)} positions:")
    for pos in positions:
        print(f"  {pos['ticker']}: {pos['quantity']} shares @ ${pos['avg_cost']}")
