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
    rows = []

    for jp, en in PRODUCT_MAP.items():
        rows.append(pd.DataFrame({
            "product": en,
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
# Daily Trend（過去10日〜未来2日／土日削除／曜日付）
# ------------------------------------------------------------
def build_daily_trend(records):

    latest = records["market_date"].max()
    start = latest - dt.timedelta(days=10)
    end   = latest + dt.timedelta(days=2)

    df = records[(records["market_date"] >= start) & (records["market_date"] <= end)]
    p = df.pivot_table(index="market_date", columns="product", values="pct")

    p = p.dropna(how="all").reset_index()
    p["date"] = p["market_date"].dt.strftime("%Y-%m-%d (%a)")
    p = p.drop(columns=["market_date"])

    p.to_csv(BASE/"daily_chart_data.csv", index=False, encoding="utf-8-sig")
    return p


# ------------------------------------------------------------
# Weekly Trend（過去4週〜未来2週）
# ------------------------------------------------------------
def build_weekly_trend(records):

    latest = records["market_date"].max()
    this_week = latest.to_period("W-MON")

    target_weeks = [
        this_week - 4, this_week - 3, this_week - 2, this_week - 1,
        this_week, this_week + 1, this_week + 2
    ]

    df = records.copy()
    df["week"] = df["market_date"].dt.to_period("W-MON")

    weekly = df.groupby(["week","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product").reset_index()

    weekly = weekly[weekly["week"].isin(target_weeks)]
    weekly["week"] = weekly["week"].dt.start_time.dt.strftime("%Y-%m-%d")
    weekly["week"] = weekly["week"] + " W"

    weekly.to_csv(BASE/"weekly_chart_data.csv", index=False, encoding="utf-8-sig")
    weekly.to_csv(BASE/"monthly_chart_data.csv", index=False, encoding="utf-8-sig")

    return weekly


# ------------------------------------------------------------
# Cumulative Trend（最大20件／最新+1日／デイリーと同期間）
# ------------------------------------------------------------
def build_cumulative_trend(records):

    latest = records["market_date"].max()
    start = latest - dt.timedelta(days=10)
    end   = latest + dt.timedelta(days=1)

    df = records[(records["market_date"] >= start) & (records["market_date"] <= end)]

    p = df.pivot_table(
        index="market_date",
        columns="product",
        values="cum_pct"
    ).reset_index()

    p = p.tail(20)
    p = p.rename(columns={"market_date": "date"})

    p.to_csv(BASE/"cum_chart_data.csv", index=False, encoding="utf-8-sig")
    return p


# ------------------------------------------------------------
# HTML Dashboard
# ------------------------------------------------------------
def build_dashboard_html(today, daily, weekly, cumulative):

    import json

    products = [c for c in daily.columns if c not in ["date"]]

    html = """
<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { background:#f5f5f7; font-family:-apple-system; padding:24px; }
h2 { margin-top:40px; }
.table-container { background:#fff; padding:16px; border-radius:16px; }
table { width:100%; border-collapse:collapse; table-layout:fixed; }
th,td { padding:6px 8px; font-size:13px; border-bottom:1px solid #e5e5e7; }
th { text-align:center; }
td { text-align:right; }
td:first-child, th:first-child { text-align:center; }
.chart-container { width:100%; height:420px; }
</style>
</head><body>
"""

    # ----------------- TODAY SUMMARY -----------------
    html += """
<h2>Today Summary</h2>
<div class="table-container">
<table>
<colgroup>
<col style='width:14%;'>
<col style='width:12%;'>
<col style='width:12%;'>
<col style='width:12%;'>
<col style='width:12%;'>
<col style='width:12%;'>
<col style='width:12%;'>
<col style='width:12%;'>
</colgroup>
<thead><tr>
<th>Product</th><th>Date</th><th>NAV</th>
<th>Prod Δ (¥)</th><th>Prod Δ (%)</th>
<th>Value (¥)</th><th>Value Δ (¥)</th><th>Value Δ (%)</th>
</tr></thead><tbody>
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

    html += "</tbody></table></div>"

    # ---------- helper for datasets ----------
    def make_datasets(df, type_="bar"):
        ds = []
        for prod in products:
            ds.append({
                "type": type_,
                "label": prod,
                "data": df[prod].round(2).fillna(0).tolist(),
                "backgroundColor": COLOR_MAP[prod],
                "borderColor": COLOR_MAP[prod],
                "borderWidth": 2,
            })
        return ds


    # ----------------- DAILY CHART -----------------
    daily_labels = daily["date"].tolist()
    ds_daily = make_datasets(daily, "bar")

    html += f"""
<h2>Daily Performance</h2>
<canvas id="dailyChart" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("dailyChart"), {{
    data: {{ labels: {json.dumps(daily_labels)}, datasets: {json.dumps(ds_daily)} }},
    options: {{
        scales: {{
            y: {{
                title: {{ display: true, text: 'Daily %' }}
            }}
        }}
    }}
}});
</script>
"""

    # ----------------- WEEKLY CHART -----------------
    weekly_labels = weekly["week"].tolist()
    ds_weekly = make_datasets(weekly, "bar")

    html += f"""
<h2>Weekly Performance</h2>
<canvas id="weeklyChart" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("weeklyChart"), {{
    data: {{ labels: {json.dumps(weekly_labels)}, datasets: {json.dumps(ds_weekly)} }},
    options: {{
        scales: {{
            y: {{
                title: {{ display: true, text: 'Weekly %' }}
            }}
        }}
    }}
}});
</script>
"""

    # ----------------- CUMULATIVE CHART -----------------
    cum_labels = cumulative["date"].astype(str).tolist()
    cum_ds = []

    for prod in products:
        values = cumulative[prod].round(2).fillna(0).tolist()
        point_sizes = [3]*(len(values)-1) + [7]  # 最新のみ大きい点

        cum_ds.append({
            "type": "line",
            "label": prod,
            "data": values,
            "borderColor": COLOR_MAP[prod],
            "backgroundColor": COLOR_MAP[prod],
            "borderWidth": 2,
            "tension": 0,        # ←完全に折れ線
            "pointRadius": point_sizes,
            "fill": False
        })

    html += f"""
<h2>Cumulative Performance</h2>
<canvas id="cumChart" class="chart-container"></canvas>
<script>
new Chart(document.getElementById("cumChart"), {{
    plugins:[{{
        id: 'valueLabel',
        afterDraw(chart) {{
            const ctx = chart.ctx;
            chart.data.datasets.forEach((ds, i) => {{
                const meta = chart.getDatasetMeta(i);
                const last = meta.data[meta.data.length - 1];
                ctx.fillStyle = ds.borderColor;
                ctx.font = "12px -apple-system";
                ctx.fillText(
                    ds.data[ds.data.length-1] + "%",
                    last.x + 6,
                    last.y - 6
                );
            }});
        }}
    }}],
    data: {{
        labels: {json.dumps(cum_labels)},
        datasets: {json.dumps(cum_ds)}
    }},
    options: {{
        scales: {{
            y: {{
                title: {{ display: true, text: 'Cumulative %' }}
            }}
        }}
    }}
}});
</script>
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
