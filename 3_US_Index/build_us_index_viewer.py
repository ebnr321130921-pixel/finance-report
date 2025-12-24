#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Index Viewer (FINAL / Mobile Decision UI)

Display only (NO recalculation)

- Market Performance (Daily)
- Market Performance (Weekly) [collapsible]
- Decision Index Summary
- MRDI Correlation (Short × Long, SPC-based scatter)
- RiskScore × MRDI Short (SPC-based scatter)
- Assessment (collapsible, bottom)

=========================================================
[Scatter Graph Rules — DO NOT REGRESS]
=========================================================
1) Style: Excel-like clean scatter, axis labels + ticks (min/max at least)
2) Points:
   - Base cloud: many points, small, light gray, drawn at back
   - Trace points: small, slightly stronger than base, connected with thin dotted line
   - Latest point: on top, slightly larger, colored by SPC thresholds
3) Front order (important):
   Latest point (top) -> SPC lines -> trace line/trace points -> base points (back)
4) Lines:
   - All dotted (no mixed dash styles)
   - Thin (stroke-width=1)
   - Mean: green dotted
   - +1σ: ORANGE dotted
   - +3σ: red dotted
   - Median: NOT drawn
5) Threshold color for Latest:
   - If either axis > +3σ : red
   - Else if either axis > +1σ : orange
   - Else : blue
6) Data columns:
   - mrdi_scatter_short_long.csv : date, mrdi_short, mrdi_long, risk_score, is_latest, display_roled
   - market_state_distribution_summary.csv :
       metric, mean, std, +1sigma, -1sigma, +3sigma, -3sigma, median
   - display_roled convention:
       2 = latest (top)
       1 = trace (connectable)
       0 = base cloud (back)
       0.5 etc allowed; treat as base unless you want special later
=========================================================
"""

import pandas as pd
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SUMMARY_TABLE_PATH = DATA_DIR / "market_summary_table.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"
MRDI_PATH = DATA_DIR / "mrdi_scatter_short_long.csv"
DIST_PATH = DATA_DIR / "market_state_distribution_summary.csv"
SUMMARY_TEXT_PATH = DATA_DIR / "market_summary_text.txt"
NOTES_PATH = DATA_DIR / "market_indicator_notes.csv"
# =========================================================
# Forecast Log / Actual Market
# =========================================================
FORECAST_LOG_PATH = DATA_DIR / "forward_direction_forecast_log.csv"
ACTUAL_PATH = DATA_DIR / "market_factors_raw.csv"

OUT_HTML = BASE_DIR / "us_index.html"

# =========================================================
# Market Performance
# =========================================================
summary = pd.read_csv(SUMMARY_TABLE_PATH)
summary.columns = [c.strip() for c in summary.columns]

def find_col(keys, percent=None):
    for c in summary.columns:
        cl = c.lower()
        if all(k in cl for k in keys):
            if percent is None:
                return c
            if percent and "%" in c:
                return c
            if not percent and "%" not in c:
                return c
    raise KeyError(keys)

COL_ITEM   = find_col(["item"])
COL_LATEST = find_col(["latest"])
COL_DAY    = find_col(["yesterday"], percent=False)
COL_DAY_P  = find_col(["yesterday"], percent=True)
COL_WEEK   = find_col(["lastweek"], percent=False)
COL_WEEK_P = find_col(["lastweek"], percent=True)

INDEX_ITEMS = ["QQQ", "SP500", "NASDAQ", "DOW", "VIX", "US10Y", "USDJPY"]
perf = summary[summary[COL_ITEM].isin(INDEX_ITEMS)].copy()

perf["Index"] = perf[COL_ITEM]
perf["Last"]  = perf[COL_LATEST]
perf["Day"]   = perf[COL_DAY]
perf["%Day"]  = perf[COL_DAY_P]
perf["Week"]  = perf[COL_WEEK]
perf["%Week"] = perf[COL_WEEK_P]

fmt_val = lambda x: f"{x:,.2f}"
fmt_sig = lambda x: f"{x:+,.2f}"
fmt_pct = lambda x: f"{x:+.2f}%"

perf["LastDisp"]  = perf["Last"].map(fmt_val)
perf["DayDisp"]   = perf["Day"].map(fmt_sig)
perf["WeekDisp"]  = perf["Week"].map(fmt_sig)
perf["%DayDisp"]  = perf["%Day"].map(fmt_pct)
perf["%WeekDisp"] = perf["%Week"].map(fmt_pct)

# =========================================================
# Market Dates (from summary_table)
# =========================================================
# Expected columns (name flexible):
# - Market Date / Trading Date
# - Previous Date
# - Week Start
# - Week End

try:
    market_date = summary.loc[0, find_col(["market", "date"])]
except KeyError:
    market_date = ""

try:
    prev_date = summary.loc[0, find_col(["prev", "date"])]
except KeyError:
    prev_date = ""

try:
    week_start = summary.loc[0, find_col(["week", "avg", "from"])]
except KeyError:
    week_start = ""

try:
    week_end = summary.loc[0, find_col(["week", "avg", "to"])]
except KeyError:
    week_end = ""



def perf_color(index, v):
    if index == "VIX":
        return "blue" if v < 0 else "red"
    if index == "USDJPY":
        return "blue" if v > 0 else "red"
    return "blue" if v > 0 else "red"

# =========================================================
# Decision Index Summary & TOP RISK
# =========================================================
metrics = pd.read_csv(METRIC_PATH)
metrics["date"] = pd.to_datetime(metrics["date"])
latest_m = metrics.sort_values("date").iloc[-1]

def status(v, low, high):
    if v < low:
        return "LOW", "blue"
    elif v < high:
        return "NORMAL", "green"
    else:
        return "HIGH", "red"

risk_label, risk_color = status(latest_m["RiskScore"], 0.3, 0.6)

decision_rows = [("RiskScore", latest_m["RiskScore"], risk_label, risk_color, "Overall risk")]
for k, note in [
    ("MRDI_Short", "Short-term"),
    ("MRDI_Long",  "Structural"),
    ("MA20_MRDI",  "MA20"),
    ("MA60_MRDI",  "MA60"),
]:
    if k in latest_m:
        s, c = status(latest_m[k], 2.5, 3.5)
        decision_rows.append((k, latest_m[k], s, c, note))

# =========================================================
# Market Direction Log (Prediction)
# =========================================================
pred_df = pd.read_csv(
    FORECAST_LOG_PATH,
    parse_dates=["as_of_date", "target_date"]
)

latest_asof = pred_df["as_of_date"].max()
pred_today = pred_df[pred_df["as_of_date"] == latest_asof].copy()

WINDOW_ORDER = {"1y": 1, "3y": 3, "5y": 5, "10y": 10, "all": 99}
pred_today["window_order"] = pred_today["window"].map(WINDOW_ORDER)

pred_today = pred_today.sort_values(
    ["horizon", "window_order", "direction_score"],
    ascending=[True, True, True]
)

def dir_class(d: str) -> str:
    d = str(d).upper()
    if d == "UP": return "dir-up"
    if d == "DOWN": return "dir-down"
    if d == "WEAK": return "dir-weak"
    if d == "NEUTRAL": return "dir-neutral"
    return "gray"

def conf_class(c: str) -> str:
    c = str(c).upper()
    if c == "HIGH": return "conf-high"
    if c == "MID":  return "conf-mid"
    if c == "LOW":  return "conf-low"
    return "gray"

def score_class(s: float) -> str:
    try:
        v = float(s)
    except Exception:
        return "gray"
    # “感度高すぎ問題”を避けて、ざっくり3段
    if abs(v) >= 8.0: return "score-strong"
    if abs(v) >= 3.0: return "score-mid"
    return "score-weak"

# =========================================================
# Actual Market Data
# =========================================================
actual_df = pd.read_csv(ACTUAL_PATH, parse_dates=["date"])
actual_df = actual_df.sort_values("date").set_index("date")


# =========================================================
# Evaluation Logic (with dead zone)
# =========================================================
THRESHOLD = {
    "1W": 0.003,   # ±0.3%
    "1M": 0.010,   # ±1.0%
}

def judge_result(row):
    if row["direction"] not in ["UP", "DOWN"]:
        return "NON", "gray"

    if row["target_date"] not in actual_df.index:
        return "NON", "gray"

    th = THRESHOLD.get(row["horizon"], 0.005)

    idx = actual_df.index.get_loc(row["target_date"])
    if idx == 0:
        return "NON", "gray"

    today = actual_df.iloc[idx]["QQQ"]
    prev = actual_df.iloc[idx - 1]["QQQ"]

    ret = (today - prev) / prev

    if abs(ret) < th:
        return "NON", "gray"

    actual_dir = "UP" if ret > 0 else "DOWN"
    return ("HIT", "green") if actual_dir == row["direction"] else ("MISS", "red")

# =========================================================
# Evaluation 대상 : 今日の予測 × 今日時点で答えが出たもののみ
# =========================================================
eval_df = pred_df[pred_df["as_of_date"] == latest_asof].copy()

eval_df[["result", "result_color"]] = eval_df.apply(
    lambda r: pd.Series(judge_result(r)), axis=1
)

# =========================================================
# MRDI / Risk Scatter Data
# =========================================================
mrdi = pd.read_csv(MRDI_PATH)
mrdi.columns = [c.strip() for c in mrdi.columns]
mrdi["date"] = pd.to_datetime(mrdi["date"])

# column name is display_roled (not display_role)
if "display_roled" not in mrdi.columns:
    if "display_role" in mrdi.columns:
        mrdi["display_roled"] = mrdi["display_role"]
    else:
        mrdi["display_roled"] = mrdi.get("is_latest", 0).apply(lambda v: 2 if float(v) == 1.0 else 0)

mrdi = mrdi.dropna(subset=["mrdi_short", "mrdi_long", "risk_score"]).sort_values("date")

# Distribution summary (metric, mean, std, +1sigma, -1sigma, +3sigma, -3sigma, median)
dist_df = pd.read_csv(DIST_PATH)
dist_df.columns = [c.strip() for c in dist_df.columns]
dist_df["metric"] = dist_df["metric"].astype(str).str.strip()
dist = dist_df.set_index("metric")

def D(metric: str, col: str) -> float:
    return float(dist.loc[metric, col])

# Stats
short_mean = D("mrdi_short", "mean")
short_1s   = D("mrdi_short", "+1sigma")
short_3s   = D("mrdi_short", "+3sigma")

long_mean  = D("mrdi_long", "mean")
long_1s    = D("mrdi_long", "+1sigma")
long_3s    = D("mrdi_long", "+3sigma")

risk_mean  = D("risk_score", "mean")
risk_1s    = D("risk_score", "+1sigma")
risk_3s    = D("risk_score", "+3sigma")

# Latest row: prefer display_roled==2, else is_latest==1, else last date
latest_candidates = mrdi[mrdi["display_roled"] == 2]
if len(latest_candidates) > 0:
    latest = latest_candidates.iloc[-1]
else:
    if "is_latest" in mrdi.columns and (mrdi["is_latest"] == 1).any():
        latest = mrdi[mrdi["is_latest"] == 1].iloc[-1]
    else:
        latest = mrdi.iloc[-1]

def latest_color_by_spc(xv: float, x1: float, x3: float, yv: float, y1: float, y3: float) -> str:
    # If either axis exceeds threshold -> color
    if xv > x3 or yv > y3:
        return "#ff3b30"  # red
    if xv > x1 or yv > y1:
        return "#ff9500"  # orange
    return "#007aff"      # blue

# =========================================================
# SVG scatter generator (shared)
# =========================================================
def build_spc_scatter_svg(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
    x_mean: float, x_1s: float, x_3s: float,
    y_mean: float, y_1s: float, y_3s: float,
    latest_row: pd.Series,
    legend_text: str,
):
    # Canvas
    W, H = 360, 230
    left, right = 50, 330
    top, bottom = 36, 195

    x = df[x_col]
    y = df[y_col]
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())

    # avoid divide-by-zero
    if x_max == x_min:
        x_max = x_min + 1e-9
    if y_max == y_min:
        y_max = y_min + 1e-9

    def cx(v): return left + (float(v) - x_min) / (x_max - x_min) * (right - left)
    def cy(v): return bottom - (float(v) - y_min) / (y_max - y_min) * (bottom - top)

    # ticks: min/max only (clean)
    tick_svg = f"""
    <text x="{left}" y="{bottom+14}" font-size="10" fill="#6e6e73">{x_min:.2f}</text>
    <text x="{right}" y="{bottom+14}" font-size="10" fill="#6e6e73" text-anchor="end">{x_max:.2f}</text>

    <text x="{left-6}" y="{bottom}" font-size="10" fill="#6e6e73" text-anchor="end">{y_min:.2f}</text>
    <text x="{left-6}" y="{top+4}" font-size="10" fill="#6e6e73" text-anchor="end">{y_max:.2f}</text>
    """

    # base points (back): display_roled == 0 or others not in (1,2)
    base_df = df[(df["display_roled"] != 1) & (df["display_roled"] != 2)]
    base_points = "".join(
        f"<circle cx='{cx(r[x_col]):.1f}' cy='{cy(r[y_col]):.1f}' r='1.6' fill='#d1d1d6'/>"
        for _, r in base_df.iterrows()
    )

    # trace points + trace line: display_roled == 1 (connect in date order)
    trace_df = df[df["display_roled"] == 1].sort_values("date")
    trace_points = "".join(
        f"<circle cx='{cx(r[x_col]):.1f}' cy='{cy(r[y_col]):.1f}' r='1.6' fill='rgba(0,122,255,0.35)'/>"
        for _, r in trace_df.iterrows()
    )

    trace_line = ""
    if len(trace_df) >= 2:
        pts = [(cx(r[x_col]), cy(r[y_col])) for _, r in trace_df.iterrows()]
        for i in range(1, len(pts)):
            x1, y1 = pts[i-1]
            x2, y2 = pts[i]
            trace_line += (
                f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                f"stroke='rgba(0,122,255,0.35)' stroke-dasharray='3,3' stroke-width='1'/>"
            )

    # SPC lines (front): mean/+1/+3
    spc_lines = f"""
    <!-- Mean (green dotted) -->
    <line x1="{cx(x_mean):.1f}" y1="{top}" x2="{cx(x_mean):.1f}" y2="{bottom}"
          stroke="#34c759" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_mean):.1f}" x2="{right}" y2="{cy(y_mean):.1f}"
          stroke="#34c759" stroke-dasharray="3,3" stroke-width="1"/>

    <!-- +1σ (ORANGE dotted) -->
    <line x1="{cx(x_1s):.1f}" y1="{top}" x2="{cx(x_1s):.1f}" y2="{bottom}"
          stroke="#ff9500" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_1s):.1f}" x2="{right}" y2="{cy(y_1s):.1f}"
          stroke="#ff9500" stroke-dasharray="3,3" stroke-width="1"/>

    <!-- +3σ (red dotted) -->
    <line x1="{cx(x_3s):.1f}" y1="{top}" x2="{cx(x_3s):.1f}" y2="{bottom}"
          stroke="#ff3b30" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_3s):.1f}" x2="{right}" y2="{cy(y_3s):.1f}"
          stroke="#ff3b30" stroke-dasharray="3,3" stroke-width="1"/>
    """

    # Latest point (top)
    lx, ly = cx(latest_row[x_col]), cy(latest_row[y_col])
    latest_fill = latest_color_by_spc(float(latest_row[x_col]), x_1s, x_3s, float(latest_row[y_col]), y_1s, y_3s)
    latest_point = f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.6' fill='{latest_fill}'/>"

    # Axes
    axes = f"""
    <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#c7c7cc"/>
    <line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#c7c7cc"/>

    <text x="{(left+right)/2:.1f}" y="{H-6}" font-size="11"
      fill="#6e6e73" text-anchor="middle">{x_label}</text>
    <text x="15" y="{(top+bottom)/2:.1f}" font-size="11" fill="#6e6e73"
          transform="rotate(-90 15 {(top+bottom)/2:.1f})">{y_label}</text>
    """

    # Legend
    legend = f"""
    <rect x="60" y="50" width="240" height="28" rx="6" fill="#ffffff" stroke="#e5e5ea"/>
    <text x="70" y="69" font-size="11" fill="#6e6e73">{legend_text}</text>
    """

    svg = f"""
    <svg viewBox="0 0 {W} {H}">
      <!-- Axes -->
      {axes}

      <!-- Ticks (min/max) -->
      {tick_svg}

      <!-- Base points (BACK) -->
      {base_points}

      <!-- Trace line (middle) -->
      {trace_line}

      <!-- Trace points (middle) -->
      {trace_points}

      <!-- SPC lines (FRONT) -->
      {spc_lines}

      <!-- Latest point (TOP) -->
      {latest_point}

      <!-- Legend -->
      {legend}
    </svg>
    """
    return svg

# =========================================================
# SVG histogram generator (SPC aligned)
# =========================================================
def build_histogram_svg(series, title, mean=None, s1=None, s3=None, latest=None):
    import numpy as np

    data = series.dropna().values
    if len(data) == 0:
        return ""

    W, H = 360, 78
    left, right = 40, 330
    top, bottom = 14, 64

    bins = 30  # ← 指定どおり30

    hist, edges = np.histogram(data, bins=bins)
    max_h = hist.max() if hist.max() > 0 else 1

    def cx(v):
        return left + (v - edges[0]) / (edges[-1] - edges[0]) * (right - left)

    def cy(v):
        return bottom - (v / max_h) * (bottom - top)

    bars = ""
    for h, x0, x1 in zip(hist, edges[:-1], edges[1:]):
        x = cx(x0)
        w = cx(x1) - cx(x0)
        y = cy(h)
        bars += (
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{bottom-y:.1f}' "
            f"fill='#d1d1d6'/>"
        )

    def vline(val, color):
        if val is None:
            return ""
        x = cx(val)
        return (
            f"<line x1='{x:.1f}' y1='{top}' x2='{x:.1f}' y2='{bottom}' "
            f"stroke='{color}' stroke-dasharray='3,3' stroke-width='1'/>"
            f"<text x='{x:.1f}' y='{top-6}' font-size='7' fill='{color}' opacity='0.85' "
            f"text-anchor='middle' "
            f"transform='rotate(-90 {x:.1f} {top-6})'>"
            f"{val:.2f}</text>"
        )

    lines = ""
    lines += vline(mean, "#34c759")
    lines += vline(s1,   "#ff9500")
    lines += vline(s3,   "#ff3b30")

    if latest is not None:
        if s3 is not None and latest > s3:
            c = "#ff3b30"
        elif s1 is not None and latest > s1:
            c = "#ff9500"
        else:
            c = "#007aff"
        lines += vline(latest, c)

    x_min = edges[0]
    x_max = edges[-1]

    svg = f"""
    <svg viewBox="0 0 {W} {H}">
    {bars}
    {lines}

    <!-- Legend (Right) -->
    <text x="{right+6}" y="{top+10}" font-size="7" fill="#34c759" opacity="0.85">Mean</text>
    <text x="{right+6}" y="{top+22}" font-size="7" fill="#ff9500" opacity="0.85">+1σ</text>
    <text x="{right+6}" y="{top+34}" font-size="7" fill="#ff3b30" opacity="0.85">+3σ</text>
    <text x="{right+6}" y="{top+46}" font-size="7" fill="#007aff" opacity="0.85">Latest</text>

    <text x="10" y="{bottom:.1f}"
    font-size="9" fill="#6e6e73"
    text-anchor="start"
    transform="rotate(-90 10 {bottom:.1f})">
    {title}

    </svg>
    """
    return svg

# =========================================================
# Build 2 scatter SVGs
#   - MRDI Short×Long
#   - RiskScore×MRDI Short
#   (RiskScore×MRDI Long is REMOVED)
# =========================================================
svg_mrdi = build_spc_scatter_svg(
    df=mrdi,
    x_col="mrdi_short",
    y_col="mrdi_long",
    x_label="MRDI Short",
    y_label="MRDI Long",
    x_mean=short_mean, x_1s=short_1s, x_3s=short_3s,
    y_mean=long_mean,  y_1s=long_1s,  y_3s=long_3s,
    latest_row=latest,
    legend_text=f"Today : Short {float(latest.mrdi_short):.2f} / Long {float(latest.mrdi_long):.2f}",
)

svg_risk_short = build_spc_scatter_svg(
    df=mrdi,
    x_col="risk_score",
    y_col="mrdi_short",
    x_label="RiskScore",
    y_label="MRDI Short",
    x_mean=risk_mean, x_1s=risk_1s, x_3s=risk_3s,
    y_mean=short_mean, y_1s=short_1s, y_3s=short_3s,
    latest_row=latest,
    legend_text=f"Today : Risk {float(latest.risk_score):.2f} / MRDI Short {float(latest.mrdi_short):.2f}",
)

# =========================================================
# Histograms (Distribution / SPC aligned)
# =========================================================
hist_mrdi_short = build_histogram_svg(
    mrdi["mrdi_short"], "MRDI Short",
    mean=short_mean,
    s1=short_1s,
    s3=short_3s,
    latest=float(latest.mrdi_short),
)

hist_mrdi_long = build_histogram_svg(
    mrdi["mrdi_long"], "MRDI Long",
    mean=long_mean,
    s1=long_1s,
    s3=long_3s,
    latest=float(latest.mrdi_long)
)

hist_ma20 = build_histogram_svg(
    mrdi["ma20_mrdi"], "MA20 MRDI",
    mean=D("ma20_mrdi", "mean"),
    s1=D("ma20_mrdi", "+1sigma"),
    s3=D("ma20_mrdi", "+3sigma"),
    latest=float(latest.ma20_mrdi)
)

hist_ma60 = build_histogram_svg(
    mrdi["ma60_mrdi"], "MA60 MRDI",
    mean=D("ma60_mrdi", "mean"),
    s1=D("ma60_mrdi", "+1sigma"),
    s3=D("ma60_mrdi", "+3sigma"),
    latest=float(latest.ma60_mrdi)
)

# =========================================================
# Assessment
# =========================================================
assessment_paragraphs = [
    l.strip() for l in SUMMARY_TEXT_PATH.read_text(encoding="utf-8").splitlines()
    if l.strip()
]

# =========================================================
# Indicator Notes (from CSV)
# =========================================================
NOTES_PATH = DATA_DIR / "market_indicator_notes.csv"

notes_df = pd.read_csv(NOTES_PATH)

notes_by_section = {}
for _, r in notes_df.iterrows():
    sec = r["section"]
    notes_by_section.setdefault(sec, []).append(
        f"<p class='gray'><b>{r['title']}</b> — {r['description']}</p>"
    )

indicator_notes_html = "".join(
    f"<h3 style='margin:12px 0 6px 0;font-size:0.95rem;'>{sec}</h3>"
    + "".join(items)
    for sec, items in notes_by_section.items()
)

# =========================================================
# HTML
# =========================================================
html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Market Dashboard</title>

<style>
:root {{ font-size:15px; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial;
       background:#f5f5f7; margin:0; padding:12px; }}
.card {{ background:#fff; border-radius:14px; padding:14px; margin-bottom:16px; }}
h2 {{ margin:0 0 10px 0; font-size:1.15rem; font-weight:600; }}
.risk {{ font-size:1.8rem; font-weight:700; text-align:center; }}
.blue {{ color:#007aff; }}
.green {{ color:#34c759; }}
.red {{ color:#ff3b30; }}
.gray {{ color:#8e8e93; }}

/* --- Prediction / Evaluation semantic colors --- */
.dir-up {{ color:#34c759; font-weight:600; }}
.dir-down {{ color:#ff3b30; font-weight:600; }}
.dir-weak {{ color:#ff9500; font-weight:600; }}
.dir-neutral {{ color:#007aff; font-weight:600; }}

.conf-high {{ color:#ff3b30; font-weight:600; }}
.conf-mid  {{ color:#ff9500; font-weight:600; }}
.conf-low  {{ color:#8e8e93; font-weight:600; }}

.score-strong {{ color:#ff3b30; font-weight:700; }}
.score-mid    {{ color:#ff9500; font-weight:700; }}
.score-weak   {{ color:#8e8e93; font-weight:600; }}

/* 少し“色気”を出す：カード見出しの左アクセント */
h2 {{
  position:relative;
  padding-left:10px;
}}
h2::before {{
  content:"";
  position:absolute;
  left:0;
  top:3px;
  bottom:3px;
  width:3px;
  border-radius:2px;
  background:#007aff;
  opacity:0.55;
}}

table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:6px; text-align:right; }}
th:first-child, td:first-child {{ text-align:left; }}
tr:nth-child(even) {{ background:#fafafa; }}
details summary {{ cursor:pointer; font-weight:600; }}
.assessment p {{ margin:0.6em 0; }}
svg {{ width:100%; height:auto; }}
</style>
</head>

<body>

<div class="card">
  <div class="risk {risk_color}">RISK : {risk_label}</div>
</div>

<div class="card gray" style="font-size:0.85rem; line-height:1.5;">
  <b>Market Date</b> : {market_date}<br>
  <b>Previous Trade</b> : {prev_date}<br>
  <b>Week Range</b> : {week_start} – {week_end}
</div>

<div class="card">
<h2>Market Performance (Daily)</h2>
<table>
<tr><th>Index</th><th>Last</th><th>Day</th><th>%</th></tr>
{''.join(
f"<tr><td>{r.Index}</td><td>{r.LastDisp}</td>"
f"<td class='{perf_color(r.Index,r.Day)}'>{r.DayDisp}</td>"
f"<td class='{perf_color(r.Index,r.Day)}'>{r['%DayDisp']}</td></tr>"
for _, r in perf.iterrows())}
</table>
</div>

<div class="card">
<details>
<summary>Market Performance (Weekly)</summary>
<table>
<tr><th>Index</th><th>Last</th><th>Week</th><th>%</th></tr>
{''.join(
f"<tr><td>{r.Index}</td><td>{r.LastDisp}</td>"
f"<td class='{perf_color(r.Index,r.Week)}'>{r.WeekDisp}</td>"
f"<td class='{perf_color(r.Index,r.Week)}'>{r['%WeekDisp']}</td></tr>"
for _, r in perf.iterrows())}
</table>
</details>
</div>

<div class="card">
<h2>Decision Index Summary</h2>
<table>
<tr><th>Index</th><th>Value</th><th>Status</th><th>Note</th></tr>
{''.join(
f"<tr><td>{n}</td><td>{v:.2f}</td><td class='{c}'><b>{s}</b></td><td class='gray'>{note}</td></tr>"
for n,v,s,c,note in decision_rows)}
</table>
</div>

<div class="card">
<h2>Market Direction Log (Prediction)</h2>
<div class="gray" style="font-size:0.85rem;">As of : {latest_asof.date()}</div>

<table>
<tr>
  <th>Horizon</th><th>Window</th><th>Dir</th>
  <th>Score</th><th>Action</th><th>Conf</th><th>Comment</th>
</tr>

{''.join(
f"<tr>"
f"<td>{r.horizon}</td>"
f"<td>{r.window}</td>"
f"<td class='{dir_class(r.direction)}'><b>{r.direction}</b></td>"
f"<td class='{score_class(r.direction_score)}'>{float(r.direction_score):+,.2f}</td>"
f"<td><b>{r.recommended_action}</b></td>"
f"<td class='{conf_class(r.confidence)}'>{r.confidence}</td>"
f"<td class='gray'>{r.jp_comment}</td>"
f"</tr>"
for _, r in pred_today.iterrows()
)}

</table>
</div>

<!-- ★ これが⑤：Forecast Evaluation を追加 ★ -->
<div class="card">
<details>
<summary>Forecast Evaluation (Answer Check)</summary>

<p class="gray" style="font-size:0.8rem; line-height:1.4; margin:6px 0 10px 0;">
<b>Note:</b><br>
• Evaluation is performed <b>only for forecasts made today</b>.<br>
• Result is judged using <b>QQQ close price</b> on the target date.<br>
• If price change is within a small neutral range (dead zone), result is marked as <b>NON</b>.<br>
• This table represents <b>answer checking</b>, not prediction.
</p>

<table>
<tr>
  <th>As Of</th>
  <th>Target</th>
  <th>Horizon</th>
  <th>Window</th>
  <th>Dir</th>
  <th>Result</th>
</tr>
{''.join(
f"<tr>"
f"<td>{r.as_of_date.date()}</td>"
f"<td>{r.target_date.date()}</td>"
f"<td>{r.horizon}</td>"
f"<td>{r.window}</td>"
f"<td>{r.direction}</td>"
f"<td class='{r.result_color}'><b>{r.result}</b></td>"
f"</tr>"
for _, r in eval_df.iterrows()
)}
</table>

</details>
</div>

<div class="card">
<h2>MRDI Correlation (Short × Long)</h2>
{svg_mrdi}
</div>

<div class="card">
<h2>RiskScore × MRDI Short</h2>
{svg_risk_short}
</div>

<div class="card">
<h2>Distributions (MRDI / MA)</h2>

{hist_mrdi_short}
{hist_mrdi_long}
{hist_ma20}
{hist_ma60}

</div>



<div class="card assessment">
<details>
<summary>Assessment</summary>
{''.join(f"<p>{p}</p>" for p in assessment_paragraphs)}
</details>
</div>

<div class="card">
<details>
<summary>Indicator Notes (Methodology / Caution)</summary>
{indicator_notes_html}
</details>
</div>

</body>
</html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
print("GENERATED:", OUT_HTML)
