"""
Spend Chart Service
Generate a YTD monthly-spend bar chart for one client, with their
monthly-committed line, in Hunch visual style.

GO IN → GET CLIENT + TRACKER → BUILD SERIES → RENDER PNG → GET OUT

Returns base64-encoded PNG plus a one-line summary. Brain hands the
summary to Claude (so Claude can talk about it) and pipes the image
through to Hub as a side-channel attachment.
"""

import base64
from datetime import date, datetime, timezone
from collections import defaultdict

from flask import jsonify

from utils import airtable
from .build_chart import build_chart_bytes


# ===================
# CONSTANTS
# ===================

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}


# ===================
# HELPERS
# ===================

def _parse_created_time(iso_str: str) -> datetime:
    """Parse Airtable createdTime (ISO 8601 with Z) into a UTC datetime."""
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    return datetime.fromisoformat(iso_str)


def _derive_year(month_num: int, created_iso: str) -> int:
    """Pick the year whose (year, month) is closest to createdTime.

    Handles backdated records (logged late) and forward-planned ones
    (logged early) symmetrically. Documented in the build skill.
    """
    dt = _parse_created_time(created_iso)
    cy, cm = dt.year, dt.month
    return min(
        [cy - 1, cy, cy + 1],
        key=lambda y: abs((y - cy) * 12 + (month_num - cm))
    )


def _fy_for_today(year_end_month: int, today: date):
    """Return (start_year, end_year, ordered list of (month_num, year))
    for the financial year containing today."""
    if today.month > year_end_month:
        fy_start_year = today.year
    else:
        fy_start_year = today.year - 1
    fy_end_year = fy_start_year + 1

    start_m = (year_end_month % 12) + 1  # month after year-end
    months = []
    m, y = start_m, fy_start_year
    for _ in range(12):
        months.append((m, y))
        if m == 12:
            m, y = 1, y + 1
        else:
            m += 1
    return fy_start_year, fy_end_year, months


def _committed_for_month(year: int, month_num: int,
                         budget_history: list, clients_fallback: float) -> float:
    """Return the monthly committed amount for (year, month_num).

    Looks up Budget History for the most recent record where
    Effective From <= first day of target month. Falls back to the
    Clients table's Monthly Committed if no Budget History entry applies.

    Mirrors the Hub's tracker.py get_committed model — same inputs, same
    semantics, just inlined here so the worker doesn't depend on Hub code.
    """
    target = date(year, month_num, 1)
    matching = []
    for row in budget_history:
        eff_str = row.get('effective_from')
        if not eff_str:
            continue
        try:
            eff = date.fromisoformat(eff_str)
        except (TypeError, ValueError):
            continue
        if eff <= target:
            matching.append((eff, row.get('monthly_committed', 0)))
    if matching:
        matching.sort(key=lambda x: x[0], reverse=True)
        return float(matching[0][1])
    return float(clients_fallback or 0)


def _build_series(client: dict, tracker_records: list,
                  budget_history: list, today: date) -> dict:
    """Aggregate tracker records into the 12-month FY series the renderer expects."""
    year_end_name = client["year_end"]
    if year_end_name not in MONTH_NUM:
        raise ValueError(f"Bad year_end value: {year_end_name!r}")
    year_end_num = MONTH_NUM[year_end_name]
    clients_committed = client.get("monthly_committed") or 0

    # Bucket spend by (month_num, year)
    agg = defaultdict(float)
    for r in tracker_records:
        month_name = r.get("month")
        spend = r.get("spend") or 0
        created = r.get("createdTime")
        if not month_name or not created:
            continue
        m = MONTH_NUM.get(month_name)
        if not m:
            continue
        y = _derive_year(m, created)
        agg[(m, y)] += spend

    fy_start, fy_end, fy_months = _fy_for_today(year_end_num, today)
    series = []
    today_tuple = (today.year, today.month)

    # Determine the first month in this FY that has any tracked spend.
    # Months before that pre-date the engagement and shouldn't count toward
    # expected/variance. (A six-month gap of $0s isn't an underspend — it's
    # months before the meter started running.)
    fy_month_set = set((y, m) for (m, y) in fy_months)
    first_spend_tuple = None
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
        if (y, m) in fy_month_set:
            t = (y, m)
            if first_spend_tuple is None or t < first_spend_tuple:
                first_spend_tuple = t

    for (m, y) in fy_months:
        spend = agg.get((m, y), 0)
        is_future = (y, m) > today_tuple
        # Pre-engagement = before the first month with any tracked spend in this FY
        is_pre_engagement = (
            first_spend_tuple is not None and (y, m) < first_spend_tuple
        )
        committed = _committed_for_month(y, m, budget_history, clients_committed)
        series.append({
            "month_short": MONTHS[m - 1][:3],
            "month_full": MONTHS[m - 1],
            "year": y,
            "is_future": is_future,
            "is_pre_engagement": is_pre_engagement,
            "spend": round(spend, 2),
            "committed": round(committed, 2),
        })

    # Variance only counts months where the client was active and the month
    # has happened. Future months and pre-engagement months excluded.
    counted_months = [
        s for s in series
        if not s["is_future"] and not s["is_pre_engagement"]
    ]
    total_ytd = sum(s["spend"] for s in counted_months)
    months_so_far = len(counted_months)
    expected_ytd = sum(s["committed"] for s in counted_months)
    variance = total_ytd - expected_ytd

    # Detect whether committed changed during the FY
    committed_values = sorted({s["committed"] for s in series if s["committed"] > 0})
    committed_changed = len(committed_values) > 1
    # "Headline" committed for the label — use the most recent month's value
    # (current month's committed if available, else the latest non-zero value)
    current_committed = next(
        (s["committed"] for s in series if (s["year"], MONTH_NUM[s["month_full"]]) == today_tuple),
        series[-1]["committed"] if series else clients_committed,
    )

    return {
        "code": client["code"],
        "name": client["name"],
        "year_end_month": year_end_name,
        "fy_label": f"FY{str(fy_start)[2:]}-{str(fy_end)[2:]}",
        "monthly_committed": current_committed,   # for label
        "committed_changed": committed_changed,   # signals stepped line worth annotating
        "total_ytd": round(total_ytd, 2),
        "expected_ytd": round(expected_ytd, 2),
        "variance": round(variance, 2),
        "months_so_far": months_so_far,
        "series": series,
    }


def _summarise(d: dict) -> str:
    """One-line text summary for Claude to use in its reply."""
    name = d["name"]
    fy = d["fy_label"]
    ytd = d["total_ytd"]
    expected = d["expected_ytd"]
    variance = d["variance"]
    direction = "behind" if variance < 0 else ("ahead" if variance > 0 else "on pace")
    base = (
        f"{name} {fy}: ${ytd:,.0f} YTD against ${expected:,.0f} expected "
        f"({d['months_so_far']} months in). ${abs(variance):,.0f} {direction} "
        f"on a simple-aggregate basis (note: rollovers reset quarterly — "
        f"this number doesn't reflect carry-forward write-offs)."
    )
    if d.get("committed_changed"):
        base += " Committed amount changed during the FY — chart shows the stepped line."
    return base


# ===================
# MAIN HANDLER
# ===================

def generate_spend_chart(data):
    """
    Build a YTD spend chart for one client.

    Input:
        data: {"client_code": "TOW"}

    Returns:
        Flask jsonify response:
        {
          "success": true,
          "summary": "<one-line summary>",
          "image_base64": "<PNG bytes b64>",
          "client_code": "TOW",
          "client_name": "Tower",
          "fy_label": "FY25-26",
          "variance": -11000
        }
    """
    client_code = (data or {}).get("client_code", "").strip().upper()
    print(f"[spend_chart] === BUILDING CHART ===")
    print(f"[spend_chart] Client: {client_code}")

    if not client_code:
        return jsonify({"success": False, "error": "Missing client_code"}), 400

    # 1. Pull client metadata
    client = airtable.get_client_for_chart(client_code)
    if not client:
        return jsonify({
            "success": False,
            "error": f"Client {client_code} not found in Clients table"
        }), 404

    if not client.get("monthly_committed"):
        return jsonify({
            "success": False,
            "error": (
                f"{client_code} has no Monthly Committed value set. "
                "Add one in the Clients table or pick a different client."
            )
        }), 400

    # 2. Pull tracker records and budget history for this client
    tracker_records = airtable.get_tracker_for_client(client_code)
    budget_history  = airtable.get_budget_history_for_client(client_code)
    print(f"[spend_chart] Tracker records: {len(tracker_records)}, "
          f"Budget History: {len(budget_history)}")

    # 3. Build the 12-month series (NZ today)
    today = airtable.get_nz_today()
    chart_data = _build_series(client, tracker_records, budget_history, today)

    # 4. Render PNG
    try:
        png_bytes = build_chart_bytes(chart_data)
    except Exception as e:
        print(f"[spend_chart] Render failed: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": f"Render failed: {e}"}), 500

    image_b64 = base64.b64encode(png_bytes).decode("ascii")
    summary = _summarise(chart_data)

    print(f"[spend_chart] Done. Image size: {len(png_bytes):,} bytes  "
          f"({len(image_b64):,} chars b64)")

    return jsonify({
        "success": True,
        "summary": summary,
        "image_base64": image_b64,
        "client_code": chart_data["code"],
        "client_name": chart_data["name"],
        "fy_label": chart_data["fy_label"],
        "variance": chart_data["variance"],
    })
