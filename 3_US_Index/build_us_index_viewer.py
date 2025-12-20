#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Index Viewer (FINAL / Mobile Decision UI)

- Market Performance (Daily / Weekly, both with Last)
- Decision Index Summary
- Assessment
- Mahalanobis Correlation (Short × Long, weighted 5-day trail)

Display only (NO recalculation)
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

fmt = lambda x, s="": f"{x:+,.2f}{s}"
perf["LastDisp"]  = perf["Last"].map(lambda x: f"{x:,.2f}")
perf["DayDisp"]   = perf["Day"].map(lambda x: fmt(x))
perf["WeekDisp"]  = perf["Week"].map(lambda x: fmt(x))
perf["%DayDisp"]  = perf["%Day"].map(lambda x: fmt(x, "%"))
perf["%WeekDisp"] = perf["%Week"].map(lambda x: fmt(x, "%"))

def perf_color(index, val):
    if index == "VIX":     # 下がる＝安心
        return "blue" if val < 0 else "red"
    if index == "USDJPY":  # 円安＝ウェルカム
        return "blue" if val > 0 else "red"
    return "blue" if val > 0 else "red"

# =========================================================
# Decision Index Summary
# =========================================================
metrics = pd.read_csv(METRIC_PATH)
metrics["date"] = pd.to_datetime(metrics["date"])
latest = metrics.sort_values("date").iloc[-1]

def status(val, low, high):
    if val < low:
        return "LOW", "blue"
    elif val < high:
        return "NORMAL", "green"
    else:
        return "HIGH", "red"

decision_rows = []
s, c = status(latest["RiskScore"], 0.3, 0.6)
decision_rows.append(("RiskScore", latest["RiskScore"], s, c, "Overall market risk"))

for k, note in [
    ("MRDI_Short", "Short-term deviation"),
    ("MRDI_Long",  "Structural deviation"),
    ("MA20_MRDI",  "Short MA distance"),
    ("MA60_MRDI",  "Mid MA distance"),
]:
    if k in latest:
        s, c = status(latest[k], 2.5, 3.5)
        decision_rows.append((k, latest[k], s, c, note))

# =========================================================
# MRDI Correlation (5-day trail)
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

COLOR = lambda w: f"rgba(0,122,255,{w})"
RADIUS = lambda w: 4 if w < 1 else 7
WIDTH  = lambda w: 1.5 + w*1.5

trail_svg = ""
prev = None
for _, r in trail.iterrows():
    cx = 20 + (r.mrdi_short - x_min) / (x_max - x_min) * 320
    cy = 340 - (r.mrdi_long  - y_min) / (y_max - y_min) * 320
    col = COLOR(r.weight)

    if prev:
        trail_svg += (
            f"<line x1='{prev[0]}' y1='{prev[1]}' "
            f"x2='{cx}' y2='{cy}' "
            f"stroke='{col}' stroke-width='{WIDTH(r.weight)}'/>"
        )
    trail_svg += (
        f"<circle cx='{cx}' cy='{cy}' "
        f"r='{RADIUS(r.weight)}' fill='{col}'/>"
    )
    prev = (cx, cy)

# =========================================================
# Text
# =========================================================
summary_text = SUMMARY_TEXT_PATH.read_text(encoding="utf-8")

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
body {{
  font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial;
  background:#f5f5f7;
  margin:0;
  padding:12px;
}}
.card {{
  background:#fff;
  border-radius:14px;
  padding:14px;
  margin-bottom:16px;
}}
h2 {{ margin:0 0 12px 0; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:6px; text-align:right; }}
th:first-child,td:first-child {{ text-align:left; }}
tr:nth-child(even) {{ background:#fafafa; }}

.blue{{color:#007aff}} .green{{color:#34c759}} .red{{color:#ff3b30}}
.gray{{color:#8e8e93}}

svg{{width:100%; height:auto}}
</style>
</head>

<body>

<div class="card">
<h2>Market Performance (Daily)</h2>
<table>
<tr><th>Index</th><th>Last</th><th>Day</th><th>%</th></tr>
{''.join(
f"<tr><td>{r.Index}</td><td>{r.LastDisp}</td>"
f"<td class='{perf_color(r.Index,r.Day)}'>{r.DayDisp}</td>"
f"<td class='{perf_color(r.Index,r.Day)}'>{r['%DayDisp']}</td></tr>"
for _,r in perf.iterrows())}
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
for _,r in perf.iterrows())}
</table>
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
<h2>Assessment</h2>
<pre>{summary_text}</pre>
</div>

<div class="card">
<h2>MRDI Correlation (Short × Long)</h2>
<svg viewBox="0 0 360 360">
<line x1="20" y1="340" x2="340" y2="340" stroke="#aaa"/>
<line x1="20" y1="20" x2="20" y2="340" stroke="#aaa"/>
{''.join(
f"<circle cx='{20+(r.mrdi_short-x_min)/(x_max-x_min)*320}' "
f"cy='{340-(r.mrdi_long-y_min)/(y_max-y_min)*320}' r='2' fill='#d1d1d6'/>"
for _,r in past.iterrows())}
{trail_svg}
</svg>
<p class="gray">薄→濃 = 古→新（最大5日）</p>
</div>

</body>
</html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
print("GENERATED:", OUT_HTML)
