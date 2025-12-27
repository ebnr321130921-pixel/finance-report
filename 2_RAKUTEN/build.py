#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
from pathlib import Path
import json

BASE = Path(__file__).resolve().parent

# ------------------------------------------------------------
# Color / Format
# ------------------------------------------------------------
COLOR_MAP = {
    "Rakuten QQQ": "#007aff",
    "Rakuten S&P 500": "#ff9500",
    "Rakuten VTI": "#34c759",
    "Rakuten LN": "#af52de"
}

def fmt_yen(x):
    if pd.isna(x): return ""
    return f"{int(round(x)):,}"

def fmt_pct(x):
    if pd.isna(x): return ""
    return f"{x:.2f}%"

# ------------------------------------------------------------
# Load CSVs (Forge outputs)
# ------------------------------------------------------------
def load_data():
    market = pd.read_csv(BASE/"summary_market_daily.csv")
    portfolio = pd.read_csv(BASE/"summary_portfolio_pnl.csv")
    daily = pd.read_csv(BASE/"daily_chart_data.csv")
    cum_daily = pd.read_csv(BASE/"cum_daily_chart_data.csv")
    weekly = pd.read_csv(BASE/"weekly_chart_data.csv")
    cum_weekly = pd.read_csv(BASE/"cum_weekly_chart_data.csv")
    monthly = pd.read_csv(BASE/"monthly_chart_data.csv")
    cum_monthly = pd.read_csv(BASE/"cum_monthly_chart_data.csv")
    return market, portfolio, daily, cum_daily, weekly, cum_weekly, monthly, cum_monthly

# ------------------------------------------------------------
# HTML Builder
# ------------------------------------------------------------
def build_html(market, portfolio, daily, cum_daily, weekly, cum_weekly, monthly, cum_monthly):

    products = [c for c in daily.columns if c != "date"]
    weekly_labels = [s.replace(" ~ ", "\n~\n") for s in weekly["week"].tolist()]
    weekly_labels_cum = [s.replace(" ~ ", "\n~\n") for s in cum_weekly["week"].tolist()]

    def bar_ds(df):
        return [{
            "type":"bar",
            "label":p,
            "data":[None if pd.isna(x) else round(x,2) for x in df[p]],
            "backgroundColor":COLOR_MAP.get(p,"#888")
        } for p in products]

    def line_ds(df):
        return [{
            "type":"line",
            "label":p,
            "data":[None if pd.isna(x) else round(x,2) for x in df[p]],
            "borderColor":COLOR_MAP.get(p),
            "borderWidth":2,
            "tension":0,
            "pointRadius":3
        } for p in products]
    axis_opts_bar = "options:{scales:{x:{ticks:{autoSkip:false,maxRotation:0,minRotation:0,callback:function(v){var l=this.getLabelForValue(v);return l.includes('\\n')?l.split('\\n'):l;}},grid:{display:false}},y:{min:-5,max:5,ticks:{stepSize:1,callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}},title:{display:true,text:'Performance (%)'}}}}"
    axis_opts_line = "options:{scales:{x:{ticks:{autoSkip:false,maxRotation:0,minRotation:0,callback:function(v){var l=this.getLabelForValue(v);return l.includes('\\n')?l.split('\\n'):l;}},grid:{display:false}},y:{ticks:{callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}},title:{display:true,text:'Cumulative (%)'}}}}"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{{background:#f2f2f7;font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial;padding:22px;color:#111}}
.card{{background:#fff;padding:22px;border-radius:22px;margin-bottom:26px;box-shadow:0 6px 18px rgba(0,0,0,.08)}}
h2{{font-size:22px;margin-bottom:18px;font-weight:600}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:8px 6px;border-bottom:1px solid #e5e5ea;font-size:13px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
.chart-container{{width:100%;height:420px}}
summary{{cursor:pointer;font-size:22px;font-weight:600}}
</style>
</head>
<body>
"""

    # ------------------------------------------------------------
    # 1. Market Summary
    # ------------------------------------------------------------
    html += """<div class="card"><h2>Market Summary</h2><table><thead><tr>
<th>Product</th><th>Date</th><th>NAV</th><th>Daily %</th><th>Δ ¥ /10k</th>
</tr></thead><tbody>"""
    for _,r in market.iterrows():
        html += f"<tr><td>{r['product']}</td><td>{r['date']}</td><td>{fmt_yen(r['nav'])}</td><td>{fmt_pct(r['daily_pct'])}</td><td>{fmt_yen(r['prod_diff_yen_per_10k'])}</td></tr>"
    html += "</tbody></table></div>"

    # ------------------------------------------------------------
    # 2. Portfolio (hidden)
    # ------------------------------------------------------------
    html += """<details class="card"><summary>Portfolio (Private)</summary><table><thead><tr>
<th>Product</th><th>Units</th><th>Value ¥</th><th>Daily ¥</th><th>Since ¥</th><th>Since %</th>
</tr></thead><tbody>"""
    for _,r in portfolio.iterrows():
        html += f"<tr><td>{r['product']}</td><td>{int(r['units'])}</td><td>{fmt_yen(r['value'])}</td><td>{fmt_yen(r['daily_pnl_yen'])}</td><td>{fmt_yen(r['since_change_pnl_yen'])}</td><td>{fmt_pct(r['since_change_pnl_pct'])}</td></tr>"
    html += "</tbody></table></details>"

    # ------------------------------------------------------------
    # Charts helper
    # ------------------------------------------------------------
    def chart_block(title, cid, labels, datasets, axis):
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


    html += chart_block("Daily Performance","d1",daily["date"].tolist(),bar_ds(daily),axis_opts_bar)
    html += chart_block("Daily Cumulative","d2",cum_daily["date"].tolist(),line_ds(cum_daily),axis_opts_line)

    html += chart_block("Weekly Performance","w1",weekly_labels,bar_ds(weekly),axis_opts_bar)
    html += chart_block("Weekly Cumulative","w2",weekly_labels_cum,line_ds(cum_weekly),axis_opts_line)

    html += chart_block("Monthly Performance","m1",monthly["month"].tolist(),bar_ds(monthly),axis_opts_bar)
    html += chart_block("Monthly Cumulative","m2",cum_monthly["month"].tolist(),line_ds(cum_monthly),axis_opts_line)

    html += "</body></html>"

    (BASE/"dashboard.html").write_text(html,encoding="utf-8")

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    data = load_data()
    build_html(*data)
    print("=== DASHBOARD HTML GENERATED ===")

if __name__ == "__main__":
    main()
