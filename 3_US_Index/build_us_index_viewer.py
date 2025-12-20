#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Index Viewer (FINAL / Mobile Decision UI)

Display only (NO recalculation)

- Market Performance (Daily / Weekly, both with Last)
- Decision Index Summary
- Assessment
- MRDI Correlation (Short × Long, 5-day trail)
"""

import pandas as pd
import numpy as np
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SUMMARY_TABLE_PATH = DATA_DIR / "market_summary_table.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"
MRDI_PATH = DATA_DIR / "mrdi_scatter_short_long.csv"
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
# Decision Index Summary
# =========================================================
metrics = pd.read_csv(METRIC_PATH)
metrics["date"] = pd.to_datetime(metrics["date"])
latest = metrics.sort_values("date").iloc[-1]

def status(v, low, high):
    if v < low:
        return "LOW", "blue"
    elif v < high:
        return "NORMAL", "green"
    else:
        return "HIGH", "red"

decision_rows = []
s, c = status(latest["RiskScore"], 0.3, 0.6)
decision_rows.append(("RiskScore", latest["RiskScore"], s, c, "Overall risk"))

for k, note in [
    ("MRDI_Short", "Short-term"),
    ("MRDI_Long",  "Structural"),
    ("MA20_MRDI",  "MA20"),
    ("MA60_MRDI",  "MA60"),
]:
    if k in latest:
        s, c = status(latest[k], 2.5, 3.5)
        decision_rows.append((k, latest[k], s, c, note))

# =========================================================
# MRDI Correlation
# =========================================================
mrdi = pd.read_csv(MRDI_PATH)
mrdi["date"] = pd.to_datetime(mrdi["date"])
mrdi = mrdi.dropna(subset=["mrdi_short", "mrdi_long"]).sort_values("date")

trail = mrdi.tail(5).copy()
trail["weight"] = [0.2, 0.4, 0.6, 0.8, 1.0][-len(trail):]
past = mrdi.iloc[:-len(trail)]

x = mrdi["mrdi_short"]
y = mrdi["mrdi_long"]

x_min, x_max = x.min(), x.max()
y_min, y_max = y.min(), y.max()
x_mean, y_mean = x.mean(), y.mean()

def cx(v): return 40 + (v - x_min) / (x_max - x_min) * 300
def cy(v): return 320 - (v - y_min) / (y_max - y_min) * 300

def color(w): return f"rgba(0,122,255,{w})"
def radius(): return 3
def width(w): return 1.2 + w

trail_svg = ""
prev = None
for _, r in trail.iterrows():
    px, py = cx(r.mrdi_short), cy(r.mrdi_long)
    if prev:
        trail_svg += (
            f"<line x1='{prev[0]:.1f}' y1='{prev[1]:.1f}' "
            f"x2='{px:.1f}' y2='{py:.1f}' "
            f"stroke='{color(r.weight)}' stroke-width='{width(r.weight):.1f}'/>"
        )
    trail_svg += (
        f"<circle cx='{px:.1f}' cy='{py:.1f}' r='{radius()}' fill='{color(r.weight)}'/>"
    )
    prev = (px, py)

today = trail.iloc[-1]

# =========================================================
# Assessment Text
# =========================================================
summary_text = SUMMARY_TEXT_PATH.read_text(encoding="utf-8")
assessment_paragraphs = [l.strip() for l in summary_text.splitlines() if l.strip()]

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

body {{
  font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial;
  background:#f5f5f7;
  margin:0;
  padding:12px;
  line-height:1.5;
}}

.card {{
  background:#fff;
  border-radius:14px;
  padding:14px;
  margin-bottom:16px;
}}

h2 {{
  margin:0 0 10px 0;
  font-size:1.15rem;
  font-weight:600;
}}

table {{
  width:100%;
  border-collapse:collapse;
}}

th, td {{
  padding:6px;
  text-align:right;
}}

th:first-child, td:first-child {{
  text-align:left;
}}

tr:nth-child(even) {{
  background:#fafafa;
}}

.blue {{ color:#007aff; }}
.green {{ color:#34c759; }}
.red {{ color:#ff3b30; }}
.gray {{ color:#8e8e93; }}

.note {{ white-space:nowrap; }}

.assessment p {{
  margin:0 0 0.6em 0;
}}

svg {{ width:100%; height:auto; }}
</style>
</head>

<body>

<div class="card assessment">
<h2>Assessment</h2>
{''.join(f"<p>{p}</p>" for p in assessment_paragraphs)}
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
<h2>Market Performance (Weekly)</h2>
<table>
<tr><th>Index</th><th>Last</th><th>Week</th><th>%</th></tr>
{''.join(
f"<tr><td>{r.Index}</td><td>{r.LastDisp}</td>"
f"<td class='{perf_color(r.Index,r.Week)}'>{r.WeekDisp}</td>"
f"<td class='{perf_color(r.Index,r.Week)}'>{r['%WeekDisp']}</td></tr>"
for _, r in perf.iterrows())}
</table>
</div>

<div class="card">
<h2>Decision Index Summary</h2>
<table>
<tr><th>Index</th><th>Value</th><th>Status</th><th class="note">Note</th></tr>
{''.join(
f"<tr><td>{n}</td><td>{v:.2f}</td><td class='{c}'><b>{s}</b></td><td class='gray note'>{note}</td></tr>"
for n,v,s,c,note in decision_rows)}
</table>
</div>

<div class="card">
<h2>MRDI Correlation (Short × Long)</h2>

<svg viewBox="0 0 360 360">

<!-- Axis -->
<line x1="40" y1="320" x2="340" y2="320" stroke="#aaa"/>
<line x1="40" y1="40" x2="40" y2="320" stroke="#aaa"/>

<!-- Axis ticks -->
<text x="40" y="334" font-size="10" fill="#6e6e73">{x_min:.1f}</text>
<text x="{cx(x_mean):.1f}" y="334" font-size="10" fill="#6e6e73" text-anchor="middle">{x_mean:.1f}</text>
<text x="340" y="334" font-size="10" fill="#6e6e73" text-anchor="end">{x_max:.1f}</text>

<text x="8" y="320" font-size="10" fill="#6e6e73" text-anchor="end">{y_min:.1f}</text>
<text x="8" y="{cy(y_mean):.1f}" font-size="10" fill="#6e6e73" text-anchor="end">{y_mean:.1f}</text>
<text x="8" y="40" font-size="10" fill="#6e6e73" text-anchor="end">{y_max:.1f}</text>

<!-- Past cluster -->
{''.join(
f"<circle cx='{cx(r.mrdi_short):.1f}' cy='{cy(r.mrdi_long):.1f}' r='2' fill='#d1d1d6'/>"
for _, r in past.iterrows())}

<!-- Trail -->
{trail_svg}

<!-- Mean lines (TOP) -->
<line x1="{cx(x_mean):.1f}" y1="40" x2="{cx(x_mean):.1f}" y2="320"
      stroke="#34c759" stroke-dasharray="4"/>
<line x1="40" y1="{cy(y_mean):.1f}" x2="340" y2="{cy(y_mean):.1f}"
      stroke="#34c759" stroke-dasharray="4"/>

<!-- Legend -->
<rect x="46" y="46" width="250" height="32" rx="6" fill="#ffffff" stroke="#e5e5ea"/>
<circle cx="60" cy="62" r="3" fill="#007aff"/>
<text x="72" y="66" font-size="11" fill="#007aff">
Today : MRDI Short {today.mrdi_short:.2f} / Long {today.mrdi_long:.2f}
</text>

<!-- Axis labels -->
<text x="190" y="350" font-size="11" fill="#6e6e73" text-anchor="middle">MRDI Short</text>
<text x="10" y="190" font-size="11" fill="#6e6e73"
      transform="rotate(-90 10 190)">MRDI Long</text>

</svg>
</div>

</body>
</html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
print("GENERATED:", OUT_HTML)
