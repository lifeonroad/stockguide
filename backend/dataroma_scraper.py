"""
dataroma_scraper.py — Dataroma.com page fetcher and parser
==========================================================

Provides manual/exploratory data access to Dataroma's superinvestor pages.
Each function fetches a specific page type, parses it, and returns structured data.

Page types supported:
  - holdings    Current portfolio positions
  - activity    All/buys/sells activity (paginated)
  - history     Quarter-by-quarter portfolio composition
  - stock_hist  Per-stock activity history for a manager

Usage (from validation page):
  1. User selects a manager code + page type
  2. Backend fetches from Dataroma with browser-like headers
  3. Parses HTML into structured JSON
  4. Returns to frontend for display + manual inspection
"""

import requests
import logging
import time
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dataroma.com/m"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

REFERERS = {
    "holdings": "https://www.dataroma.com/m/holdings.php",
    "activity": "https://www.dataroma.com/m/holdings.php",
    "history": "https://www.dataroma.com/m/holdings.php",
    "stock_hist": "https://www.dataroma.com/m/hist/p_hist.php",
    "all_managers": "https://www.dataroma.com/m/managers.php",
    "grand_portfolio": "https://www.dataroma.com/m/g/portfolio.php",
    "grand_portfolio_qtr_buys": "https://www.dataroma.com/m/g/portfolio.php",
    "grand_portfolio_qtr_sells": "https://www.dataroma.com/m/g/portfolio.php",
    "grand_portfolio_6mo_buys": "https://www.dataroma.com/m/g/portfolio.php",
    "grand_portfolio_6mo_sells": "https://www.dataroma.com/m/g/portfolio.php",
    "grand_portfolio_sector": "https://www.dataroma.com/m/g/portfolio.php",
    "all_activity": "https://www.dataroma.com/m/allact.php",
}

ALL_PAGE_TYPES = [
    "holdings", "activity", "activity_buys", "activity_sells",
    "history", "stock_hist",
    "all_managers", "grand_portfolio", "grand_portfolio_qtr_buys",
    "grand_portfolio_qtr_sells", "grand_portfolio_6mo_buys",
    "grand_portfolio_6mo_sells", "grand_portfolio_sector",
    "all_activity",
]

# Mapping from our internal page types to Dataroma URL params
PAGE_ROUTES = {
    "holdings": "/holdings.php",
    "activity": "/m_activity.php",
    "activity_buys": "/m_activity.php",
    "activity_sells": "/m_activity.php",
    "history": "/hist/p_hist.php",
    "stock_hist": "/hist/hist.php",
    "all_managers": "/managers.php",
    "grand_portfolio": "/g/portfolio.php",
    "grand_portfolio_qtr_buys": "/g/portfolio.php",
    "grand_portfolio_qtr_sells": "/g/portfolio.php",
    "grand_portfolio_6mo_buys": "/g/portfolio.php",
    "grand_portfolio_6mo_sells": "/g/portfolio.php",
    "grand_portfolio_sector": "/g/portfolio.php",
    "all_activity": "/allact.php",
}

_LAST_FETCH_TIME = 0.0
_MIN_INTERVAL = 3.0

def _respectful_delay():
    global _LAST_FETCH_TIME
    now = time.time()
    elapsed = now - _LAST_FETCH_TIME
    if elapsed < _MIN_INTERVAL:
        sleep_time = _MIN_INTERVAL - elapsed
        logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
        time.sleep(sleep_time)
    _LAST_FETCH_TIME = time.time()

def _fetch_page(url: str, referer: str) -> Optional[str]:
    _respectful_delay()
    headers = {**BROWSER_HEADERS, "Referer": referer}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            logger.warning(f"Unexpected content type: {content_type} for {url}")
        text = resp.text
        if "Not Acceptable" in text[:200] or "Mod_Security" in text[:200]:
            logger.warning(f"Blocked by WAF: {url}")
            return None
        return text
    except requests.RequestException as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return None


def _soup(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "lxml")


def fetch_holdings(manager_code: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/holdings.php?m={manager_code}"
    html = _fetch_page(url, REFERERS["holdings"])
    if not html:
        return {"error": "Failed to fetch holdings page (blocked or timeout)", "raw_html": None}
    soup = _soup(html)

    header_info = _parse_header(soup)
    holdings = _parse_holdings_table(soup)

    return {
        "manager": manager_code,
        "page_type": "holdings",
        "page_url": url,
        "header": header_info,
        "holdings": holdings,
        "holdings_count": len(holdings),
    }


def fetch_activity(manager_code: str, typ: str = "a", page: int = 1) -> Dict[str, Any]:
    typ_map = {"a": "a", "b": "b", "s": "s", "all": "a", "buys": "b", "sells": "s"}
    t = typ_map.get(typ, "a")
    url = f"{BASE_URL}/m_activity.php?m={manager_code}&typ={t}&L={page}"
    html = _fetch_page(url, REFERERS["activity"])
    if not html:
        return {"error": f"Failed to fetch activity page (typ={t} page={page})", "raw_html": None}
    soup = _soup(html)

    activities = _parse_activity_table(soup)
    pagination = _parse_pagination(soup)

    return {
        "manager": manager_code,
        "page_type": f"activity_{typ}",
        "page_url": url,
        "page": page,
        "pagination": pagination,
        "activities": activities,
        "activities_count": len(activities),
    }


def fetch_history(manager_code: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/hist/p_hist.php?f={manager_code}"
    html = _fetch_page(url, REFERERS["history"])
    if not html:
        return {"error": "Failed to fetch history page", "raw_html": None}
    soup = _soup(html)

    periods, stock_names = _parse_history_table(soup)

    return {
        "manager": manager_code,
        "page_type": "history",
        "page_url": url,
        "periods": periods,
        "period_count": len(periods),
        "stock_names": stock_names,
    }


def fetch_stock_history(manager_code: str, symbol: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/hist/hist.php?f={manager_code}&s={symbol.upper()}"
    html = _fetch_page(url, REFERERS["stock_hist"])
    if not html:
        return {"error": f"Failed to fetch stock history for {symbol}", "raw_html": None}
    soup = _soup(html)

    entries = _parse_stock_history(soup)

    return {
        "manager": manager_code,
        "symbol": symbol.upper(),
        "page_type": "stock_hist",
        "page_url": url,
        "entries": entries,
        "entries_count": len(entries),
    }


def _parse_header(soup: BeautifulSoup) -> Dict[str, str]:
    info = {}
    fname = soup.find("div", id="f_name")
    if fname:
        info["name"] = fname.get_text(strip=True)
    p2 = soup.find("p", id="p2")
    if p2:
        contents = p2.decode_contents()
        parts = re.split(r"<br\s*/?>", contents, flags=re.IGNORECASE)
        for part in parts:
            part_clean = BeautifulSoup(part, "lxml").get_text(strip=True)
            if ":" in part_clean:
                k, v = part_clean.split(":", 1)
                info[k.strip().lower().replace(" ", "_").replace(".", "")] = v.strip()
    return info


def _parse_holdings_table(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    results = []
    table = soup.find("table", id="grid")
    if not table:
        return results
    tbody = table.find("tbody")
    if not tbody:
        return results
    rows = tbody.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        hist_cell = cells[0]
        stock_cell = cells[1]
        pct_cell = cells[2]
        act_cell = cells[3]
        shares_cell = cells[4]
        price_cell = cells[5]
        value_cell = cells[6]

        a_tag = stock_cell.find("a")
        symbol = _extract_symbol_from_a(a_tag)
        name = ""
        if a_tag:
            span_tag = a_tag.find("span")
            if span_tag:
                name = span_tag.get_text(strip=True).lstrip("- ")

        shares = shares_cell.get_text(strip=True)
        reported_price = price_cell.get_text(strip=True)
        value = value_cell.get_text(strip=True)
        pct = pct_cell.get_text(strip=True)
        act_text = act_cell.get_text(strip=True).strip()

        entry = {
            "symbol": symbol,
            "name": name,
            "portfolio_pct": pct,
            "activity": act_text or None,
            "shares": shares,
            "reported_price": reported_price,
            "value": value,
        }

        if len(cells) > 7:
            gap = cells[7]
        if len(cells) > 8:
            entry["current_price"] = cells[8].get_text(strip=True)
        if len(cells) > 9:
            entry["price_change_pct"] = cells[9].get_text(strip=True)

        results.append(entry)
    return results


def _parse_activity_table(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    results = []
    table = soup.find("table", id="grid")
    if not table:
        return results
    tbody = table.find("tbody")
    if not tbody:
        return results

    # Dataroma's HTML is malformed: data <td>s sit directly under <tbody>
    # without a wrapping <tr>. We group consecutive <td> siblings into rows.
    all_children = [c for c in tbody.children if c.name]

    current_row_cells = []
    current_is_data = False
    current_period = None

    for child in all_children:
        if child.name == "tr":
            cells = child.find_all("td")
            if len(cells) == 1 and cells[0].get("colspan"):
                current_period = cells[0].get_text(strip=True)
            continue

        if child.name != "td":
            continue

        cls = child.get("class", [])
        is_hist = "hist" in cls

        if is_hist and current_row_cells:
            _flush_activity_row(results, current_row_cells, current_period)
            current_row_cells = []
            current_is_data = True

        current_row_cells.append(child)

    if current_row_cells:
        _flush_activity_row(results, current_row_cells, current_period)

    return results


def _extract_symbol_from_a(a_tag) -> str:
    if not a_tag:
        return ""
    href = a_tag.get("href", "")
    m = re.search(r"[?&]sym=([A-Z][A-Z0-9.]*)", href)
    if m:
        return m.group(1)
    txt = a_tag.get_text(strip=True)
    return txt.split()[0].rstrip("-").strip() if txt else ""


def _flush_activity_row(results: List[Dict[str, Any]], cells, period: str):
    if len(cells) < 5:
        return
    hist_cell = cells[0]
    stock_cell = cells[1]
    activity_cell = cells[2]
    shares_cell = cells[3]
    pct_cell = cells[4] if len(cells) > 4 else None

    a_tag = stock_cell.find("a") if stock_cell else None
    symbol = _extract_symbol_from_a(a_tag)
    name = ""
    if a_tag:
        span_tag = a_tag.find("span")
        if span_tag:
            name = span_tag.get_text(strip=True).lstrip("- ")

    activity_text = activity_cell.get_text(strip=True) if activity_cell else ""
    cls_list = activity_cell.get("class", []) if activity_cell else []
    cls_str = " ".join(cls_list) if isinstance(cls_list, list) else str(cls_list)
    act_type = "buy" if "buy" in cls_str.lower() else "sell" if "red" in cls_str.lower() or "sell" in cls_str.lower() else "neutral"

    results.append({
        "symbol": symbol,
        "name": name,
        "activity": activity_text,
        "activity_type": act_type,
        "shares": shares_cell.get_text(strip=True) if shares_cell else "",
        "portfolio_pct_change": pct_cell.get_text(strip=True) if pct_cell else "",
        "period": period,
    })


def _parse_pagination(soup: BeautifulSoup) -> Dict[str, Any]:
    pagination = {"current_page": 1, "total_pages": 1, "pages": []}
    links = soup.find_all("a", href=re.compile(r"L=\d+"))
    if links:
        pages = set()
        for a in links:
            m = re.search(r"L=(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        if pages:
            pagination["total_pages"] = max(pages)
            pagination["pages"] = sorted(pages)
            # Find current page
            for a in links:
                if a.find_parent() and "sel" in a.get("class", []):
                    m = re.search(r"L=(\d+)", a.get("href", ""))
                    if m:
                        pagination["current_page"] = int(m.group(1))
                        break
    return pagination


def _parse_history_table(soup: BeautifulSoup) -> Tuple[List[Dict], List[str]]:
    periods = []
    stock_names = []

    table = soup.find("table")
    if not table:
        return periods, stock_names

    # Parse header row: skip Period and Portfolio Value columns, remainder are stock names
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            hcells = header_row.find_all("td")
            for cell in hcells[2:]:
                txt = cell.get_text(strip=True)
                if txt:
                    stock_names.append(txt)

    # Parse data rows from tbody
    tbody = table.find("tbody")
    if not tbody:
        return periods, stock_names

    rows = tbody.find_all("tr", recursive=False)
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        period_text = cells[0].get_text(strip=True)
        if period_text.lower() == "period":
            continue

        val_text = cells[1].get_text(strip=True)

        holdings = []
        for cell in cells[2:]:
            txt = cell.get_text(strip=True)
            if txt:
                sym_match = re.match(r"([A-Z][A-Z0-9.]*?)(?:[A-Z][a-z]|$|\d)", txt)
                raw = sym_match.group(1) if sym_match else txt
                holdings.append(raw)
            else:
                holdings.append(None)

        periods.append({
            "period": period_text,
            "portfolio_value": val_text,
            "holdings": holdings,
        })

    return periods, stock_names


def _parse_stock_history(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    entries = []
    table = soup.find("table")
    if not table:
        return entries
    tbody = table.find("tbody")
    if not tbody:
        return entries
    rows = tbody.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        entries.append({
            "period": cells[0].get_text(strip=True),
            "shares": cells[1].get_text(strip=True) if len(cells) > 1 else "",
            "value": cells[2].get_text(strip=True) if len(cells) > 2 else "",
            "price": cells[3].get_text(strip=True) if len(cells) > 3 else "",
        })
    return entries


def list_all_activities(manager_code: str) -> List[Dict[str, Any]]:
    """Fetch all pages of activity data for a manager."""
    all_activities = []
    page = 1
    while True:
        result = fetch_activity(manager_code, "a", page)
        if "error" in result or not result.get("activities"):
            break
        all_activities.extend(result["activities"])
        total = result.get("pagination", {}).get("total_pages", page)
        if page >= total:
            break
        page += 1
    return all_activities


# ─── Grand Portfolio ──────────────────────────────────────────────────────────

GRAND_PORTFOLIO_VIEWS = {
    "grand_portfolio": "h",            # holdings
    "grand_portfolio_qtr_buys": "qb",
    "grand_portfolio_qtr_sells": "qs",
    "grand_portfolio_6mo_buys": "hb",
    "grand_portfolio_6mo_sells": "hs",
    "grand_portfolio_sector": "ss",
}

def _gp_table_to_dict(table) -> List[Dict[str, Any]]:
    """Parse grand portfolio table rows into structured data."""
    results = []
    rows = table.find_all("tr") if table else []
    for row in rows[1:]:  # skip header
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        symbol_a = cells[0].find("a")
        symbol = symbol_a.get_text(strip=True) if symbol_a else cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        pct = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        own_count = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        reported_price = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        max_pct = cells[5].get_text(strip=True) if len(cells) > 5 else ""

        entry = {
            "symbol": symbol,
            "name": name,
            "portfolio_pct": pct,
            "ownership_count": own_count,
            "reported_price": reported_price,
            "max_pct": max_pct,
        }

        if len(cells) > 6:
            entry["current_price"] = cells[6].get_text(strip=True)
        if len(cells) > 7:
            entry["week_52_low"] = cells[7].get_text(strip=True)
        if len(cells) > 8:
            entry["above_52w_low_pct"] = cells[8].get_text(strip=True)
        if len(cells) > 9:
            entry["week_52_high"] = cells[9].get_text(strip=True)

        results.append(entry)
    return results


def fetch_grand_portfolio(view: str = "grand_portfolio") -> Dict[str, Any]:
    t_param = GRAND_PORTFOLIO_VIEWS.get(view, "h")
    url = f"{BASE_URL}/g/portfolio.php?t={t_param}"
    html = _fetch_page(url, REFERERS.get(view, REFERERS["grand_portfolio"]))
    if not html:
        return {"error": f"Failed to fetch grand portfolio (view={view})"}
    soup = _soup(html)

    header_info = _parse_header(soup)

    holdings = []
    sector_data = []

    if view == "grand_portfolio_sector":
        # Sector stats: look for sector breakdown
        sector_table = soup.find("table", id="sector")
        if sector_table:
            rows = sector_table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    sector_data.append({
                        "sector": cells[0].get_text(strip=True),
                        "value": cells[1].get_text(strip=True),
                    })
    else:
        table = soup.find("table", id="grid")
        if table:
            holdings = _gp_table_to_dict(table)

    # Extract summary info from header
    summary = {}
    p2 = soup.find("p", id="p2")
    if p2:
        spans = p2.find_all("span")
        labels = ["total_stocks", "portfolio_value"]
        for i, span in enumerate(spans):
            key = labels[i] if i < len(labels) else f"field_{i}"
            summary[key] = span.get_text(strip=True)

    return {
        "page_type": view,
        "page_url": url,
        "header": header_info,
        "summary": summary,
        "holdings": holdings,
        "holdings_count": len(holdings),
        "sector_data": sector_data,
    }


# ─── All Managers ─────────────────────────────────────────────────────────────

def fetch_all_managers() -> Dict[str, Any]:
    """Fetch list of all ~82 superinvestors tracked by Dataroma."""
    url = f"{BASE_URL}/managers.php"
    html = _fetch_page(url, REFERERS["all_managers"])
    if not html:
        return {"error": "Failed to fetch managers page"}
    soup = _soup(html)

    managers = []
    table = soup.find("table")
    if not table:
        return {"managers": managers, "manager_count": 0}

    tbody = table.find("tbody")
    if not tbody:
        return {"managers": managers, "manager_count": 0}

    # Each row: name/firm link, portfolio value, stock count, top 10 holdings
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        name_cell = cells[0]
        a_tag = name_cell.find("a")
        name = ""
        firm = ""
        code = None
        if a_tag:
            name = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            m = re.search(r"[?&]m=([A-Za-z0-9._]+)", href)
            if m:
                code = m.group(1)
            # firm name may be in a separate element
            firm_span = name_cell.find("span", class_="firm")
            if firm_span:
                firm = firm_span.get_text(strip=True)

        portfolio_val = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        stock_count = cells[2].get_text(strip=True) if len(cells) > 2 else ""

        # Top 10 holdings
        top_holdings = []
        for cell in cells[3:]:
            txt = cell.get_text(strip=True)
            if txt:
                a = cell.find("a")
                sym = _extract_symbol_from_a(a) if a else txt.split()[0]
                top_holdings.append(sym)

        if code:
            managers.append({
                "code": code,
                "name": name,
                "firm": firm,
                "portfolio_value": portfolio_val,
                "stock_count": stock_count,
                "top_holdings": top_holdings[:10],
            })

    return {
        "page_type": "all_managers",
        "page_url": url,
        "managers": managers,
        "manager_count": len(managers),
    }


# ─── All Activity (aggregate across all managers) ────────────────────────────

ALL_ACTIVITY_TYPES = {"a": "a", "b": "b", "s": "s"}

def _parse_all_activity_cell(cell) -> Optional[Dict[str, Any]]:
    """Parse a single activity cell in the all-activity table.
    
    Structure:
    <td class="sym">
      <span class="tit_ctl">
        <a class="sell" href="/m/activity.php?sym=FLUT&typ=a">FLUT</a>
        <div>Company Name<br/>Reduce -84.34%<br/>Change to portfolio: 5.22%</div>
      </span>
    </td>
    """
    a_tag = cell.find("a")
    if not a_tag:
        return None
    symbol = _extract_symbol_from_a(a_tag)
    cls_list = a_tag.get("class", [])
    cls_str = " ".join(cls_list) if isinstance(cls_list, list) else str(cls_list)
    act_type = "buy" if "buy" in cls_str.lower() else "sell" if "sell" in cls_str.lower() or "red" in cls_str.lower() else "neutral"

    div = cell.find("div")
    name = ""
    action = ""
    portfolio_change = ""
    if div:
        contents = div.decode_contents()
        parts = re.split(r"<br\s*/?>", contents, flags=re.IGNORECASE)
        if parts:
            name = BeautifulSoup(parts[0], "lxml").get_text(strip=True) if parts[0] else ""
        if len(parts) > 1:
            action = BeautifulSoup(parts[1], "lxml").get_text(strip=True) if parts[1] else ""
        if len(parts) > 2:
            portfolio_change = BeautifulSoup(parts[2], "lxml").get_text(strip=True).replace("Change to portfolio:", "").strip() if parts[2] else ""

    return {
        "symbol": symbol,
        "name": name,
        "activity": action,
        "activity_type": act_type,
        "portfolio_pct_change": portfolio_change,
    }


def fetch_all_activity(typ: str = "a", page: str = "") -> Dict[str, Any]:
    """Fetch aggregate activity across all superinvestors."""
    t = ALL_ACTIVITY_TYPES.get(typ, "a")
    url = f"{BASE_URL}/allact.php?typ={t}"
    if page:
        url += f"&p={page.upper()}"
    html = _fetch_page(url, REFERERS["all_activity"])
    if not html:
        return {"error": f"Failed to fetch all activity page (typ={typ})"}
    soup = _soup(html)

    manager_activities = []
    table = soup.find("table")
    if table:
        tbody = table.find("tbody")
        if tbody:
            current_manager = None
            current_period = None
            current_activities = []

            for row in tbody.find_all("tr"):
                cells = row.find_all("td")
                if not cells:
                    continue

                # Manager row: first cell has a link to manager page
                first_cell = cells[0]
                first_a = first_cell.find("a")

                if first_a and len(cells) >= 3 and first_cell.get("class") != ["hist"]:
                    # Flush previous manager
                    if current_manager and current_activities:
                        manager_activities.append({
                            "manager": current_manager,
                            "period": current_period,
                            "activities": current_activities,
                        })
                    current_activities = []
                    current_manager = first_a.get_text(strip=True)
                    current_period = cells[1].get_text(strip=True) if len(cells) > 1 else ""

                    # Parse the remaining cells as activity items
                    for cell in cells[2:]:
                        parsed = _parse_all_activity_cell(cell)
                        if parsed:
                            current_activities.append(parsed)
                    continue

                # Period-only or standalone rows
                if len(cells) == 1 and cells[0].get("colspan"):
                    if current_manager and current_activities:
                        manager_activities.append({
                            "manager": current_manager,
                            "period": current_period,
                            "activities": current_activities,
                        })
                    current_activities = []
                    current_period = cells[0].get_text(strip=True)
                    current_manager = None
                    continue

                # Activity cells without manager name (continuation rows)
                if first_cell.get("class") == ["hist"] or (not first_a and len(cells) >= 5):
                    a_tag = cells[1].find("a") if len(cells) > 1 else None
                    if a_tag:
                        act_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        cls_str = " ".join(cells[2].get("class", [])) if len(cells) > 2 else ""
                        act_type = "buy" if "buy" in cls_str.lower() else "sell" if "red" in cls_str.lower() or "sell" in cls_str.lower() else "neutral"
                        current_activities.append({
                            "symbol": _extract_symbol_from_a(a_tag),
                            "name": (a_tag.find("span").get_text(strip=True).lstrip("- ") if a_tag.find("span") else ""),
                            "activity": act_text,
                            "activity_type": act_type,
                            "shares": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                            "portfolio_pct_change": cells[4].get_text(strip=True) if len(cells) > 4 else "",
                        })
                    continue

            # Flush last manager
            if current_manager and current_activities:
                manager_activities.append({
                    "manager": current_manager,
                    "period": current_period,
                    "activities": current_activities,
                })

    # Parse alphabet pagination
    alpha_pages = []
    alpha_div = soup.find("div", id="alpha")
    if alpha_div:
        for a in alpha_div.find_all("a"):
            href = a.get("href", "")
            m = re.search(r"p=([A-Z])", href)
            if m:
                alpha_pages.append(m.group(1))

    return {
        "page_type": f"all_activity_{typ}",
        "page_url": url,
        "managers": manager_activities,
        "manager_count": len(manager_activities),
        "alpha_pages": alpha_pages,
    }
