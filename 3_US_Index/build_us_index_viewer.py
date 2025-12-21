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
    W, H = 360, 360
    left, right = 50, 330
    top, bottom = 40, 320

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

    <text x="{(left+right)/2:.1f}" y="{H-10}" font-size="11" fill="#6e6e73" text-anchor="middle">{x_label}</text>
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
# Assessment
# =========================================================
assessment_paragraphs = [
    l.strip() for l in SUMMARY_TEXT_PATH.read_text(encoding="utf-8").splitlines()
    if l.strip()
]

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
.blue {{ color:#007aff; }} .green {{ color:#34c759; }}
.red {{ color:#ff3b30; }} .gray {{ color:#8e8e93; }}
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

<div class="card"><div class="risk {risk_color}">RISK : {risk_label}</div></div>

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
<h2>MRDI Correlation (Short × Long)</h2>
{svg_mrdi}
</div>

<div class="card">
<h2>RiskScore × MRDI Short</h2>
{svg_risk_short}
</div>

<div class="card assessment">
<details>
<summary>Assessment</summary>
{''.join(f"<p>{p}</p>" for p in assessment_paragraphs)}
</details>
</div>

</body>
</html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
print("GENERATED:", OUT_HTML)
