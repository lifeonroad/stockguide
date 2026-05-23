"""
filing_calendar.py — 13F SEC Filing Schedule Intelligence
==========================================================
Knows when 13F filings are due, whether we're inside a filing window,
and dynamically calculates cache TTLs based on filing proximity.

13F filing rules:
- Due 45 days after each calendar quarter end
- Q1 (Mar 31)  → May 15
- Q2 (Jun 30)  → Aug 14
- Q3 (Sep 30)  → Nov 14
- Q4 (Dec 31)  → Feb 14

Filing window opens on the quarter end date and closes ~15 days after the
deadline (most funds file by the deadline, stragglers file within ~2 weeks).

Usage
-----
    from filing_calendar import get_filing_status, filing_aware_ttl

    status = get_filing_status()
    # → {
    #       "data_through_quarter": "Q3 2025",
    #       "next_filing_quarter": "Q4 2025",
    #       "filing_window_open": False,
    #       "days_until_window": 120,
    #       "next_deadline": "2026-02-14",
    #       "cache_ttl_seconds": 2592000,   # 30 days outside window
    #       "badge": "📌 Data through Q3 2025",
    #       "badge_color": "green"
    #   }

    ttl = filing_aware_ttl()  # → seconds for cache decorator
"""

from datetime import date, timedelta
import math


# ──────────────────────────────────────────────────────────
# Filing schedule constants
# ──────────────────────────────────────────────────────────

# (quarter_end_month, quarter_end_day, deadline_month, deadline_day, label)
FILING_SCHEDULE = [
    (3,  31,  5,  15, "Q1"),   # Q1: ends Mar 31, due May 15
    (6,  30,  8,  14, "Q2"),   # Q2: ends Jun 30, due Aug 14
    (9,  30,  11, 14, "Q3"),   # Q3: ends Sep 30, due Nov 14
    (12, 31,  2,  14, "Q4"),   # Q4: ends Dec 31, due Feb 14 (next year)
]

# How long after the deadline do we still consider the window "active"?
# Most funds file by the deadline, but stragglers can file up to ~15 days late.
STRAGGLER_GRACE_DAYS = 15

# Cache TTLs
TTL_OUTSIDE_WINDOW = 30 * 24 * 3600    # 30 days (data is static)
TTL_INSIDE_WINDOW  = 6 * 3600           # 6 hours (refresh frequently)
TTL_POST_DEADLINE  = 1 * 3600           # 1 hour (check often right after deadline)


# ──────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────

def _get_filing_events(today: date):
    """
    Returns ordered list of filing events for the current and next year.
    Each event: (date, quarter_label, event_type)
    event_type: 'window_open', 'deadline', 'window_close'
    """
    events = []
    for q_end_month, q_end_day, dl_month, dl_day, label in FILING_SCHEDULE:
        # Determine the year for this quarter
        # Q4 deadline falls in the year AFTER the quarter ends
        if label == "Q4":
            year_for_deadline = today.year + 1 if today.month > 2 else today.year
            year_for_q_end = today.year if today.month > 2 or (today.month == 2 and today.day <= 14) else today.year - 1
        else:
            year_for_deadline = today.year
            year_for_q_end = today.year

        window_open = date(year_for_q_end, q_end_month, q_end_day)
        deadline = date(year_for_deadline, dl_month, dl_day)
        window_close = deadline + timedelta(days=STRAGGLER_GRACE_DAYS)

        events.append((window_open, label, "window_open"))
        events.append((deadline, label, "deadline"))
        events.append((window_close, label, "window_close"))

    # Sort by date, then by event priority (window_open < deadline < window_close)
    event_order = {"window_open": 0, "deadline": 1, "window_close": 2}
    events.sort(key=lambda e: (e[0], event_order[e[2]]))
    return events


def get_filing_status(today: date = None) -> dict:
    """
    Returns the current 13F filing status with cache TTL recommendation.
    """
    if today is None:
        today = date.today()

    events = _get_filing_events(today)

    # Find where we are relative to filing events
    data_through_quarter = None
    next_filing_quarter = None
    filing_window_open = False
    window_phase = "outside"  # outside, inside_window, post_deadline
    next_deadline = None
    days_until_deadline = None
    days_since_window_open = None
    cache_ttl = TTL_OUTSIDE_WINDOW
    badge = ""
    badge_color = "green"  # green, yellow, red

    # Walk through events to find our position
    prev_window_label = None
    for i, (evt_date, label, evt_type) in enumerate(events):
        if evt_date > today:
            # We're before this event
            if evt_type == "window_open":
                next_filing_quarter = label
                days_until_window = (evt_date - today).days
                break
            elif evt_type == "deadline" and next_deadline is None:
                next_deadline = evt_date
                days_until_deadline = (evt_date - today).days
            continue
        else:
            # We're at or past this event
            if evt_type == "window_open":
                prev_window_label = label
                days_since_window_open = (today - evt_date).days
                filing_window_open = True
                window_phase = "inside_window"
                cache_ttl = TTL_INSIDE_WINDOW
                badge_color = "yellow"
            elif evt_type == "deadline":
                next_filing_quarter = label  # This quarter's deadline passed
                days_until_deadline = (evt_date - today).days
            elif evt_type == "window_close":
                # Window has closed for this quarter
                if filing_window_open:
                    filing_window_open = False
                    window_phase = "outside"
                    data_through_quarter = label
                    cache_ttl = TTL_OUTSIDE_WINDOW
                    badge_color = "green"

    # Determine data_through_quarter: the last quarter whose deadline has fully passed
    if data_through_quarter is None:
        # Find the most recent quarter whose window_close has passed
        for evt_date, label, evt_type in reversed(events):
            if evt_type == "window_close" and evt_date <= today:
                data_through_quarter = label
                break
        if data_through_quarter is None:
            # Fallback: Q4 of previous year
            data_through_quarter = "Q4" if today.month <= 2 else f"Q{max(1, ((today.month - 1) // 3))} {today.year - 1}"

    # Refine badge and TTL based on proximity to deadline
    if window_phase == "inside_window":
        if next_deadline and days_until_deadline is not None:
            if days_until_deadline == 0:
                badge = f"🔴 {next_filing_quarter} filings due TODAY!"
                badge_color = "red"
                cache_ttl = 1 * 3600  # 1 hour
            elif days_until_deadline <= 7:
                badge = f"🟡 {next_filing_quarter} filings due in {days_until_deadline} days — active window"
                badge_color = "yellow"
                cache_ttl = TTL_INSIDE_WINDOW
            else:
                badge = f"🟡 {next_filing_quarter} filings incoming — window open ({days_until_deadline} days to deadline)"
                badge_color = "yellow"
                cache_ttl = TTL_INSIDE_WINDOW
        else:
            badge = f"🟡 Filing window open — checking for new {next_filing_quarter} data"
            badge_color = "yellow"
    elif window_phase == "post_deadline":
        badge = f"🔴 {next_filing_quarter} deadline passed — checking for stragglers"
        badge_color = "red"
        cache_ttl = TTL_POST_DEADLINE
    else:
        badge = f"📌 Data through {data_through_quarter} — next window in {days_until_window} days"
        badge_color = "green"

    return {
        "data_through_quarter": data_through_quarter,
        "next_filing_quarter": next_filing_quarter,
        "filing_window_open": filing_window_open,
        "window_phase": window_phase,
        "next_deadline": next_deadline.isoformat() if next_deadline else None,
        "days_until_deadline": days_until_deadline,
        "days_until_window": days_until_window if window_phase == "outside" else None,
        "days_since_window_open": days_since_window_open,
        "cache_ttl_seconds": cache_ttl,
        "badge": badge,
        "badge_color": badge_color,
    }


def filing_aware_ttl(today: date = None) -> int:
    """
    Returns the recommended cache TTL in seconds for 13F data.
    """
    return get_filing_status(today)["cache_ttl_seconds"]


def get_quarter_label(month: int) -> str:
    """Returns Q1-Q4 for a given month number."""
    return f"Q{math.ceil(month / 3)}"


def get_current_data_quarter(today: date = None) -> str:
    """
    Returns the quarter label of the most recent fully-filed 13F data.
    E.g., on June 1, returns "Q1 2025" (Q1 deadline was May 15).
    """
    if today is None:
        today = date.today()

    status = get_filing_status(today)
    return status["data_through_quarter"]
