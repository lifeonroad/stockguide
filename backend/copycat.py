from data_client import get_ticker_info
from cache_utils import timed_cache
import logging
import time

logger = logging.getLogger(__name__)

FILTER_OPTIONS = {
    "all":      "All Signals",
    "overlap":  "Multi-Manager",
    "new_buys": "New Buys",
    "increased":"Conviction Up",
    "exits":    "Exits",
}

INVESTOR_COLORS = {
    "buffett":      "bg-blue-500/20 text-blue-300",
    "burry":        "bg-red-500/20 text-red-300",
    "druckenmiller":"bg-yellow-500/20 text-yellow-300",
    "pabrai":       "bg-purple-500/20 text-purple-300",
    "gates":        "bg-green-500/20 text-green-300",
    "einhorn":      "bg-orange-500/20 text-orange-300",
}

STATIC_FALLBACK = [
    {"symbol": "RIG", "name": "Transocean", "held_by": ["Pabrai"]},
    {"symbol": "AMR", "name": "Alpha Metallurgical", "held_by": ["Pabrai"]},
    {"symbol": "GOOGL","name": "Alphabet", "held_by": ["Warren Buffett", "Stanley Druckenmiller"]},
    {"symbol": "AMZN", "name": "Amazon", "held_by": ["Stanley Druckenmiller"]},
    {"symbol": "LEN",  "name": "Lennar Corp", "held_by": ["Warren Buffett"]},
    {"symbol": "MOH",  "name": "Molina Healthcare", "held_by": ["Michael Burry"]},
    {"symbol": "NTRA", "name": "Natera", "held_by": ["Stanley Druckenmiller"]},
    {"symbol": "STZ",  "name": "Constellation Brands", "held_by": ["Warren Buffett"]},
    {"symbol": "MSFT", "name": "Microsoft", "held_by": ["Bill & Melinda Gates Foundation"]},
    {"symbol": "WM",   "name": "Waste Management", "held_by": ["Bill & Melinda Gates Foundation"]},
    {"symbol": "BRK.B","name": "Berkshire Hathaway B", "held_by": ["David Einhorn"]},
    {"symbol": "CPNG", "name": "Coupang", "held_by": ["David Einhorn"]},
]


def _query_sec_edgar(filter_type: str = "all"):
    """Query sec_13f_db tables to build dynamic copycat data."""
    try:
        from sec_13f_db import _get_conn, ALL_INVESTOR_CIKS, init_13f_db, compute_changes
    except ImportError:
        logger.warning("sec_13f_db not available, using static fallback")
        return None

    init_13f_db()
    conn = _get_conn()
    try:
        investors = dict(ALL_INVESTOR_CIKS)

        latest_quarters = {}
        for inv_id in investors:
            row = conn.execute(
                "SELECT quarter FROM sec_13f_filings WHERE investor_id = ? ORDER BY fetched_at DESC LIMIT 1",
                (inv_id,)
            ).fetchone()
            if row:
                latest_quarters[inv_id] = row["quarter"]

        if not latest_quarters:
            return None

        ticker_map = {}
        for inv_id, quarter in latest_quarters.items():
            rows = conn.execute("""
                SELECT h.ticker, h.name_of_issuer, h.value_millions, h.pct_of_portfolio, h.shares
                FROM sec_13f_holdings h
                JOIN sec_13f_filings f ON h.filing_id = f.id
                WHERE h.investor_id = ? AND h.quarter = ?
                  AND h.ticker IS NOT NULL AND h.ticker != ''
            """, (inv_id, quarter)).fetchall()

            meta = investors[inv_id]
            for r in rows:
                sym = r["ticker"].upper().strip()
                if sym not in ticker_map:
                    ticker_map[sym] = {
                        "symbol": sym,
                        "name": r["name_of_issuer"] or sym,
                        "held_by": [],
                        "investor_detail": [],
                        "total_value_millions": 0,
                        "filter_tags": set(),
                    }
                ticker_map[sym]["held_by"].append(meta["name"])
                ticker_map[sym]["investor_detail"].append({
                    "investor_id": inv_id,
                    "name": meta["name"],
                    "value_millions": round(r["value_millions"] or 0, 1),
                    "pct": round(r["pct_of_portfolio"] or 0, 1),
                })
                ticker_map[sym]["total_value_millions"] += r["value_millions"] or 0

        for inv_id, quarter in latest_quarters.items():
            try:
                changes = compute_changes(inv_id, quarter)
            except Exception:
                changes = {}
            meta = investors[inv_id]

            for change_type in ("new", "increased", "decreased", "exited"):
                for item in changes.get(change_type, []):
                    sym = (item.get("symbol") or "").upper().strip()
                    if not sym or sym not in ticker_map:
                        continue
                    tag = {"new": "new_buys", "increased": "increased",
                           "decreased": "decreased", "exited": "exits"}.get(change_type)
                    if tag:
                        ticker_map[sym]["filter_tags"].add(tag)
                    for d in ticker_map[sym]["investor_detail"]:
                        if d["investor_id"] == inv_id:
                            d["action"] = change_type.upper()

        result = list(ticker_map.values())
        for r in result:
            if len(r["held_by"]) >= 2:
                r["filter_tags"].add("overlap")
            if not r["filter_tags"]:
                r["filter_tags"].add("held")

        if filter_type != "all":
            result = [r for r in result if filter_type in r["filter_tags"]]

        result.sort(key=lambda x: x["total_value_millions"], reverse=True)
        return result

    finally:
        conn.close()


def _enrich_with_prices(items: list) -> list:
    """Attach cached prices to copycat items. Read-only from SQLite — never
    triggers a Yahoo fetch, so this is instant even when Yahoo is rate-limited."""
    try:
        from persistent_cache import get_ticker_info_cached
    except ImportError:
        get_ticker_info_cached = None

    for item in items:
        sym = item["symbol"]
        item["price"] = 0
        item["daily_change"] = 0
        item["yearly_change"] = 0
        item["market_cap"] = 0

        if not get_ticker_info_cached:
            continue

        try:
            cached = get_ticker_info_cached(sym)
            if cached and cached.get("price", 0) > 0:
                item["price"] = cached["price"]
                item["market_cap"] = cached.get("market_cap", 0) or 0
        except Exception:
            pass

    return items


def _build_static(filter_type: str = "all"):
    """Fallback: add prices to hardcoded list."""
    items = [dict(h) for h in STATIC_FALLBACK]
    tags_map = {
        sym: set()
        for sym in {h["symbol"] for h in STATIC_FALLBACK}
    }
    for h in STATIC_FALLBACK:
        tags_map[h["symbol"]].add("held")

    overlap_symbols = set()
    for h in STATIC_FALLBACK:
        for h2 in STATIC_FALLBACK:
            if h["symbol"] == h2["symbol"] and len(h["held_by"]) >= 2:
                overlap_symbols.add(h["symbol"])
    for sym in overlap_symbols:
        tags_map[sym].add("overlap")

    for item in items:
        item["filter_tags"] = list(tags_map.get(item["symbol"], ["held"]))
        item["total_value_millions"] = 0
        item["investor_detail"] = [
            {"name": name, "action": "HELD", "value_millions": 0, "pct": 0}
            for name in item["held_by"]
        ]

    if filter_type != "all":
        items = [r for r in items if filter_type in r["filter_tags"]]

    return _enrich_with_prices(items)


def _build_error(message: str, error_type: str = "Data Fetch Error"):
    """Return a structured error dict for the frontend."""
    return {"_error": error_type, "_message": message, "data": []}


@timed_cache(ttl_seconds=600, soft_ttl_seconds=400)
def get_copycat_performance(filter_type: str = "all"):
    """
    Generate the copycat portfolio from SEC EDGAR 13F filings.
    Falls back to static curated list if EDGAR data is unavailable.

    filter_type: all | overlap | new_buys | increased | exits
    """
    if filter_type not in FILTER_OPTIONS:
        filter_type = "all"

    try:
        sec_data = _query_sec_edgar(filter_type)
        if sec_data is not None:
            items = _enrich_with_prices(sec_data)
            items.sort(key=lambda x: x.get("total_value_millions", 0), reverse=True)
            return {
                "data": items,
                "filter": filter_type,
                "source": "sec_edgar",
                "count": len(items),
            }
    except Exception as e:
        logger.warning("SEC EDGAR copycat query failed: %s", e)

    try:
        items = _build_static(filter_type)
        return {
            "data": items,
            "filter": filter_type,
            "source": "static_fallback",
            "count": len(items),
        }
    except Exception as e:
        logger.error("Static copycat fallback also failed: %s", e)
        return _build_error(str(e))
