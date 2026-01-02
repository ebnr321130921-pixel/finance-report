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
def sign_class(x):
    if pd.isna(x):
        return ""
    try:
        v = float(x)
    except Exception:
        return ""
    if v > 0:
        return "pos"
    if v < 0:
        return "neg"
    return ""

def fmt_yen(x, show_plus=True):
    if pd.isna(x):
        return ""
    v = int(round(float(x)))
    s = f"{abs(v):,}"
    if v < 0:
        return f"-{s}"
    if v > 0 and show_plus:
        return f"+{s}"
    return s

def fmt_pct(x, show_plus=True):
    if pd.isna(x):
        return ""
    v = float(x)
    if v > 0 and show_plus:
        return f"+{v:.2f}%"
    return f"{v:.2f}%"

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
            labels.append(monday.strftime("%m/%d"))
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
            "backgroundColor": COLOR_MAP.get(p, "#888"),
            "categoryPercentage": 0.75,
            "barPercentage": 0.7
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
    # Axis presets
    # ========================================================
    # ---------- BAR（±6% 固定・1%刻み） ----------
    AXIS_BAR = (
        "options:{"
        "layout:{padding:{top:24,bottom:24,left:8,right:8}},"
        "plugins:{"
            "legend:{labels:{color:'#8e8e93',font:{size:13,weight:'600'}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:true,"
        "grid:{display:true,drawBorder:true},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#8e8e93',font:{size:12,weight:'600'}},"
        "},"
        "y:{"
        "min:-6,"
        "max:6,"
        "ticks:{stepSize:1,color:'#8e8e93',font:{size:12,weight:'600'},"
            "callback:function(v){return (v>0?'+':'')+v.toFixed(0)+'%';}"
        "},"
        "title:{display:true,text:'Performance (%)',color:'#8e8e93',font:{size:12,weight:'600'}},"
        "grid:{display:true,color:'#e5e5ea',lineWidth:1},"
        "border:{display:true}"
        "}"
        "}"
        "}"
    )


    # ---------- LINE（Auto・Edge FIX） ----------
    AXIS_LINE = (
        "options:{"
        "layout:{padding:{top:24,bottom:24,left:8,right:8}},"
        "plugins:{"
            "legend:{labels:{color:'#8e8e93',font:{size:13,weight:'600'}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:false,"
        "grid:{display:true,drawBorder:true},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#8e8e93',font:{size:12,weight:'600'}},"
        "},"
        "y:{"
        "title:{display:true,text:'Cumulative (%)',color:'#8e8e93',font:{size:12,weight:'600'}},"
        "grid:{display:true,color:'#e5e5ea',lineWidth:1},"
        "border:{display:true},"
        "ticks:{color:'#8e8e93',font:{size:12,weight:'600'},"
            "callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}"
        "}"
        "}"
        "}"
        "}"
    )

    # ========================================================
    # HTML head
    # ========================================================
    html = """<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <title>Finance Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
            :root {
                --bg-main:#f2f2f7;
                --card-bg:#ffffff;

                /* ✅黒を排除してグレー統一 */
                --text-main:#6e6e73;  /* 通常本文 */
                --text-sub:#8e8e93;   /* 見出し/補助 */
                --text-soft:#aeaeb2;  /* さらに薄い補助 */

                --border:#e5e5ea;

                /* ✅accent (title decoration) */
                --accent-pos:#5ac8fa; /* 水色（プラス） */
                --accent-neg:#ff9bb0; /* ピンク（マイナス） */
            }

            body {
                background:var(--bg-main);
                font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display",Helvetica,Arial,sans-serif;
                padding:20px;
                color:var(--text-main);
                font-size:17px;          /* ✅スマホで拡大しなくて良い寄り */
                line-height:1.6;
            }

            .card {
                background:var(--card-bg);
                padding:22px;
                border-radius:22px;
                margin-bottom:28px;
                box-shadow:0 6px 18px rgba(0,0,0,.08);
            }

            h2 {
                font-size:21px;
                margin-bottom:16px;
                font-weight:650;
                color:var(--text-sub);
            }

            h3 {
                font-size:17px;
                font-weight:650;
                color:var(--text-sub);
            }

            table {
                width:100%;
                border-collapse:separate;
                border-spacing:0;
                font-variant-numeric: tabular-nums;
            }

            th, td {
                padding:14px 12px;
                border-bottom:1px solid var(--border);
                font-size:16px;
                line-height:1.55;
                text-align:right;
                color:var(--text-main);
            }

            th {
                font-weight:650;
                font-size:13px;
                letter-spacing:0.02em;
                color:var(--text-soft);
            }

            td { font-weight:550; }

            th:first-child,
            td:first-child { text-align:left; }

            .chart-container { width:100%; height:420px; }
            .chart-container canvas { width:100% !important; height:100% !important; }

            summary {
                cursor:pointer;
                font-size:18px;
                font-weight:650;
                color:var(--text-sub);
            }

            .highlight {
                font-weight:700;
                color:var(--text-main);
            }

            .section-title {
                position: relative;
                padding-left: 14px;
                font-size: 21px;
                font-weight: 650;
                color: var(--text-sub);
            }

            .section-title::before {
                content: "";
                position: absolute;
                left: 0;
                top: 0.2em;
                width: 4px;
                height: 1.2em;
                border-radius: 2px;
                background: var(--accent-pos); /* ✅水色 */
            }

            /* ✅Update History 用（inline style 排除） */
            .history-item { margin-top:16px; }
            .history-title { font-weight:650; color:var(--text-main); }
            .history-summary { color:var(--text-sub); font-size:15px; margin-top:4px; }

            /* ✅ +/- coloring */
            .pos { color: var(--accent-pos); font-weight: 700; }
            .neg { color: var(--accent-neg); font-weight: 700; }

            /* ✅ key metrics (iDeCo) */
            .key-metric { font-size: 18px; font-weight: 750; color: var(--text-main); }
            .key-metric.pos { color: var(--accent-pos); }
            .key-metric.neg { color: var(--accent-neg); }

        </style>

    </head>
    <body>
    """


    # ========================================================
    # Market Summary
    # ========================================================
    html += """<div class="card"><h2 class="section-title">Market Summary</h2><table>
<tr><th>Product</th><th>Date</th><th>NAV</th><th>Daily %</th><th>Δ ¥ /10k</th></tr>"""
    for _, r in market.iterrows():
        cls_pct = sign_class(r.get("daily_pct"))
        cls_dif = sign_class(r.get("prod_diff_yen_per_10k"))

        html += (
            f"<tr><td>{r['product']}</td>"
            f"<td>{r['date']}</td>"
            f"<td>{fmt_yen(r['nav'], show_plus=False)}</td>"
            f"<td class='{cls_pct}'>{fmt_pct(r['daily_pct'])}</td>"
            f"<td class='{cls_dif}'>{fmt_yen(r['prod_diff_yen_per_10k'])}</td></tr>"
        )
    html += "</table></div>"

    # ========================================================
    # Portfolio + iDeCo
    # ========================================================
    html += """<details class="card"><summary class="section-title">Portfolio (Private)</summary><table>
<tr><th>Product</th><th>Units</th><th>Value ¥</th><th>Daily ¥</th><th>Since ¥</th><th>Since %</th></tr>"""
    for _, r in portfolio.iterrows():
        cls_daily = sign_class(r.get("daily_pnl_yen"))
        cls_since_y = sign_class(r.get("since_change_pnl_yen"))
        cls_since_p = sign_class(r.get("since_change_pnl_pct"))

        html += (
            f"<tr><td>{r['product']}</td>"
            f"<td>{int(r['units'])}</td>"
            f"<td>{fmt_yen(r['value'], show_plus=False)}</td>"
            f"<td class='{cls_daily}'>{fmt_yen(r['daily_pnl_yen'])}</td>"
            f"<td class='{cls_since_y}'>{fmt_yen(r['since_change_pnl_yen'])}</td>"
            f"<td class='{cls_since_p}'>{fmt_pct(r['since_change_pnl_pct'])}</td></tr>"
        )
    html += "</table>"

    if not ideco.empty:
        r = ideco.iloc[0]
        delta = r["end_value"] - r["start_value"]
        html += f"""
        <div style="margin-top:16px;border-top:1px solid #e5e5ea;padding-top:12px">
        <h3 class="section-title">iDeCo Performance</h3>
        <table>
        <tr><th>Period</th><td>{r['start_date']} → {r['end_date']} ({r['years']} yrs)</td></tr>

        <tr><th>Start</th><td class="key-metric">{fmt_yen(r['start_value'], show_plus=False)} ¥</td></tr>
        <tr><th>End</th><td class="key-metric">{fmt_yen(r['end_value'], show_plus=False)} ¥</td></tr>

        <tr><th>Δ Value</th><td class="key-metric {sign_class(delta)}">{fmt_yen(delta)} ¥</td></tr>
        <tr><th>Total Return</th><td class="key-metric {sign_class(r['total_return_pct'])}">{fmt_pct(r['total_return_pct'])}</td></tr>
        <tr><th>CAGR</th><td class="key-metric {sign_class(r['cagr_pct'])}">{fmt_pct(r['cagr_pct'])}</td></tr>
        </table></div>
        """
    html += "</details>"

    # ========================================================
    # Chart helper
    # ========================================================
    def chart(title, cid, labels, datasets, axis):
            return """
        <div class="card">
        <h2 class="section-title">{title}</h2>
        <div class="chart-container">
            <canvas id="{cid}"></canvas>
        </div>
        <script>
        new Chart(document.getElementById("{cid}"), {{
        data: {{ labels: {labels}, datasets: {datasets} }},
        {axis}
        }});
        </script>
        </div>
        """.format(
                title=title,
                cid=cid,
                labels=json.dumps(labels),
                datasets=json.dumps(datasets),
                axis=axis
            )



    # ========================================================
    # Charts
    # ========================================================
    html += chart(f"Daily Performance ({YEAR})", "d1", daily_labels, bar_ds(daily), AXIS_BAR)
    html += chart(f"Daily Cumulative ({YEAR})", "d2", cum_daily_labels, line_ds(cum_daily), AXIS_LINE)

    html += chart(f"Weekly Performance ({YEAR})", "w1", weekly_labels, bar_ds(weekly), AXIS_BAR)
    html += chart(f"Weekly Cumulative ({YEAR})", "w2", weekly_labels_cum, line_ds(cum_weekly), AXIS_LINE)

    html += chart(f"Monthly Performance ({MONTHLY_YEAR_LABEL})", "m1", monthly_labels, bar_ds(monthly), AXIS_BAR)
    html += chart(f"Monthly Cumulative ({MONTHLY_YEAR_LABEL})", "m2", cum_monthly_labels, line_ds(cum_monthly), AXIS_LINE)

    history_path = BASE / "update_history.csv"
    if history_path.exists():
        hist = pd.read_csv(history_path)

        html += """
        <details class="card" style="margin-top:32px">
          <summary class="section-title">Update History</summary>
        """

        for _, r in hist.sort_values("version", ascending=False).iterrows():
            html += f"""
            <div class="history-item">
              <div class="history-title">Ver {r['version']} – {r['title']}</div>
              <div class="history-summary">{r['summary']}</div>
            </div>
            """

        html += "</details>"


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
