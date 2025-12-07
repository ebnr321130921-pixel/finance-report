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

def load_csv(name):
    return pd.read_csv(BASE / name)

def save_csv(df, name):
    df.to_csv(BASE / name, index=False, encoding="utf-8-sig")

def fmt_yen(x):
    if pd.isna(x): return ""
    return f"{int(round(x)):,}"

def fmt_pct(x):
    if pd.isna(x): return ""
    return f"{x:.2f}%"

# ============================================================
# LOAD 全データ
# ============================================================

def load_source():
    rec = load_csv("daily_records.csv")

    # 正規化
    rec = rec.loc[:, ~rec.columns.str.contains("^Unnamed")]
    rec["fetch_time"] = pd.to_datetime(rec["fetch_time"], errors="coerce")

    # 各列を適切に変換
    for col in rec.columns:
        if col.endswith("_market_date") or col == "global_market_date":
            rec[col] = pd.to_datetime(rec[col], errors="coerce")
        if col.endswith("_prev_pct") or col.endswith("_prev_diff") or col.endswith("_cum_pct"):
            rec[col] = pd.to_numeric(rec[col], errors="coerce")

    holdings = load_csv("holdings.csv")

    return rec, holdings

# ============================================================
# 1. Today Summary（現状維持）
# ============================================================

def build_today_summary(rec, holdings):

    latest = rec["global_market_date"].max()
    rows = rec[rec["global_market_date"] == latest]
    row = rows.sort_values("fetch_time").iloc[-1]

    products = ["楽天QQQ","楽天SP500","楽天VTI","楽天レバナス"]
    en = {
        "楽天QQQ":"Rakuten QQQ",
        "楽天SP500":"Rakuten S&P 500",
        "楽天VTI":"Rakuten VTI",
        "楽天レバナス":"Rakuten LN"
    }

    out = []

    for jp in products:
        prod = en[jp]
        nav = row[jp]
        diff = row[f"{jp}_prev_diff"]
        pct = row[f"{jp}_prev_pct"]

        h = holdings[holdings["product"] == prod]
        units = h["units"].iloc[0] if len(h) else 0
        value = nav * units / 10000 if nav > 0 else np.nan
        value_diff = diff * units / 10000 if diff != 0 else np.nan

        out.append({
            "product": prod,
            "date": latest.strftime("%Y-%m-%d"),
            "nav": nav,
            "prod_diff": diff,
            "prod_pct": pct,
            "value": value,
            "value_diff": value_diff,
            "value_pct": pct
        })

    df = pd.DataFrame(out)
    save_csv(df, "today_summary.csv")
    return df


# ============================================================
# 2. DAILY（棒 + 累積線）
# 当日 -10日 → +5日
# pivot_table を完全排除
# ============================================================

def build_daily_trend(rec):

    latest = rec["global_market_date"].max()
    start = latest - dt.timedelta(days=10)
    end   = latest + dt.timedelta(days=5)
    all_days = pd.date_range(start, end)

    en = {
        "楽天QQQ":"Rakuten QQQ",
        "楽天SP500":"Rakuten S&P 500",
        "楽天VTI":"Rakuten VTI",
        "楽天レバナス":"Rakuten LN"
    }

    # -------- prev_pct --------
    pct_cols = ["global_market_date"] + [f"{jp}_prev_pct" for jp in en.keys()]
    pct_df = rec[pct_cols].drop_duplicates(subset=["global_market_date"], keep="last")
    pct_df = pct_df.set_index("global_market_date")
    pct_df = pct_df.rename(columns={f"{jp}_prev_pct":en[jp] for jp in en.keys()})
    pct_df = pct_df.reindex(all_days)

    # -------- cum_pct --------
    cum_cols = ["global_market_date"] + [f"{jp}_cum_pct" for jp in en.keys()]
    cum_df = rec[cum_cols].drop_duplicates(subset=["global_market_date"], keep="last")
    cum_df = cum_df.set_index("global_market_date")
    cum_df = cum_df.rename(columns={f"{jp}_cum_pct":en[jp] for jp in en.keys()})
    cum_df = cum_df.reindex(all_days)

    # -------- 仕上げ --------
    df = pd.DataFrame({"date": all_days})
    for jp_en in en.values():
        df[jp_en] = pct_df[jp_en].values
        df[f"{jp_en}_cum"] = cum_df[jp_en].values

    save_csv(df, "daily_chart_data.csv")
    return df


# ============================================================
# 3. WEEKLY（棒 + 累積線）
# pivot_table 完全排除
# ============================================================

def build_weekly_trend(rec):

    latest = rec["global_market_date"].max()
    today_week = latest.to_period("W-MON")
    weeks = [today_week - 3, today_week - 2, today_week - 1, today_week, today_week + 1]

    rec["week"] = rec["global_market_date"].dt.to_period("W-MON")

    en = {
        "楽天QQQ":"Rakuten QQQ",
        "楽天SP500":"Rakuten S&P 500",
        "楽天VTI":"Rakuten VTI",
        "楽天レバナス":"Rakuten LN"
    }

    out = []

    for w in weeks:
        rows = rec[rec["week"] == w].sort_values("global_market_date")
        if len(rows) == 0:
            continue

        row = {"week": str(w)}

        for jp in en.keys():
            # weekly pct
            p0 = rows.iloc[0][jp]
            p1 = rows.iloc[-1][jp]
            row[en[jp]] = (p1 / p0 - 1) * 100 if p0 > 0 else np.nan

            # cumulative at week end
            row[f"{en[jp]}_cum"] = rows.iloc[-1][f"{jp}_cum_pct"]

        out.append(row)

    df = pd.DataFrame(out)
    save_csv(df, "weekly_chart_data.csv")
    return df


# ============================================================
# 4. 全期間累積（最新 20 点）
# Simple pivot（手動）
# ============================================================

def build_cum_trend(rec):

    en = {
        "楽天QQQ":"Rakuten QQQ",
        "楽天SP500":"Rakuten S&P 500",
        "楽天VTI":"Rakuten VTI",
        "楽天レバナス":"Rakuten LN"
    }

    cols = ["global_market_date"] + [f"{jp}_cum_pct" for jp in en.keys()]
    df = rec[cols].sort_values("global_market_date").drop_duplicates("global_market_date")

    out = pd.DataFrame()
    out["date"] = df["global_market_date"]

    for jp in en.keys():
        out[en[jp]] = df[f"{jp}_cum_pct"]

    # 最新 20 点だけ
    out = out.tail(20)

    save_csv(out, "cum_chart_data.csv")
    return out


# ============================================================
# DASHBOARD HTML
# Chart.js に daily / weekly / cum を描画
# ============================================================

def build_dashboard_html(today, daily, weekly, cum):

    import json

    products = ["Rakuten QQQ","Rakuten S&P 500","Rakuten VTI","Rakuten LN"]

    color_map = {
        "Rakuten QQQ": "#007aff",
        "Rakuten S&P 500": "#ff9500",
        "Rakuten VTI": "#34c759",
        "Rakuten LN": "#af52de"
    }

    line_color = {
        "Rakuten QQQ": "#0040ff",
        "Rakuten S&P 500": "#cc5500",
        "Rakuten VTI": "#228b22",
        "Rakuten LN": "#7d3ccf"
    }

    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Finance Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body { background:#f5f5f7; font-family:-apple-system; padding:24px; }
h2 { margin-top:40px; }
.table-container { background:#fff; padding:16px; border-radius:16px; }
table { width:100%; border-collapse:collapse; }
th,td { padding:6px 8px; border-bottom:1px solid #e5e5e7; font-size:13px; }
.chart-container { width:100%; height:420px; }
</style>
</head>
<body>
"""

    # ============================================================
    # Today Summary
    # ============================================================

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
</thead><tbody>
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

    # ============================================================
    # Cumulative Performance（20点）
    # ============================================================

    html += """
<h2>Cumulative Performance (Latest 20)</h2>
<canvas id="cumChart" class="chart-container"></canvas>
<script>
"""

    labels = cum["date"].astype(str).tolist()
    datasets = []
    for prod in products:
        datasets.append({
            "type": "line",
            "label": prod,
            "data": cum[prod].round(2).tolist(),
            "borderColor": line_color[prod],
            "borderWidth": 2,
            "tension": 0.2,
            "fill": False
        })

    import json
    html += f"""
new Chart(document.getElementById("cumChart"), {{
    data: {{
        labels: {json.dumps(labels)},
        datasets: {json.dumps(datasets)}
    }},
    options: {{
        scales: {{
            y: {{
                title: {{ display: true, text: "Cumulative %" }}
            }}
        }}
    }}
}});
</script>
"""

    # ============================================================
    # DAILY Performance（棒 + 累積線）
    # ============================================================

    html += """
<h2>Daily Performance</h2>
<canvas id="dailyChart" class="chart-container"></canvas>
<script>
"""

    labels_d = daily["date"].astype(str).tolist()
    ds = []

    for prod in products:
        ds.append({
            "type": "bar",
            "label": prod,
            "data": daily[prod].round(2).tolist(),
            "backgroundColor": color_map[prod]
        })
        ds.append({
            "type": "line",
            "label": prod + " (Cum)",
            "data": daily[f"{prod}_cum"].round(2).tolist(),
            "borderColor": line_color[prod],
            "borderWidth": 2,
            "tension": 0.2,
            "fill": False
        })

    html += f"""
new Chart(document.getElementById("dailyChart"), {{
    data: {{
        labels: {json.dumps(labels_d)},
        datasets: {json.dumps(ds)}
    }},
    options: {{
        scales: {{
            y: {{
                min: -5,
                max: 5,
                ticks: {{ stepSize: 1 }},
                title: {{ display: true, text: "Daily % / Cum %" }}
            }}
        }}
    }}
}});
</script>
"""

    # ============================================================
    # WEEKLY Performance（棒 + 累積線）
    # ============================================================

    html += """
<h2>Weekly Performance</h2>
<canvas id="weeklyChart" class="chart-container"></canvas>
<script>
"""

    labels_w = weekly["week"].tolist()
    ds_w = []

    for prod in products:
        ds_w.append({
            "type": "bar",
            "label": prod,
            "data": weekly[prod].round(2).tolist(),
            "backgroundColor": color_map[prod]
        })
        ds_w.append({
            "type": "line",
            "label": prod + " (Cum)",
            "data": weekly[f"{prod}_cum"].round(2).tolist(),
            "borderColor": line_color[prod],
            "borderWidth": 2,
            "tension": 0.2,
            "fill": False
        })

    html += f"""
new Chart(document.getElementById("weeklyChart"), {{
    data: {{
        labels: {json.dumps(labels_w)},
        datasets: {json.dumps(ds_w)}
    }},
    options: {{
        scales: {{
            y: {{
                min: -5,
                max: 5,
                ticks: {{ stepSize: 1 }},
                title: {{ display: true, text: "Weekly % / Cum %" }}
            }}
        }}
    }}
}});
</script>
"""

    html += "</body></html>"

    (BASE / "dashboard.html").write_text(html, encoding="utf-8")


# ============================================================
# MAIN
# ============================================================

def main():
    rec, holdings = load_source()

    today = build_today_summary(rec, holdings)
    daily = build_daily_trend(rec)
    weekly = build_weekly_trend(rec)
    cum = build_cum_trend(rec)

    build_dashboard_html(today, daily, weekly, cum)

    print("=== BUILD COMPLETED ===")

if __name__ == "__main__":
    main()
