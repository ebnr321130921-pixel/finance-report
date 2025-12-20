#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Index Viewer (FINAL)

- Market Performance
- Decision Index Summary（Risk / MRDI 系）
- Mahalanobis Analysis
    * Histogram (MRDI Short) + Today line
    * Correlation (Short × Long) + Today point
- Assessment

Viewer = Display only (NO recalculation)
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

COL_ITEM = find_col(["item"])
COL_LATEST = find_col(["latest"])
COL_DAY = find_col(["yesterday"], percent=False)
COL_DAY_P = find_col(["yesterday"], percent=True)
COL_WEEK = find_col(["lastweek"], percent=False)
COL_WEEK_P = find_col(["lastweek"], percent=True)

INDEX_ITEMS = ["QQQ", "SP500", "NASDAQ", "DOW", "VIX", "US10Y", "USDJPY"]
perf_df = summary[summary[COL_ITEM].isin(INDEX_ITEMS)].copy()

perf_df["Index"] = perf_df[COL_ITEM]
perf_df["Last"] = perf_df[COL_LATEST]
perf_df["Day"] = perf_df[COL_DAY]
perf_df["%Day"] = perf_df[COL_DAY_P]
perf_df["Week"] = perf_df[COL_WEEK]
perf_df["%Week"] = perf_df[COL_WEEK_P]

perf_df["Last"] = perf_df["Last"].map(lambda x: f"{x:,.2f}")
perf_df["DayDisp"] = perf_df["Day"].map(lambda x: f"{x:+,.2f}")
perf_df["WeekDisp"] = perf_df["Week"].map(lambda x: f"{x:+,.2f}")
perf_df["%DayDisp"] = perf_df["%Day"].map(lambda x: f"{x:+.2f}%")
perf_df["%WeekDisp"] = perf_df["%Week"].map(lambda x: f"{x:+.2f}%")

# =========================================================
# Risk / MRDI Metrics
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
    ("MRDI_Long", "Structural deviation"),
    ("MA20_MRDI", "Short MA distance"),
    ("MA60_MRDI", "Mid MA distance"),
]:
    s, c = status(latest[k], 2.5, 3.5)
    decision_rows.append((k, latest[k], s, c, note))

# =========================================================
# MRDI Histogram / Scatter
# =========================================================
mrdi = pd.read_csv(MRDI_PATH)
mrdi["date"] = pd.to_datetime(mrdi["date"])

mrdi_valid = mrdi.dropna(subset=["mrdi_short", "mrdi_long"]).copy()

latest_row = mrdi_valid[mrdi_valid["is_latest"] == 1].iloc[-1]
today_short = latest_row["mrdi_short"]
today_long = latest_row["mrdi_long"]

x = mrdi_valid["mrdi_short"]
y = mrdi_valid["mrdi_long"]

x_min, x_max = x.min(), x.max()
y_min, y_max = y.min(), y.max()
x_mean, y_mean = x.mean(), y.mean()

hist, edges = np.histogram(x, bins=24)
hist_max = hist.max()

# =========================================================
# Text
# =========================================================
summary_text = SUMMARY_TEXT_PATH.read_text(encoding="utf-8")

# =========================================================
# HTML
# =========================================================
html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US Market Dashboard</title>

<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, Helvetica, Arial;
  background:#f5f5f7;
  padding:16px;
  font-size:16px;
}}
h2 {{ font-size:20px; margin-top:0; }}

.card {{
  background:#fff;
  border-radius:14px;
  padding:16px;
  margin-bottom:20px;
}}

table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:8px; text-align:right; }}
th:first-child, td:first-child {{ text-align:left; }}
tr:nth-child(even) {{ background:#fafafa; }}

.blue {{ color:#007aff; }}
.green {{ color:#34c759; }}
.red {{ color:#ff3b30; }}
.gray {{ color:#8e8e93; }}

.grid {{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:16px;
}}

svg {{
  width:100%;
  height:auto;
  max-height:240px;
}}

@media (max-width:768px) {{
  body {{ font-size:17px; }}
  h2 {{ font-size:22px; }}
  .grid {{ grid-template-columns:1fr; }}
}}
</style>
</head>

<body>

<!-- Market Performance -->
<div class="card">
<h2>Market Performance</h2>
<table>
<tr><th>Index</th><th>Last</th><th>Day</th><th>%</th><th>Week</th><th>%</th></tr>
{''.join(
f"<tr><td>{r.Index}</td><td>{r.Last}</td>"
f"<td class='{ 'blue' if r.Day>=0 else 'red' }'>{r.DayDisp}</td>"
f"<td class='{ 'blue' if r['%Day']>=0 else 'red' }'>{r['%DayDisp']}</td>"
f"<td class='{ 'blue' if r.Week>=0 else 'red' }'>{r.WeekDisp}</td>"
f"<td class='{ 'blue' if r['%Week']>=0 else 'red' }'>{r['%WeekDisp']}</td></tr>"
for _, r in perf_df.iterrows())}
</table>
</div>

<!-- Decision Index -->
<div class="card">
<h2>Decision Index Summary</h2>
<table>
<tr><th>Index</th><th>Value</th><th>Status</th><th>Note</th></tr>
{''.join(
f"<tr><td>{n}</td><td>{v:.2f}</td><td class='{c}'><b>{s}</b></td><td class='gray'>{note}</td></tr>"
for n,v,s,c,note in decision_rows)}
</table>
</div>

<!-- Mahalanobis Analysis -->
<div class="card">
<h2>Mahalanobis Distance Analysis</h2>

<div class="grid">

<!-- Histogram -->
<div>
<svg viewBox="0 0 360 240">
{''.join(
f"<rect x='{20+i*320/len(hist):.1f}' y='{220-h/hist_max*180:.1f}' "
f"width='{320/len(hist)-1:.1f}' height='{h/hist_max*180:.1f}' fill='#d1d1d6'/>"
for i,h in enumerate(hist))}
<!-- Mean -->
<line x1='{20+(x_mean-x_min)/(x_max-x_min)*320:.1f}' y1='20'
      x2='{20+(x_mean-x_min)/(x_max-x_min)*320:.1f}' y2='220'
      stroke='#34c759' stroke-dasharray='4'/>
<!-- Today -->
<line x1='{20+(today_short-x_min)/(x_max-x_min)*320:.1f}' y1='20'
      x2='{20+(today_short-x_min)/(x_max-x_min)*320:.1f}' y2='220'
      stroke='#007aff' stroke-width='2'/>
</svg>
<p class="gray"><span class="blue">■</span> Today MRDI Short: {today_short:.2f}</p>
</div>

<!-- Scatter -->
<div>
<svg viewBox="0 0 360 360">
<!-- Mean lines -->
<line x1='{20+(x_mean-x_min)/(x_max-x_min)*320:.1f}' y1='20'
      x2='{20+(x_mean-x_min)/(x_max-x_min)*320:.1f}' y2='340'
      stroke='#34c759' stroke-dasharray='4'/>
<line x1='20' y1='{340-(y_mean-y_min)/(y_max-y_min)*320:.1f}'
      x2='340' y2='{340-(y_mean-y_min)/(y_max-y_min)*320:.1f}'
      stroke='#34c759' stroke-dasharray='4'/>
<!-- Past points -->
{''.join(
f"<circle cx='{20+(r.mrdi_short-x_min)/(x_max-x_min)*320:.1f}' "
f"cy='{340-(r.mrdi_long-y_min)/(y_max-y_min)*320:.1f}' "
f"r='2' fill='#d1d1d6'/>"
for _,r in mrdi_valid[mrdi_valid['is_latest']==0].iterrows())}
<!-- Today point -->
<circle cx='{20+(today_short-x_min)/(x_max-x_min)*320:.1f}'
        cy='{340-(today_long-y_min)/(y_max-y_min)*320:.1f}'
        r='5' fill='#007aff'/>
</svg>
<p class="gray">Today: MRDI Short {today_short:.2f}, Long {today_long:.2f}</p>
</div>

</div>
</div>

<!-- Assessment -->
<div class="card">
<h2>Assessment</h2>
<pre>{summary_text}</pre>
</div>

</body>
</html>
"""

OUT_HTML.write_text(html, encoding="utf-8")
print("GENERATED:", OUT_HTML)
