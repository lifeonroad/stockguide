"""
Live 13F Data Fetcher
Fetches superinvestor 13F filings from free SEC EDGAR API.
Falls back to static data if SEC API is unavailable.

Caching strategy — filing-aware:
- Outside filing window: 30-day cache (data is completely static)
- Inside filing window (45 days after quarter end): 6-hour cache
- Day of deadline: 1-hour cache (checking aggressively)
- Post-deadline stragglers (15 days): 1-hour cache

See filing_calendar.py for the schedule logic.
"""

import os
import time
import logging
from datetime import datetime, date
from superinvestors import get_superinvestors as get_static_superinvestors
from filing_calendar import get_filing_status, filing_aware_ttl

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Manual cache (filing-aware TTL)
# ──────────────────────────────────────────────────────────
_13F_CACHE = {
    "result": None,
    "expiry": 0.0,
    "last_good": None,
    "cached_quarter": None,
}


def _cache_valid():
    if _13F_CACHE["result"] is None:
        return False
    if time.time() > _13F_CACHE["expiry"]:
        return False
    return True


def _set_cache(result, ttl_seconds):
    filing_status = get_filing_status()
    _13F_CACHE["result"] = result
    _13F_CACHE["expiry"] = time.time() + ttl_seconds
    _13F_CACHE["last_good"] = result
    _13F_CACHE["cached_quarter"] = filing_status["data_through_quarter"]


def _get_cached_or_fetch():
    if _cache_valid():
        return _13F_CACHE["result"]

    ttl = filing_aware_ttl()
    data = _fetch_all_investors()

    if data:
        _set_cache(data, ttl)
    elif _13F_CACHE["last_good"] is not None:
        return _13F_CACHE["last_good"]

    return data


def get_next_filing_info():
    """
    Returns information about the next 13F filing deadline.
    Delegates to filing_calendar for accurate schedule logic.
    """
    status = get_filing_status()
    days_remaining = status["days_until_deadline"]

    if days_remaining is not None:
        if days_remaining < 0:
            filing_status_text = "Filing window recently closed"
        elif days_remaining == 0:
            filing_status_text = "Filings are due TODAY!"
        elif days_remaining <= 7:
            filing_status_text = f"Filings due in {days_remaining} days (Active Window)"
        else:
            filing_status_text = f"Next major update: {status['next_deadline']}"
    else:
        days_remaining_val = status.get("days_until_window")
        if days_remaining_val is not None:
            filing_status_text = f"Next filing window opens in {days_remaining_val} days"
        else:
            filing_status_text = status["badge"]

    return {
        "status": filing_status_text,
        "quarter": status["next_filing_quarter"] or "Unknown",
        "deadline": status["next_deadline"],
        "days_remaining": days_remaining,
    }


def _fetch_all_investors():
    """
    Fetch 13F data for all tracked investors via SEC EDGAR.
    Falls back per-investor to static data if SEC EDGAR fails.
    """
    try:
        from sec_13f import get_investor_with_changes, INVESTOR_CIKS
    except ImportError:
        logger.warning("sec_13f module not available, using static data")
        return get_static_superinvestors()

    from sec_13f_db import ALL_INVESTOR_CIKS

    static_fallback = _build_static_fallback_map()
    live_data = []

    for investor_id in ALL_INVESTOR_CIKS:
        meta = ALL_INVESTOR_CIKS[investor_id]
        try:
            result = get_investor_with_changes(investor_id)
            if result:
                formatted = _format_investor_from_sec(result, meta)
                if formatted:
                    live_data.append(formatted)
                    continue
        except Exception as e:
            logger.warning("SEC EDGAR fetch failed for %s: %s", investor_id, e)

        fallback = static_fallback.get(investor_id)
        if fallback:
            live_data.append(fallback)
        else:
            live_data.append({
                "id": investor_id,
                "name": meta.get("name", investor_id.title()),
                "firm": meta.get("firm", ""),
                "style": meta.get("style", "Value"),
                "dataroma_code": meta.get("dataroma_code"),
                "history": [],
            })

        time.sleep(0.5)

    return live_data if live_data else get_static_superinvestors()


def _build_static_fallback_map():
    """Build dict of investor_id -> static data for all tracked investors."""
    from sec_13f_db import ALL_INVESTOR_CIKS
    fallback = {}
    static_list = get_static_superinvestors()
    for inv in static_list:
        meta = ALL_INVESTOR_CIKS.get(inv["id"], {})
        inv["dataroma_code"] = meta.get("dataroma_code")
        fallback[inv["id"]] = inv
    return fallback


def _format_investor_from_sec(result: dict, meta: dict) -> dict:
    """
    Convert sec_13f data format to frontend-friendly format
    with history, top_buys, top_sells, weirdest_bet.
    """
    investor_id = result.get("investor_id", "")
    quarter = result.get("quarter", "")
    holdings = result.get("holdings", [])
    changes = result.get("changes", {})

    if not quarter and not holdings:
        return None

    top_buys = _build_top_buys(changes)
    top_sells = _build_top_sells(changes)
    weirdest_bet = _build_weirdest_bet(changes)
    summary = _build_summary(changes, holdings)

    base_history = [{
        "quarter": quarter,
        "summary": summary,
        "top_buys": top_buys,
        "top_sells": top_sells,
        "weirdest_bet": weirdest_bet,
    }]

    prev_histories = _build_previous_histories(investor_id, quarter)
    base_history.extend(prev_histories)

    return {
        "id": investor_id,
        "name": meta.get("name", investor_id.title()),
        "firm": meta.get("firm", ""),
        "style": meta.get("style", "Value"),
        "dataroma_code": meta.get("dataroma_code"),
        "history": base_history,
    }


def _build_top_buys(changes: dict) -> list:
    """Combine new + increased positions into top_buys format."""
    buys = []

    for item in changes.get("new", []):
        buys.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "change": "NEW",
            "value_millions": item.get("curr_value_millions", 0),
        })

    for item in changes.get("increased", []):
        buys.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "change": "ADDED",
            "value_millions": item.get("curr_value_millions", 0),
        })

    buys.sort(key=lambda x: x.get("value_millions", 0), reverse=True)
    return buys[:5]


def _build_top_sells(changes: dict) -> list:
    """Combine decreased + exited positions into top_sells format."""
    sells = []

    for item in changes.get("decreased", []):
        sells.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "change": "REDUCED",
            "value_change": abs(item.get("value_change_millions", 0)),
        })

    for item in changes.get("exited", []):
        sells.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "change": "EXIT",
            "value_change": abs(item.get("prev_value_millions", 0)),
        })

    sells.sort(key=lambda x: x.get("value_change", 0), reverse=True)
    return sells[:5]


def _build_weirdest_bet(changes: dict) -> dict:
    """Pick the most interesting/weird bet from changes."""
    new_items = changes.get("new", [])
    if not new_items:
        increased = changes.get("increased", [])
        if not increased:
            return None
        pick = increased[0]
        return {
            "symbol": pick.get("symbol", ""),
            "type": "AGGRESSIVE ADD",
            "description": f"Increased position by {pick.get('shares_change_pct', 0):.0f}% to ${pick.get('curr_value_millions', 0):.0f}M — high conviction bet.",
        }

    pick = new_items[0]
    pct = pick.get("value_change_pct", 0)
    value = pick.get("curr_value_millions", 0)
    return {
        "symbol": pick.get("symbol", ""),
        "type": "NEW POSITION",
        "description": f"New ${value:.0f}M stake ({pick.get('name', '')}) — a fresh bet at {pct:.0f}% of quarter-end portfolio value.",
    }


def _build_summary(changes: dict, holdings: list) -> str:
    """Generate a human-readable summary from changes data."""
    new_count = len(changes.get("new", []))
    inc_count = len(changes.get("increased", []))
    dec_count = len(changes.get("decreased", []))
    exit_count = len(changes.get("exited", []))
    held_count = len(changes.get("held", []))

    total_value = sum(h.get("value_millions", 0) for h in holdings) if holdings else 0
    holdings_count = len(holdings) if holdings else 0

    parts = []
    if new_count > 0:
        parts.append(f"Added {new_count} new positions")
    if inc_count > 0:
        parts.append(f"increased {inc_count} existing")
    if dec_count > 0:
        parts.append(f"trimmed {dec_count} positions")
    if exit_count > 0:
        parts.append(f"fully exited {exit_count} holdings")
    parts.append(f"${total_value:.0f}M in {holdings_count} holdings")

    return ". ".join(parts) + "."


def _build_previous_histories(investor_id: str, current_quarter: str) -> list:
    """Try to include previous quarter data from DB cache."""
    try:
        from sec_13f_db import get_all_quarters, get_filing
    except ImportError:
        return []

    try:
        all_quarters = get_all_quarters(investor_id)
        all_quarters = [q for q in all_quarters if q != current_quarter]
        all_quarters.sort(reverse=True)
        all_quarters = all_quarters[:2]
    except Exception:
        return []

    histories = []
    for q in all_quarters:
        try:
            filing = get_filing(investor_id, q)
            if not filing:
                continue
            holdings = filing.get("holdings", [])
            holdings_count = len(holdings)
            total_value = sum(h.get("value_millions", 0) or 0 for h in holdings)

            top_positions = sorted(
                holdings, key=lambda x: x.get("value_millions", 0) or 0, reverse=True
            )[:3]

            histories.append({
                "quarter": q,
                "summary": f"{holdings_count} holdings tracked, ${total_value:.0f}M total value.",
                "top_buys": [
                    {
                        "symbol": h.get("ticker", h.get("name_of_issuer", "")[:8]),
                        "name": h.get("name_of_issuer", ""),
                        "change": f"{h.get('pct_of_portfolio', 0):.1f}%",
                    }
                    for h in top_positions
                ],
                "top_sells": [],
                "weirdest_bet": None,
            })
        except Exception:
            continue

    return histories


def get_live_superinvestors():
    """
    Fetch live 13F data for all tracked investors via SEC EDGAR.
    Uses filing-aware caching: 30-day cache outside filing window,
    6-hour cache inside filing window.
    Falls back to static data if SEC EDGAR is unavailable.
    """
    data = _get_cached_or_fetch()
    return data if data else get_static_superinvestors()


def get_investor_detail(investor_id: str) -> dict:
    """
    Return detailed breakdown for a single superinvestor.
    Includes full holdings, computed changes, portfolio stats, and cached prices.
    Falls back to static data if SEC EDGAR is unavailable.
    """
    try:
        from sec_13f import get_investor_with_changes
    except ImportError:
        return {"_error": f"Cannot load SEC EDGAR module"}

    try:
        result = get_investor_with_changes(investor_id)
    except Exception as e:
        logger.warning("get_investor_detail(%s) SEC EDGAR failed: %s", investor_id, e)
        result = None

    from sec_13f_db import ALL_INVESTOR_CIKS
    meta = ALL_INVESTOR_CIKS.get(investor_id, {})
    name = meta.get("name", investor_id.title())
    firm = meta.get("firm", "")
    style = meta.get("style", "Value")

    if not result:
        static = get_static_superinvestors()
        for inv in static:
            if inv["id"] == investor_id:
                return {
                    "investor_id": investor_id,
                    "name": inv["name"],
                    "firm": inv.get("firm", ""),
                    "style": inv.get("style", ""),
                    "dataroma_code": meta.get("dataroma_code"),
                    "quarter": (inv.get("history") or [{}])[0].get("quarter", "Unknown"),
                    "holdings": [],
                    "changes": {},
                    "stats": {"total_value_millions": 0, "holdings_count": 0, "top_concentration": 0},
                    "source": "static_fallback",
                }
        return {"_error": f"Investor {investor_id} not found", "_message": "No data available"}

    holdings = result.get("holdings", [])
    changes = result.get("changes", {})
    quarter = result.get("quarter", "Unknown")

    holdings_count = len(holdings)
    total_value = sum(h.get("value_millions", 0) or 0 for h in holdings)

    holdings_sorted = sorted(holdings, key=lambda h: h.get("value_millions", 0) or 0, reverse=True)
    top3_value = sum(h.get("value_millions", 0) or 0 for h in holdings_sorted[:3])
    top_concentration = round((top3_value / total_value * 100), 1) if total_value > 0 else 0

    sector_map = {}
    for h in holdings_sorted:
        try:
            from persistent_cache import get_ticker_info_cached
            cached = get_ticker_info_cached(h.get("ticker", ""))
            sector = (cached or {}).get("sector", "Unknown")
        except Exception:
            sector = "Unknown"
        sector_map.setdefault(sector, 0)
        sector_map[sector] += h.get("value_millions", 0) or 0

    sector_breakdown = {}
    total_allocated = sum(sector_map.values())
    if total_allocated > 0:
        for sector, val in sorted(sector_map.items(), key=lambda x: -x[1]):
            sector_breakdown[sector] = round(val / total_allocated * 100, 1)

    change_counts = {}
    total_changes = 0
    for ct, items in changes.items():
        change_counts[ct] = len(items)
        total_changes += len(items)

    return {
        "investor_id": investor_id,
        "name": name,
        "firm": firm,
        "style": style,
        "dataroma_code": meta.get("dataroma_code"),
        "quarter": quarter,
        "holdings": holdings_sorted,
        "changes": changes,
        "stats": {
            "total_value_millions": round(total_value, 1),
            "holdings_count": holdings_count,
            "top_concentration": top_concentration,
            "sector_breakdown": sector_breakdown,
            "change_counts": change_counts,
            "total_changes": total_changes,
        },
        "source": "sec_edgar",
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    print("Testing SEC EDGAR 13F Fetcher (via superinvestors_live)...")
    status = get_filing_status()
    print(f"Filing status: {status['badge']}")
    print(f"Cache TTL: {status['cache_ttl_seconds']}s ({status['cache_ttl_seconds'] / 3600:.1f}h)")
    print(f"Filing window open: {status['filing_window_open']}")
    print()
    data = get_live_superinvestors()
    print(f"Fetched data for {len(data)} investors")
    for inv in data:
        print(f"  {inv['name']} ({inv.get('firm', '')}) — {len(inv.get('history', []))} quarters")
