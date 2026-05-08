"""
Hunch Spend Chart Service
Generate a rolling-12-month bar chart for the whole agency, aggregating
spend across all active clients with their total monthly committed line.

GO IN → GET ALL CLIENTS → FOR EACH: TRACKER + BUDGET HISTORY →
AGGREGATE BY MONTH → RENDER PNG → GET OUT

Returns base64-encoded PNG plus a one-line summary, same shape as the
single-client handler.
"""

import base64
from datetime import date
from collections import defaultdict

from flask import jsonify

from utils import airtable
from .build_chart import build_hunch_chart_bytes
from .handler import (
    MONTHS, MONTH_NUM,
    _derive_year, _committed_for_month,
)


# ===================
# HELPERS
# ===================

def _rolling_12_months(today: date):
    """Return ordered list of (month_num, year) for the rolling window
    ending with today's month. 12 months total — today's month is the last
    entry and is treated as in-flight."""
    months = []
    # Walk 12 months backward from today, then reverse to get chronological order
    y, m = today.year, today.month
    for _ in range(12):
        months.append((m, y))
        if m == 1:
            m, y = 12, y - 1
        else:
            m -= 1
    months.reverse()
    return months


def _period_label(months):
    """Format the rolling window as 'May 25 – Apr 26' for the subtitle/filename."""
    if not months:
        return ""
    (m1, y1) = months[0]
    (m2, y2) = months[-1]
    start = f"{MONTHS[m1 - 1][:3]} {str(y1)[2:]}"
    end = f"{MONTHS[m2 - 1][:3]} {str(y2)[2:]}"
    return f"{start} – {end}"


def _client_first_spend_in_window(tracker_records, window_set):
    """Find the client's first month with positive tracked spend that
    falls within the rolling window. Returns (year, month) tuple or None."""
    earliest = None
    for r in tracker_records:
        month_name = r.get("month")
        spend = r.get("spend") or 0
        created = r.get("createdTime")
        if not month_name or not created or spend <= 0:
            continue
        m = MONTH_NUM.get(month_name)
        if not m:
            continue
        y = _derive_year(m, created)
        if (y, m) not in window_set:
            continue
        t = (y, m)
        if earliest is None or t < earliest:
            earliest = t
    return earliest


def _build_hunch_series(active_clients_data, today: date) -> dict:
    """Aggregate spend + committed across all active clients per month
    in the rolling 12-month window.

    active_clients_data: list of dicts with keys
        client (with code/name/year_end/monthly_committed),
        tracker (list of records),
        budget_history (list of records)
    """
    window_months = _rolling_12_months(today)
    window_set = set((y, m) for (m, y) in window_months)
    today_tuple = (today.year, today.month)

    # Aggregate spend across all clients for each (year, month)
    spend_by_month = defaultdict(float)
    # Aggregate committed across all clients for each (year, month).
    # Skip a client's committed for months before their first tracked spend
    # (pre-engagement filter, applied per client).
    committed_by_month = defaultdict(float)

    client_status = []  # for the summary text

    for entry in active_clients_data:
        client = entry["client"]
        tracker = entry["tracker"]
        budget_hist = entry["budget_history"]
        clients_committed = client.get("monthly_committed") or 0

        # Spend bucket for this client
        client_spend_in_window = 0.0
        for r in tracker:
            month_name = r.get("month")
            spend = r.get("spend") or 0
            created = r.get("createdTime")
            if not month_name or not created:
                continue
            m = MONTH_NUM.get(month_name)
            if not m:
                continue
            y = _derive_year(m, created)
            if (y, m) in window_set:
                spend_by_month[(y, m)] += spend
                if (y, m) <= today_tuple:
                    client_spend_in_window += spend

        # Pre-engagement boundary for this client (within the window)
        first_spend_tuple = _client_first_spend_in_window(tracker, window_set)

        # Committed contribution for this client per month
        client_committed_in_window = 0.0
        for (m, y) in window_months:
            if first_spend_tuple is None:
                # No tracked spend in the window at all → don't count their committed
                continue
            if (y, m) < first_spend_tuple:
                continue
            committed = _committed_for_month(y, m, budget_hist, clients_committed)
            committed_by_month[(y, m)] += committed
            if (y, m) <= today_tuple and (y, m) != today_tuple:
                # only past completed months count for variance
                client_committed_in_window += committed

        client_status.append({
            "code": client["code"],
            "spend": client_spend_in_window,
            "committed_completed": client_committed_in_window,
        })

    # Build the series in chronological order
    series = []
    for (m, y) in window_months:
        is_future = (y, m) > today_tuple
        is_inflight = (y, m) == today_tuple
        spend = spend_by_month.get((y, m), 0)
        committed = committed_by_month.get((y, m), 0)
        # Treat in-flight current month visually like 'future' (faded outline,
        # excluded from variance) since it's not done yet.
        series.append({
            "month_short": MONTHS[m - 1][:3],
            "month_full": MONTHS[m - 1],
            "year": y,
            "is_future": is_future or is_inflight,
            "is_pre_engagement": False,  # at agency level, the per-client filter has already done its job
            "spend": round(spend, 2),
            "committed": round(committed, 2),
        })

    # Variance over completed months where the agency was active
    # (had at least one client with active commitment that month)
    completed = [s for s in series if not s["is_future"]]
    active_completed = [s for s in completed if s["committed"] > 0]
    total_ytd = sum(s["spend"] for s in active_completed)
    expected_ytd = sum(s["committed"] for s in active_completed)
    variance = total_ytd - expected_ytd
    months_so_far = len(active_completed)

    # Headline committed = the current month's total, the most "right now" number
    current_committed = next(
        (s["committed"] for s in series if (s["year"], MONTH_NUM[s["month_full"]]) == today_tuple),
        series[-1]["committed"] if series else 0,
    )

    # Did the total committed change during the window?
    distinct_committed = sorted({s["committed"] for s in series if s["committed"] > 0})
    committed_changed = len(distinct_committed) > 1

    return {
        "code": "HUN",
        "name": "Hunch",
        "year_end_month": "",  # not applicable
        "fy_label": _period_label(window_months),
        "monthly_committed": current_committed,
        "committed_changed": committed_changed,
        "total_ytd": round(total_ytd, 2),
        "expected_ytd": round(expected_ytd, 2),
        "variance": round(variance, 2),
        "months_so_far": months_so_far,
        "series": series,
        "client_count": len(active_clients_data),
    }


def _summarise(d: dict) -> str:
    """One-line summary for Claude to use in its reply."""
    name = d["name"]
    period = d["fy_label"]
    ytd = d["total_ytd"]
    expected = d["expected_ytd"]
    variance = d["variance"]
    direction = "behind" if variance < 0 else ("ahead" if variance > 0 else "on pace")
    base = (
        f"{name} — {period}: ${ytd:,.0f} billed against ${expected:,.0f} expected "
        f"({d['months_so_far']} completed months, {d['client_count']} active clients). "
        f"${abs(variance):,.0f} {direction} on a simple-aggregate basis (rollovers reset "
        f"quarterly per client — this aggregate doesn't reflect carry-forward write-offs)."
    )
    if d.get("committed_changed"):
        base += " Total committed shifted during the window (renegotiations) — chart shows the stepped line."
    return base


# ===================
# MAIN HANDLER
# ===================

def generate_hunch_spend_chart(data):
    """
    Build a rolling 12-month spend chart for the whole agency.

    Input:
        data: {} (no parameters needed)

    Returns:
        Flask jsonify response with base64 PNG + summary, same shape
        as the single-client handler.
    """
    print(f"[hunch_chart] === BUILDING HUNCH CHART ===")

    # 1. Pull all clients with non-zero Monthly Committed
    all_clients = airtable.get_all_clients_for_chart()
    active = [c for c in all_clients if (c.get("monthly_committed") or 0) > 0]
    print(f"[hunch_chart] Active clients: {len(active)} of {len(all_clients)}")

    if not active:
        return jsonify({
            "success": False,
            "error": "No active clients found (all have Monthly Committed = 0)."
        }), 404

    # 2. For each active client, fetch tracker + budget history
    active_data = []
    for client in active:
        code = client["code"]
        tracker = airtable.get_tracker_for_client(code)
        budget_hist = airtable.get_budget_history_for_client(code)
        active_data.append({
            "client": client,
            "tracker": tracker,
            "budget_history": budget_hist,
        })

    # 3. Build the rolling 12-month series
    today = airtable.get_nz_today()
    chart_data = _build_hunch_series(active_data, today)

    # 4. Render PNG
    try:
        png_bytes = build_hunch_chart_bytes(chart_data)
    except Exception as e:
        print(f"[hunch_chart] Render failed: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": f"Render failed: {e}"}), 500

    image_b64 = base64.b64encode(png_bytes).decode("ascii")
    summary = _summarise(chart_data)

    print(f"[hunch_chart] Done. Image size: {len(png_bytes):,} bytes")

    return jsonify({
        "success": True,
        "summary": summary,
        "image_base64": image_b64,
        "client_code": "HUN",
        "client_name": "Hunch",
        "fy_label": chart_data["fy_label"],
        "variance": chart_data["variance"],
    })
