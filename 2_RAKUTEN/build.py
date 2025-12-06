#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ============================================
# Utility
# ============================================

def load_csv(name):
    return pd.read_csv(BASE / name)

def save_csv(df, name):
    df.to_csv(BASE / name, index=False)

# 日本語 → 英語の正規化
def normalize_product(jp):
    mapping = {
        "楽天QQQ": "Rakuten QQQ",
        "楽天SP500": "Rakuten S&P 500",
        "楽天VTI": "Rakuten VTI",
        "楽天レバナス": "Rakuten LN"
    }
    return mapping.get(jp, jp)

def fmt_yen(x):
    if pd.isna(x):
        return ""
    return f"{int(round(x)):,}"

def fmt_pct(x):
    if pd.isna(x):
        return ""
    return f"{x:.2f}%"

# ============================================
# 0. Load source
# daily_records.csv を縦持ちへ変換
# ============================================

def load_source():
    raw = load_csv("daily_records.csv")

    # 構造チェック
    required_cols = ["fetch_time", "global_market_date"]
    for c in required_cols:
        if c not in raw.columns:
            raise ValueError(f"daily_records.csv に {c} が存在しません")

    # 製品群の抽出
    jp_products = ["楽天QQQ", "楽天SP500", "楽天VTI", "楽天レバナス"]

    rows = []
    for _, r in raw.iterrows():
        for jp in jp_products:
            prod = normalize_product(jp)
            nav = r[jp]
            market_date = r[f"{jp}_market_date"]
            diff = r[f"{jp}_prev_diff"]
            pct = r[f"{jp}_prev_pct"]

            rows.append({
                "product": prod,
                "market_date": market_date,
                "nav": nav,
                "diff": diff,
                "diff_pct": pct
            })

    df = pd.DataFrame(rows)

    # 日付変換
    df["market_date"] = pd.to_datetime(df["market_date"])

    holdings = load_csv("holdings.csv")
    holdings["product"] = holdings["product"].apply(normalize_product)

    return df, holdings

# ============================================
# 1. Today Summary
# ============================================

def build_today_summary(records, holdings):

    latest_date = records["market_date"].max()
    today_rows = records[records["market_date"] == latest_date]

    all_products = sorted(records["product"].unique())
    out = []

    for prod in all_products:
        r = today_rows[today_rows["product"] == prod]
        h = holdings[holdings["product"] == prod]

        nav = r.iloc[0]["nav"] if len(r) else np.nan
        diff = r.iloc[0]["diff"] if len(r) else np.nan
        pct = r.iloc[0]["diff_pct"] if len(r) else np.nan

        units = h.iloc[0]["units"] if len(h) else 0
        value = units * nav / 10000 if not pd.isna(nav) else np.nan
        value_diff = units * diff / 10000 if not pd.isna(diff) else np.nan
        value_pct = pct

        out.append({
            "product": prod,
            "date": latest_date.strftime("%Y-%m-%d"),
            "nav": nav,
            "prod_diff": diff,
            "prod_pct": pct,
            "value": value,
            "value_diff": value_diff,
            "value_pct": value_pct
        })

    df_out = pd.DataFrame(out)
    save_csv(df_out, "today_summary.csv")
    return df_out

# ============================================
# 2. Daily Trend
# ============================================

def build_daily_trend(records):

    latest = records["market_date"].max()
    start = latest - pd.Timedelta(days=30)
    end = latest + pd.Timedelta(days=10)

    full_dates = pd.date_range(start, end)
    products = sorted(records["product"].unique())

    p = records.pivot_table(
        index="market_date",
        columns="product",
        values="nav"
    )

    p2 = p.reindex(full_dates).fillna(method="ffill")

    base = p2.iloc[0]
    cum = (p2 / base - 1) * 100
    daily = p2.pct_change() * 100

    out = pd.DataFrame({"date": full_dates})
    for prod in products:
        out[f"{prod}_cum"] = cum[prod].values
        out[f"{prod}_daily"] = daily[prod].values

    save_csv(out, "daily_chart_data.csv")
    return out

# ============================================
# 3. Weekly Trend（Monthly Performance）
# ============================================

def build_weekly_trend(records):

    latest = records["market_date"].max()
    start = latest - pd.Timedelta(days=365)
    end = latest + pd.Timedelta(days=150)

    full_dates = pd.date_range(start, end)
    products = sorted(records["product"].unique())

    p = records.pivot_table(
        index="market_date",
        columns="product",
        values="nav"
    )

    p2 = p.reindex(full_dates).fillna(method="ffill")

    # 週ラベル（月曜ベース）
    week_labels = []
    for d in full_dates:
        monday = d - pd.Timedelta(days=d.weekday())
        week_labels.append(monday.strftime("%Y/%m/%dW"))

    p2["week"] = week_labels

    week_df = p2.groupby("week").last()

    base = week_df.iloc[0][products]
    cum = (week_df[products] / base - 1) * 100
    weekly = week_df[products].pct_change() * 100

    out = pd.DataFrame({"week": week_df.index})
    for prod in products:
        out[f"{prod}_cum"] = cum[prod].values
        out[f"{prod}_weekly"] = weekly[prod].values

    save_csv(out, "monthly_chart_data.csv")
    return out

# ============================================
# 4. HTML Dashboard
# ============================================

def build_dashboard_html(today, daily, weekly):

    products = sorted(today["product"].unique())

    color_map = {
        "Rakuten QQQ": "#007aff",
        "Rakuten S&P 500": "#ff9500",
        "Rakuten VTI": "#34c759",
        "Rakuten LN": "#af52de"
    }

    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body { font-family:-apple-system; padding:24px; background:#f5f5f7; }
h2 { font-weight:600; margin-top:40px; }
.table-container { background:#fff; padding:20px; border-radius:16px; }
table { width:100%; border-collapse:collapse; }
th,td { padding:6px 8px; border-bottom:1px solid #e5e5e7; font-size:13px; }
.chart-container { width:100%; height:420px; }
</style>
</head>
<body>
"""

    # === TODAY SUMMARY ======================================
    html += """
<h2>Today Summary</h2>
<div class="table-container">
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
<td>{r["product"]}</td>
<td>{r["date"]}</td>
<td>{fmt_yen(r["nav"])}</td>
<td>{fmt_yen(r["prod_diff"])}</td>
<td>{fmt_pct(r["prod_pct"])}</td>
<td>{fmt_yen(r["value"])}</td>
<td>{fmt_yen(r["value_diff"])}</td>
<td>{fmt_pct(r["value_pct"])}</td>
</tr>
"""

    html += "</tbody></table></div>"

    # === DAILY CHART ===========================================
    labels = daily["date"].dt.strftime("%Y-%m-%d").tolist()

    ds = []
    for prod in products:
        c = color_map[prod]
        cum = daily[f"{prod}_cum"].round(2).fillna(0).tolist()
        day = daily[f"{prod}_daily"].round(2).fillna(0).tolist()

        ds.append({
            "label": f"{prod} (Cumulative)",
            "type": "line",
            "data": cum,
            "borderColor": c,
            "pointRadius": 2,
            "tension": 0.3,
            "yAxisID": "y"
        })
        ds.append({
            "label": f"{prod} (Daily)",
            "type": "bar",
            "data": day,
            "backgroundColor": c + "33",
            "yAxisID": "y"
        })

    import json

    html += f"""
<h2>Daily Performance</h2>
<canvas id="dailyChart" class="chart-container"></canvas>

<script>
new Chart(document.getElementById("dailyChart"), {{
    data: {{
        labels: {json.dumps(labels)},
        datasets: {json.dumps(ds)}
    }},
    options: {{
        scales: {{
            y: {{
                min: -5, max: 5, ticks: {{ stepSize: 1 }},
                title: {{ display: true, text: "Performance (%)" }}
            }}
        }}
    }}
}});
</script>
"""

    # === WEEKLY CHART ==========================================
    labels_w = weekly["week"].tolist()

    ds2 = []
    for prod in products:
        c = color_map[prod]
        cum = weekly[f"{prod}_cum"].round(2).fillna(0).tolist()
        wk = weekly[f"{prod}_weekly"].round(2).fillna(0).tolist()

        ds2.append({
            "label": f"{prod} (Cumulative)",
            "type": "line",
            "data": cum,
            "borderColor": c,
            "pointRadius": 2,
            "tension": 0.3,
            "yAxisID": "y"
        })
        ds2.append({
            "label": f"{prod} (Weekly)",
            "type": "bar",
            "data": wk,
            "backgroundColor": c + "33",
            "yAxisID": "y"
        })

    html += f"""
<h2>Weekly Performance</h2>
<canvas id="weeklyChart" class="chart-container"></canvas>

<script>
new Chart(document.getElementById("weeklyChart"), {{
    data: {{
        labels: {json.dumps(labels_w)},
        datasets: {json.dumps(ds2)}
    }},
    options: {{
        scales: {{
            y: {{
                min: -10, max: 10, ticks: {{ stepSize: 2 }},
                title: {{ display: true, text: "Performance (%)" }}
            }}
        }}
    }}
}});
</script>
"""

    html += "</body></html>"

    (BASE / "dashboard.html").write_text(html, encoding="utf-8")

# ============================================
# MAIN
# ============================================

def main():
    print("=== LOADING ===")
    rec, hold = load_source()

    print("=== TODAY ===")
    today = build_today_summary(rec, hold)

    print("=== DAILY ===")
    daily = build_daily_trend(rec)

    print("=== WEEKLY ===")
    weekly = build_weekly_trend(rec)

    print("=== HTML ===")
    build_dashboard_html(today, daily, weekly)

    print("=== DONE ===")

if __name__ == "__main__":
    main()
