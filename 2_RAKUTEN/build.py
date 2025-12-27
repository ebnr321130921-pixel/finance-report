#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent

# ============================================================
# Color
# ============================================================
COLOR_MAP = {
    "Rakuten QQQ": "#007aff",
    "Rakuten S&P 500": "#ff9500",
    "Rakuten VTI": "#34c759",
    "Rakuten LN": "#af52de"
}

# ============================================================
# Format helpers
# ============================================================
def fmt_yen(x):
    if pd.isna(x):
        return ""
    return f"{int(round(x)):,}"

def fmt_pct(x):
    if pd.isna(x):
        return ""
    return f"{x:.2f}%"

# ============================================================
# Load CSVs
# ============================================================
def load_data():
    return (
        pd.read_csv(BASE / "summary_market_daily.csv"),
        pd.read_csv(BASE / "summary_portfolio_pnl.csv"),
        pd.read_csv(BASE / "daily_chart_data.csv"),
        pd.read_csv(BASE / "cum_daily_chart_data.csv"),
        pd.read_csv(BASE / "weekly_chart_data.csv"),
        pd.read_csv(BASE / "cum_weekly_chart_data.csv"),
        pd.read_csv(BASE / "monthly_chart_data.csv"),
        pd.read_csv(BASE / "cum_monthly_chart_data.csv"),
        pd.read_csv(BASE / "summary_ideco_return.csv"),
    )

# ============================================================
# HTML Builder
# ============================================================
def build_html(
    market, portfolio,
    daily, cum_daily,
    weekly, cum_weekly,
    monthly, cum_monthly,
    ideco
):
    products = [c for c in daily.columns if c != "date"]

    # ========================================================
    # Year labels
    # ========================================================
    YEAR = pd.to_datetime(daily["date"]).max().year

    monthly_years = sorted({int(m.split("/")[0]) for m in monthly["month"].dropna()})
    MONTHLY_YEAR_LABEL = (
        str(monthly_years[0])
        if len(monthly_years) == 1
        else f"{monthly_years[0]}–{monthly_years[-1]}"
    )

    # ========================================================
    # Label normalization (Python ONLY)
    # ========================================================

    # DAILY_LABELS
    daily_labels = [
        pd.to_datetime(d).strftime("%m/%d")
        for d in daily["date"]
    ]
    cum_daily_labels = [
        pd.to_datetime(d).strftime("%m/%d")
        for d in cum_daily["date"]
    ]

    # WEEKLY_LABELS_MONDAY
    def weekly_monday_labels(series):
        labels = []
        for s in series:
            start = pd.to_datetime(s.split("~")[0].strip())
            monday = start - pd.Timedelta(days=start.weekday())
            labels.append(monday.strftime("%Y/%m/%d"))
        return labels

    weekly_labels = weekly_monday_labels(weekly["week"])
    weekly_labels_cum = weekly_monday_labels(cum_weekly["week"])

    # MONTHLY_LABELS (CSVそのまま)
    monthly_labels = monthly["month"].tolist()
    cum_monthly_labels = cum_monthly["month"].tolist()

    # ========================================================
    # Dataset builders
    # ========================================================
    def bar_ds(df):
        return [{
            "type": "bar",
            "label": p,
            "data": [None if pd.isna(v) else round(v, 2) for v in df[p]],
            "backgroundColor": COLOR_MAP.get(p, "#888")
        } for p in products]

    def line_ds(df):
        return [{
            "type": "line",
            "label": p,
            "data": [None if pd.isna(v) else round(v, 2) for v in df[p]],
            "borderColor": COLOR_MAP.get(p),
            "borderWidth": 2,
            "tension": 0,
            "pointRadius": 3
        } for p in products]

    # ========================================================
    # Axis presets（完全固定）
    # ========================================================
    AXIS_DAILY = (
        "options:{scales:{"
        "x:{ticks:{autoSkip:true,maxTicksLimit:12,maxRotation:0,minRotation:0}},"
        "y:{grid:{display:true},border:{display:true},"
        "ticks:{callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}}}"
        "}}"
    )

    AXIS_WEEKLY = (
        "options:{scales:{"
        "x:{ticks:{autoSkip:true,maxRotation:0,minRotation:0}},"
        "y:{grid:{display:true},border:{display:true},"
        "ticks:{callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}}}"
        "}}"
    )

    AXIS_MONTHLY = AXIS_WEEKLY

    # ========================================================
    # HTML head
    # ========================================================
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {{
    background:#f2f2f7;
    font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial;
    padding:22px;
    color:#111;
}}
.card {{
    background:#fff;
    padding:22px;
    border-radius:22px;
    margin-bottom:26px;
    box-shadow:0 6px 18px rgba(0,0,0,.08);
}}
h2 {{
    font-size:22px;
    margin-bottom:18px;
    font-weight:600;
}}
table {{
    width:100%;
    border-collapse:collapse;
}}
th, td {{
    padding:10px 8px;
    border-bottom:1px solid #e5e5ea;
    font-size:15px;
    text-align:right;
}}
th:first-child, td:first-child {{
    text-align:left;
}}
.chart-container {{
    width:100%;
    height:420px;
}}
summary {{
    cursor:pointer;
    font-size:22px;
    font-weight:600;
}}
.highlight {{
    font-weight:700;
}}
</style>
</head>
<body>
"""

    # ========================================================
    # Market Summary
    # ========================================================
    html += """<div class="card"><h2>Market Summary</h2><table>
<tr><th>Product</th><th>Date</th><th>NAV</th><th>Daily %</th><th>Δ ¥ /10k</th></tr>"""
    for _, r in market.iterrows():
        html += (
            f"<tr><td>{r['product']}</td>"
            f"<td>{r['date']}</td>"
            f"<td>{fmt_yen(r['nav'])}</td>"
            f"<td>{fmt_pct(r['daily_pct'])}</td>"
            f"<td>{fmt_yen(r['prod_diff_yen_per_10k'])}</td></tr>"
        )
    html += "</table></div>"

    # ========================================================
    # Portfolio + iDeCo
    # ========================================================
    html += """<details class="card"><summary>Portfolio (Private)</summary><table>
<tr><th>Product</th><th>Units</th><th>Value ¥</th><th>Daily ¥</th><th>Since ¥</th><th>Since %</th></tr>"""
    for _, r in portfolio.iterrows():
        html += (
            f"<tr><td>{r['product']}</td>"
            f"<td>{int(r['units'])}</td>"
            f"<td>{fmt_yen(r['value'])}</td>"
            f"<td>{fmt_yen(r['daily_pnl_yen'])}</td>"
            f"<td>{fmt_yen(r['since_change_pnl_yen'])}</td>"
            f"<td>{fmt_pct(r['since_change_pnl_pct'])}</td></tr>"
        )
    html += "</table>"

    if not ideco.empty:
        r = ideco.iloc[0]
        delta = r["end_value"] - r["start_value"]
        html += f"""
        <div style="margin-top:16px;border-top:1px solid #e5e5ea;padding-top:12px">
        <h3>iDeCo Performance</h3>
        <table>
        <tr><th>Period</th><td>{r['start_date']} → {r['end_date']} ({r['years']} yrs)</td></tr>
        <tr><th>Start</th><td>{fmt_yen(r['start_value'])} ¥</td></tr>
        <tr><th>End</th><td>{fmt_yen(r['end_value'])} ¥</td></tr>
        <tr><th>Δ Value</th><td class="highlight">{fmt_yen(delta)} ¥</td></tr>
        <tr><th>Total Return</th><td>{fmt_pct(r['total_return_pct'])}</td></tr>
        <tr><th>CAGR</th><td class="highlight">{fmt_pct(r['cagr_pct'])}</td></tr>
        </table></div>
        """
    html += "</details>"

    # ========================================================
    # Chart helper
    # ========================================================
    def chart(title, cid, labels, datasets, axis):
        return f"""
<div class="card"><h2>{title}</h2>
<canvas id="{cid}" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("{cid}"),{{
data:{{labels:{json.dumps(labels)},datasets:{json.dumps(datasets)}}},
{axis}
}});
</script></div>
"""

    # ========================================================
    # Charts
    # ========================================================
    html += chart(f"Daily Performance ({YEAR})", "d1", daily_labels, bar_ds(daily), AXIS_DAILY)
    html += chart(f"Daily Cumulative ({YEAR})", "d2", cum_daily_labels, line_ds(cum_daily), AXIS_DAILY)
    html += chart(f"Weekly Performance ({YEAR})", "w1", weekly_labels, bar_ds(weekly), AXIS_WEEKLY)
    html += chart(f"Weekly Cumulative ({YEAR})", "w2", weekly_labels_cum, line_ds(cum_weekly), AXIS_WEEKLY)
    html += chart(f"Monthly Performance ({MONTHLY_YEAR_LABEL})", "m1", monthly_labels, bar_ds(monthly), AXIS_MONTHLY)
    html += chart(f"Monthly Cumulative ({MONTHLY_YEAR_LABEL})", "m2", cum_monthly_labels, line_ds(cum_monthly), AXIS_MONTHLY)

    html += "</body></html>"

    (BASE / "dashboard.html").write_text(html, encoding="utf-8")

# ============================================================
# MAIN
# ============================================================
def main():
    build_html(*load_data())
    print("=== DASHBOARD HTML GENERATED ===")

if __name__ == "__main__":
    main()
