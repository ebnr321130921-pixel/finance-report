#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ------------------------------------------------------------
# Utility
# ------------------------------------------------------------
PRODUCT_MAP = {
    "楽天QQQ": "Rakuten QQQ",
    "楽天SP500": "Rakuten S&P 500",
    "楽天VTI": "Rakuten VTI",
    "楽天レバナス": "Rakuten LN"
}

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
# Load Source
# ------------------------------------------------------------
def load_source():
    raw = pd.read_csv(BASE/"daily_records.csv")
    prods = ["楽天QQQ", "楽天SP500", "楽天VTI", "楽天レバナス"]
    rows = []

    for jp in prods:
        rows.append(pd.DataFrame({
            "product": PRODUCT_MAP[jp],
            "market_date": pd.to_datetime(raw[f"{jp}_market_date"]),
            "nav": raw[jp],
            "pct": raw[f"{jp}_prev_pct"],
            "cum_pct": raw.get(f"{jp}_cum_pct", np.nan)
        }))

    records = pd.concat(rows).reset_index(drop=True)

    holdings = pd.read_csv(BASE/"holdings.csv")
    holdings["product"] = holdings["product"].map(PRODUCT_MAP)

    return records, holdings


# ------------------------------------------------------------
# Today Summary
# ------------------------------------------------------------
def build_today_summary(records, holdings):
    latest = records["market_date"].max()
    today = records[records["market_date"] == latest]

    df = today.merge(holdings, on="product", how="left")
    df = df.assign(
        prod_diff = df["nav"] * df["pct"] / 100,
        value = df["units"] * df["nav"] / 10000,
        value_diff = df["units"] * df["nav"] * df["pct"] / 100 / 10000,
        value_pct = df["pct"],
        date = latest.strftime("%Y-%m-%d")
    )

    out = df[[
        "product","date","nav","prod_diff","pct",
        "value","value_diff","value_pct"
    ]].rename(columns={"pct":"prod_pct"})

    out.to_csv(BASE/"today_summary.csv", index=False, encoding="utf-8-sig")
    return out


# ------------------------------------------------------------
# Daily Trend（過去10日〜翌2日・平日のみ・曜日つき）
# ------------------------------------------------------------
def build_daily_trend(records):

    latest = records["market_date"].max()
    start = latest - dt.timedelta(days=30)
    end   = latest + dt.timedelta(days=2)

    df = records[(records["market_date"] >= start) & (records["market_date"] <= end)]

    p = df.pivot_table(
        index="market_date",
        columns="product",
        values="pct"
    ).sort_index()

    # ★変更：最新20件のみ（欠損はNaNのまま）
    p = p.tail(20).reset_index()

    p["date"] = p["market_date"].dt.strftime("%Y-%m-%d (%a)")
    p = p.drop(columns=["market_date"])

    p.to_csv(BASE/"daily_chart_data.csv", index=False, encoding="utf-8-sig")
    return p


# ------------------------------------------------------------
# Weekly Trend（過去4週〜翌2週）
# ------------------------------------------------------------
def build_weekly_trend(records):

    df = records.copy()
    df["week"] = df["market_date"].dt.to_period("W-MON")

    weekly = df.groupby(["week","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product").sort_index()

    # ★変更：最新20週のみ（欠損はNaNのまま）
    weekly = weekly.tail(20).reset_index()
    weekly["week"] = weekly["week"].astype(str)

    weekly.to_csv(BASE/"weekly_chart_data.csv", index=False, encoding="utf-8-sig")
    return weekly


# ------------------------------------------------------------
# Cumulative Trend（20件・当日+1まで）
# ------------------------------------------------------------
def build_cumulative_trend(records):
    latest = records["market_date"].max()
    limit = latest + dt.timedelta(days=1)

    df = records[records["market_date"] <= limit].copy()

    p = df.pivot_table(
        index="market_date",
        columns="product",
        values="cum_pct"
    ).reset_index()

    # ★変更：最新20件のみ
    p = p.tail(30).rename(columns={"market_date":"date"})

    p.to_csv(BASE/"cum_chart_data.csv", index=False, encoding="utf-8-sig")
    # ★追加：テーブル用
    p.to_csv(BASE/"cum_table_data.csv", index=False, encoding="utf-8-sig")
    return p


# -------------------------------------------------------------
# HTML（Apple Card UI）
# -------------------------------------------------------------
def build_dashboard_html(today, daily, weekly, cumulative):

    import json

    products = [c for c in daily.columns if c not in ["date"]]

    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body {
    background:#f2f2f7;
    font-family:-apple-system, BlinkMacSystemFont, Helvetica, Arial;
    padding:22px;
    color:#111;
}
.card {
    background:#ffffff;
    padding:22px;
    border-radius:22px;
    margin-bottom:26px;
    box-shadow:0 6px 18px rgba(0,0,0,0.08);
}
h2 {
    font-size:22px;
    margin-bottom:18px;
    font-weight:600;
}
table {
    width:100%;
    border-collapse:collapse;
    table-layout:fixed;
}
th,td {
    padding:8px 6px;
    border-bottom:1px solid #e5e5ea;
    font-size:13px;
    text-align:right;
}
th:first-child, td:first-child { text-align:left; }
.chart-container {
    width:100%;
    height:420px;
}

/* ===== Today Summary summary fix ===== */
summary.today-summary {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    list-style: none;
}
summary.today-summary::-webkit-details-marker {
    display: none;
}
summary.today-summary::marker {
    display: none;
}
.today-summary .arrow {
    font-size: 14px;
    line-height: 1;
    transition: transform 0.2s ease;
}
details[open] .today-summary .arrow {
    transform: rotate(90deg);
}
.today-summary .title {
    font-size: 22px;
    font-weight: 600;
    line-height: 1;
}
</style>
</head>
<body>
"""

    # =============================================================
    # Today Summary（折りたたみ・1行）
    # =============================================================
    html += """
<details class="card">
<summary class="today-summary">
  <span class="arrow">▶</span>
  <span class="title">Today Summary</span>
</summary>

<table>
<thead>
<tr>
<th>Product</th><th>Date</th><th>NAV</th>
<th>Prod Δ (¥)</th><th>Prod Δ (%)</th>
<th>Value (¥)</th><th>Value Δ (¥)</th><th>Value Δ (%)</th>
</tr>
</thead>
<tbody>
"""

    for _, r in today.iterrows():
        html += f"""
<tr>
<td>{r['product']}</td>
<td>{r['date']}</td>
<td>{fmt_yen(r['nav'])}</td>
<td>{fmt_yen(r['prod_diff'])}</td>
<td>{fmt_pct(r['prod_pct'])}</td>
<td>{fmt_yen(r['value'])}</td>
<td>{fmt_yen(r['value_diff'])}</td>
<td>{fmt_pct(r['value_pct'])}</td>
</tr>
"""

    html += "</tbody></table></details>"

    # -------------------------------------------------------------
    # Chart dataset generator
    # -------------------------------------------------------------
    def make_bar_dataset(df):
        return [{
            "type": "bar",
            "label": prod,
            "data": [None if pd.isna(x) else round(x,2) for x in df[prod]],
            "backgroundColor": COLOR_MAP.get(prod,"#888")
        } for prod in products]

    # =============================================================
    # Daily Performance
    # =============================================================
    html += f"""
<div class="card">
<h2>Daily Performance</h2>
<canvas id="dailyChart" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("dailyChart"), {{
    data: {{
        labels: {json.dumps(daily["date"].tolist())},
        datasets: {json.dumps(make_bar_dataset(daily))}
    }},
    options: {{
        scales: {{ y: {{ title: {{ display:true, text:"Daily %" }} }} }}
    }}
}});
</script>
</div>
"""

    # =============================================================
    # Weekly Performance
    # =============================================================
    html += f"""
<div class="card">
<h2>Weekly Performance</h2>
<canvas id="weeklyChart" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("weeklyChart"), {{
    data: {{
        labels: {json.dumps(weekly["week"].tolist())},
        datasets: {json.dumps(make_bar_dataset(weekly))}
    }},
    options: {{
        scales: {{ y: {{ title: {{ display:true, text:"Weekly %" }} }} }}
    }}
}});
</script>
</div>
"""

    # =============================================================
    # Cumulative Performance（凡例＝最新累積率）
    # =============================================================
    cum_ds = [{
        "type": "line",
        "label": prod,
        "data": [None if pd.isna(x) else round(x,2) for x in cumulative[prod]],
        "borderColor": COLOR_MAP.get(prod),
        "borderWidth": 2,
        "tension": 0,
        "pointRadius": 3
    } for prod in products]

    html += f"""
<div class="card">
<h2>Cumulative Performance</h2>
<canvas id="cumChart" class="chart-container"></canvas>

<script>
new Chart(document.getElementById("cumChart"), {{
    data: {{
        labels: {json.dumps(cumulative["date"].astype(str).tolist())},
        datasets: {json.dumps(cum_ds)}
    }},
    options: {{
        plugins: {{
            legend: {{
                display: true,
                position: "top",
                labels: {{
                    generateLabels: function(chart) {{
                        const datasets = chart.data.datasets;
                        return datasets.map((ds, i) => {{
                            const vals = ds.data.filter(v => v !== null);
                            const latest = vals.length ? vals[vals.length - 1] : null;
                            return {{
                                text: latest !== null
                                    ? ds.label + "  " + latest.toFixed(2) + "%"
                                    : ds.label,
                                strokeStyle: ds.borderColor,
                                fillStyle: ds.borderColor,
                                lineWidth: 2,
                                hidden: !chart.isDatasetVisible(i),
                                datasetIndex: i
                            }};
                        }});
                    }}
                }}
            }}
        }},
        scales: {{
            x: {{ ticks: {{ autoSkip:true, maxTicksLimit:10 }} }},
            y: {{ title: {{ display:true, text:"Cumulative %" }} }}
        }}
    }}
}});
</script>
</div>
"""

    html += "</body></html>"

    (BASE/"dashboard.html").write_text(html, encoding="utf-8")

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    records, holdings = load_source()

    today = build_today_summary(records, holdings)
    daily = build_daily_trend(records)
    weekly = build_weekly_trend(records)
    cumulative = build_cumulative_trend(records)

    build_dashboard_html(today, daily, weekly, cumulative)
    print("=== DONE ===")


if __name__ == "__main__":
    main()
