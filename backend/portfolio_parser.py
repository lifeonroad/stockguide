"""
Portfolio Parser — parses WealthSimple CSV and PDF files into position lists.
Reads from known file paths for server-side import.
"""

import csv
import os
import re
from typing import List, Dict, Optional

# Known file locations
PORTFOLIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolios', 'WealthSimple')
CSV_PATH = os.path.join(PORTFOLIO_DIR, 'holdings-report-2026-05-09.csv')
PDF_PATH = os.path.join(PORTFOLIO_DIR, 'portfoliows.pdf')


def parse_csv_positions(filepath: str = CSV_PATH) -> List[Dict]:
    """Parse WealthSimple holdings CSV into position list."""
    positions = []
    if not os.path.exists(filepath):
        return positions

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            try:
                ticker = (row.get('Symbol') or '').strip()
                if not ticker:
                    continue

                qty_str = (row.get('Quantity') or '0').strip()
                quantity = float(qty_str) if qty_str else 0
                if quantity <= 0:
                    continue

                book_cad_str = (row.get('Book Value (CAD)') or '0').strip().replace(',', '')
                book_cad = float(book_cad_str) if book_cad_str else 0

                price_currency = (row.get('Market Price Currency') or 'USD').strip()

                avg_cost = book_cad / quantity if quantity > 0 else 0

                positions.append({
                    'ticker': ticker,
                    'quantity': quantity,
                    'avg_cost': round(avg_cost, 2),
                    'currency': price_currency,
                    'account_type': (row.get('Account Type') or '').strip(),
                    'account_name': (row.get('Account Name') or '').strip(),
                    'security_type': (row.get('Security Type') or '').strip(),
                    'market_price': float((row.get('Market Price') or '0').replace(',', '')),
                    'market_value': float((row.get('Market Value') or '0').replace(',', '')),
                    'book_value_cad': book_cad,
                    'name': (row.get('Name') or '').strip(),
                    'notes': f'Imported from WealthSimple CSV ({price_currency})',
                })
            except (ValueError, KeyError, TypeError) as e:
                continue

    return positions


def parse_pdf_positions(filepath: str = PDF_PATH) -> List[Dict]:
    """Parse WealthSimple PDF into position list using existing parser."""
    try:
        from pdf_parser import parse_wealthsimple_positions
        return parse_wealthsimple_positions(filepath)
    except Exception:
        return []


def parse_all() -> List[Dict]:
    """Parse all available files and return merged position list (CSV preferred)."""
    positions = parse_csv_positions()
    if positions:
        return positions
    return parse_pdf_positions()


def get_available_files() -> List[Dict]:
    """List available portfolio files with metadata."""
    files = []
    if os.path.exists(PORTFOLIO_DIR):
        for fname in sorted(os.listdir(PORTFOLIO_DIR)):
            fpath = os.path.join(PORTFOLIO_DIR, fname)
            if os.path.isfile(fpath):
                files.append({
                    'name': fname,
                    'path': fpath,
                    'size_bytes': os.path.getsize(fpath),
                    'type': 'csv' if fname.endswith('.csv') else 'pdf' if fname.endswith('.pdf') else 'other',
                })
    return files


if __name__ == '__main__':
    positions = parse_csv_positions()
    print(f'CSV: {len(positions)} positions')
    if positions:
        for p in positions[:5]:
            print(f'  {p["ticker"]}: {p["quantity"]} @ ${p["avg_cost"]} ({p["currency"]}) [{p["account_type"]}]')

    pdf_positions = parse_pdf_positions()
    print(f'\nPDF: {len(pdf_positions)} positions')
    if pdf_positions:
        for p in pdf_positions[:5]:
            print(f'  {p["ticker"]}: {p["quantity"]} @ ${p["avg_cost"]} ({p["currency"]})')
