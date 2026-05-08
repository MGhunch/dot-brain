#!/usr/bin/env python3
"""
Build a Hunch-styled monthly-spend bar chart for one client.

Usage:
    python3 build_chart.py <input.json> <output.png>

Input JSON shape:
    {
      "code": "TOW",
      "name": "Tower",
      "year_end_month": "September",
      "fy_label": "FY25-26",
      "monthly_committed": 10000,
      "total_ytd": 69000,
      "expected_ytd": 80000,
      "variance": -11000,
      "months_so_far": 8,
      "series": [
        {"month_short": "Oct", "year": 2025, "spend": 15500, "is_future": false},
        ...
      ]
    }
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.ticker import FuncFormatter
import numpy as np
from PIL import Image

# ---- Fonts ----
# Both Bebas Neue and DM Sans are bundled in assets/fonts/ alongside this script.
SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = SCRIPT_DIR / "assets"

for path in [str(ASSETS_DIR / "fonts")]:
    if Path(path).exists():
        for f in fm.findSystemFonts(fontpaths=path):
            try:
                fm.fontManager.addfont(f)
            except Exception:
                pass

plt.rcParams["text.parse_math"] = False  # don't treat $ as math mode

# Hunch palette (red as the data colour now, black as structural)
RED         = "#ED1C24"
RED_FUTURE  = "#F8B5B8"  # light red for future-month outlines
BLACK       = "#1A1A1A"
GREY_DARK   = "#444444"
GREY_MED    = "#999999"
GREY_LIGHT  = "#E5E5E5"

BEBAS = "Bebas Neue"
SANS  = "DM Sans"


def _load_logo(code: str):
    """Find a client logo PNG. Returns PIL.Image or None.

    Mirrors Hub's getLogoUrl: ONB and ONS share ONE's logo.
    """
    alias_code = "ONE" if code in ("ONB", "ONS") else code
    candidates = [
        ASSETS_DIR / "logos" / f"{alias_code}.png",
        ASSETS_DIR / "logos" / "Unknown.png",
    ]
    for p in candidates:
        if p.exists():
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                continue
    return None


def build_chart(d: dict, out_path: str) -> str:
    fig = _build_figure(d)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, facecolor="white")
    plt.close(fig)
    return out_path


def build_chart_bytes(d: dict) -> bytes:
    """Same chart, rendered to memory and returned as PNG bytes.
    Used by the worker so we never touch the filesystem on Railway.
    """
    import io
    fig = _build_figure(d)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def build_hunch_chart_bytes(d: dict) -> bytes:
    """Render the Hunch (whole-of-business) chart with paired bars per month
    — committed (outlined) and actual (solid) — so the gap is visible.
    """
    import io
    fig = _build_hunch_figure(d)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _build_hunch_figure(d: dict):
    """Hunch-specific figure builder: paired committed vs actual bars per month.
    Reuses the same chrome (logo, title, variance callout, axis styling) as
    the single-client renderer, just with different bar geometry.
    """
    series = d["series"]
    code = d["code"]
    n = len(series)
    spend = [s["spend"] for s in series]
    committed_vals = [s.get("committed", 0) for s in series]
    is_future = [s["is_future"] for s in series]
    months = [s["month_short"] for s in series]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Bar geometry — two bars per month, side by side, centred on x=i
    pair_width = 0.62
    bar_width  = pair_width / 2 * 0.9   # gap between the pair
    offset     = pair_width / 4         # half the centre-to-centre spacing

    for i, s in enumerate(series):
        muted = s["is_future"] or s.get("is_pre_engagement")
        committed = committed_vals[i]
        actual    = spend[i]

        # COMMITTED bar — left, outlined (the "target box")
        if committed > 0:
            ax.bar(i - offset, committed, width=bar_width,
                   facecolor="#FFFFFF",
                   edgecolor=RED if not muted else RED_FUTURE,
                   linewidth=1.5,
                   linestyle="solid" if not muted else (0, (3, 2)))

        # ACTUAL bar — right, solid red (the "what we did")
        if actual > 0:
            ax.bar(i + offset, actual, width=bar_width,
                   facecolor=RED if not muted else "#FFFFFF",
                   edgecolor="none" if not muted else RED_FUTURE,
                   linewidth=1 if muted else 0,
                   linestyle=(0, (3, 2)) if muted else "solid")

    # Y-axis scale — fit both committed and actual
    max_val = max([0] + committed_vals + spend)
    label_offset = max_val * 0.02 if max_val else 1

    # Value labels above each ACTUAL bar (the spend number is what people read)
    for i, s in enumerate(series):
        if s["spend"] > 0:
            label = f"${s['spend']/1000:.1f}k" if s["spend"] >= 1000 else f"${s['spend']:.0f}"
            muted = s["is_future"] or s.get("is_pre_engagement")
            color = GREY_MED if muted else BLACK
            ax.text(i + offset, s["spend"] + label_offset, label,
                    ha="center", va="bottom", fontsize=8.5,
                    fontfamily=SANS, color=color)

    ymax = max_val * 1.25 if max_val > 0 else 1000
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"${v/1000:.0f}k" if v >= 1000 else f"${v:.0f}"
    ))
    ax.tick_params(axis="y", labelsize=9, colors=GREY_DARK, length=0)
    ax.tick_params(axis="x", labelsize=10, colors=BLACK, length=0, pad=6)

    ax.set_xticks(np.arange(n))
    ax.set_xticklabels(months)
    pre_engagement_flags = [bool(s.get("is_pre_engagement")) for s in series]
    for i, lbl in enumerate(ax.get_xticklabels()):
        muted = is_future[i] or pre_engagement_flags[i]
        lbl.set_color(GREY_MED if muted else GREY_DARK)

    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GREY_LIGHT)
    ax.grid(axis="y", color=GREY_LIGHT, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)

    # Pair-key — small swatch + label on the right, above the chart
    key_y = 0.93
    # Outlined committed swatch
    fig.patches.extend([
        plt.Rectangle((0.66, key_y - 0.012), 0.014, 0.024,
                      transform=fig.transFigure,
                      facecolor="white", edgecolor=RED, linewidth=1.2),
    ])
    fig.text(0.679, key_y, "committed",
             fontfamily=SANS, fontsize=9, color=GREY_DARK,
             ha="left", va="center")
    # Solid actual swatch
    fig.patches.extend([
        plt.Rectangle((0.755, key_y - 0.012), 0.014, 0.024,
                      transform=fig.transFigure,
                      facecolor=RED, edgecolor="none"),
    ])
    fig.text(0.774, key_y, "actual",
             fontfamily=SANS, fontsize=9, color=GREY_DARK,
             ha="left", va="center")

    # Header — same as single-client: [LOGO] {NAME} YTD / period label
    title = f"{d['name'].upper()} YTD"
    title_x = 0.07
    logo = _load_logo(code)
    if logo is not None:
        zoom = 0.45
        oi = OffsetImage(np.asarray(logo), zoom=zoom)
        ab = AnnotationBbox(
            oi, (0.04, 0.91), xycoords="figure fraction",
            frameon=False, box_alignment=(0, 0.5),
        )
        fig.add_artist(ab)
        title_x = 0.10

    fig.text(title_x, 0.94, title,
             fontfamily=BEBAS, fontsize=28, fontweight="bold",
             color=BLACK, ha="left", va="top")
    fig.text(title_x, 0.85, d["fy_label"],
             fontfamily=SANS, fontsize=12, color=GREY_MED,
             ha="left", va="top")

    # Variance callout (top right)
    variance = d["variance"]
    var_color = RED if variance < 0 else BLACK
    var_label = f"−${abs(variance):,.0f}" if variance < 0 else f"+${variance:,.0f}"
    fig.text(0.93, 0.85, var_label,
             fontfamily=BEBAS, fontsize=20, fontweight="bold",
             color=var_color, ha="right", va="top")
    fig.text(0.93, 0.78, "VARIANCE",
             fontfamily=SANS, fontsize=10, color=GREY_MED,
             ha="right", va="top")

    fig.subplots_adjust(left=0.07, right=0.93, top=0.74, bottom=0.10)
    return fig


def _build_figure(d: dict):
    series = d["series"]
    committed = d["monthly_committed"]
    code = d["code"]
    n = len(series)
    spend = [s["spend"] for s in series]
    is_future = [s["is_future"] for s in series]
    months = [s["month_short"] for s in series]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Bars — red for past, faded red dashed outline for future or pre-engagement
    for i, s in enumerate(series):
        muted = s["is_future"] or s.get("is_pre_engagement")
        if muted:
            ax.bar(i, s["spend"], width=0.65, facecolor="#FFFFFF",
                   edgecolor=RED_FUTURE, linewidth=1, linestyle=(0, (3, 2)))
        else:
            ax.bar(i, s["spend"], width=0.65, facecolor=RED, edgecolor="none")

    # Value labels above bars
    committed_max_for_offset = max([s.get("committed", committed) for s in series] + [committed])
    max_val_for_axis = max(max(spend), committed_max_for_offset) if (spend or committed_max_for_offset) else 1
    label_offset = max_val_for_axis * 0.02
    for i, s in enumerate(series):
        if s["spend"] > 0:
            label = f"${s['spend']/1000:.1f}k" if s["spend"] >= 1000 else f"${s['spend']:.0f}"
            muted = s["is_future"] or s.get("is_pre_engagement")
            color = GREY_MED if muted else BLACK
            ax.text(i, s["spend"] + label_offset, label,
                    ha="center", va="bottom", fontsize=9,
                    fontfamily=SANS, color=color)

    # Committed line — stepped, drawn only for months the client was active.
    # Pre-engagement months get no line (no commitment existed yet).
    committed_values = [s.get("committed", committed) for s in series]
    pre_engagement = [bool(s.get("is_pre_engagement")) for s in series]
    for i, c in enumerate(committed_values):
        if pre_engagement[i]:
            continue
        ax.hlines(c, i - 0.5, i + 0.5,
                  color=BLACK, linewidth=1.5, linestyle=(0, (1.5, 2)),
                  zorder=5)
    # Vertical risers where committed changes between active months
    for i in range(len(committed_values) - 1):
        if pre_engagement[i] or pre_engagement[i + 1]:
            continue
        a, b = committed_values[i], committed_values[i + 1]
        if a != b:
            ax.vlines(i + 0.5, min(a, b), max(a, b),
                      color=BLACK, linewidth=1.5, linestyle=(0, (1.5, 2)),
                      zorder=5)

    # Y-axis — accommodate spend bars and the highest committed step
    committed_max = max([s.get("committed", committed) for s in series] + [committed])
    ymax = max(max(spend), committed_max) * 1.25 if max(spend) > 0 else committed_max * 1.5
    if ymax == 0:
        ymax = 1000
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"${v/1000:.0f}k" if v >= 1000 else f"${v:.0f}"
    ))
    ax.tick_params(axis="y", labelsize=9, colors=GREY_DARK, length=0)
    ax.tick_params(axis="x", labelsize=10, colors=BLACK, length=0, pad=6)

    # X-axis (grey out future or pre-engagement month labels)
    ax.set_xticks(np.arange(n))
    ax.set_xticklabels(months)
    pre_engagement_flags = [bool(s.get("is_pre_engagement")) for s in series]
    for i, lbl in enumerate(ax.get_xticklabels()):
        muted = is_future[i] or pre_engagement_flags[i]
        lbl.set_color(GREY_MED if muted else GREY_DARK)

    # Spines + grid
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GREY_LIGHT)
    ax.grid(axis="y", color=GREY_LIGHT, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)

    # Committed label — anchored to the right edge of the chart, above the line
    ax.text(0.98, committed,
            f"${committed/1000:.0f}k/m committed  ",
            transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=9, fontweight="bold",
            color=BLACK, fontfamily=SANS)

    # Header — [LOGO] {NAME} YTD / FY label, plus variance callout top right.
    title = f"{d['name'].upper()} YTD"
    title_x = 0.07
    logo = _load_logo(code)
    if logo is not None:
        # Logo flush with the left-hand chart margin, title sits to its right
        zoom = 0.45  # tuned for an 88px source → ~40px on the figure
        oi = OffsetImage(np.asarray(logo), zoom=zoom)
        ab = AnnotationBbox(
            oi, (0.04, 0.91), xycoords="figure fraction",
            frameon=False, box_alignment=(0, 0.5),
        )
        fig.add_artist(ab)
        title_x = 0.10  # clear of logo with breathing room

    fig.text(title_x, 0.94, title,
             fontfamily=BEBAS, fontsize=28, fontweight="bold",
             color=BLACK, ha="left", va="top")

    fig.text(title_x, 0.85, d["fy_label"],
             fontfamily=SANS, fontsize=12, color=GREY_MED,
             ha="left", va="top")

    # Variance callout (top right) — red iff negative
    variance = d["variance"]
    var_color = RED if variance < 0 else BLACK
    var_label = f"−${abs(variance):,.0f}" if variance < 0 else f"+${variance:,.0f}"
    fig.text(0.93, 0.94, var_label,
             fontfamily=BEBAS, fontsize=28, fontweight="bold",
             color=var_color, ha="right", va="top")
    fig.text(0.93, 0.85, "VARIANCE",
             fontfamily=SANS, fontsize=11, color=GREY_MED,
             ha="right", va="top")

    fig.subplots_adjust(left=0.07, right=0.93, top=0.78, bottom=0.10)
    return fig


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 build_chart.py <input.json> <output.png>", file=sys.stderr)
        sys.exit(2)
    in_path, out_path = sys.argv[1], sys.argv[2]
    data = json.load(open(in_path))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    build_chart(data, out_path)
    print(out_path)


if __name__ == "__main__":
    main()
