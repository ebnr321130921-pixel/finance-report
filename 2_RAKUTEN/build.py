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
    "Rakuten QQQ": "#4da3ff",
    "Rakuten S&P 500": "#ffb347",
    "Rakuten VTI": "#42d392",
    "Rakuten LN": "#c084fc"
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
        "responsive:true,"
        "maintainAspectRatio:false,"
        "interaction:{mode:'index',intersect:false},"
        "layout:{padding:{top:18,bottom:12,left:6,right:10}},"
        "elements:{bar:{borderRadius:8,borderSkipped:false}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'rectRounded',boxWidth:10,color:'#667085',font:{size:13,weight:'700'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:true,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:12,weight:'700'}}"
        "},"
        "y:{"
        "min:-6,"
        "max:6,"
        "ticks:{stepSize:1,color:'#98a2b3',font:{size:12,weight:'700'},callback:function(v){return (v>0?'+':'')+v.toFixed(0)+'%';}},"
        "title:{display:true,text:'Performance (%)',color:'#667085',font:{size:12,weight:'700'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false}"
        "}"
        "}"
        "}"
    )

    # ---------- BAR WIDE（±10% 固定・2%刻み） ----------
    AXIS_BAR_WIDE = (
        "options:{"
        "responsive:true,"
        "maintainAspectRatio:false,"
        "interaction:{mode:'index',intersect:false},"
        "layout:{padding:{top:18,bottom:12,left:6,right:10}},"
        "elements:{bar:{borderRadius:8,borderSkipped:false}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'rectRounded',boxWidth:10,color:'#667085',font:{size:13,weight:'700'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:true,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:12,weight:'700'}}"
        "},"
        "y:{"
        "min:-10,"
        "max:10,"
        "ticks:{stepSize:2,color:'#98a2b3',font:{size:12,weight:'700'},callback:function(v){return (v>0?'+':'')+v.toFixed(0)+'%';}},"
        "title:{display:true,text:'Performance (%)',color:'#667085',font:{size:12,weight:'700'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false}"
        "}"
        "}"
        "}"
    )


    # ---------- LINE（Auto・Edge FIX） ----------
    AXIS_LINE = (
        "options:{"
        "responsive:true,"
        "maintainAspectRatio:false,"
        "interaction:{mode:'index',intersect:false},"
        "layout:{padding:{top:18,bottom:12,left:6,right:10}},"
        "elements:{line:{tension:0.28,borderWidth:3},point:{radius:0,hoverRadius:5,hitRadius:12}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'circle',boxWidth:10,color:'#667085',font:{size:13,weight:'700'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:false,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:12,weight:'700'}}"
        "},"
        "y:{"
        "title:{display:true,text:'Cumulative (%)',color:'#667085',font:{size:12,weight:'700'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false},"
        "ticks:{color:'#98a2b3',font:{size:12,weight:'700'},callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}}"
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
                --bg-main:#eef3f9;
                --bg-accent:#f7faff;
                --card-bg:rgba(255,255,255,0.88);

                --text-main:#344054;
                --text-sub:#667085;
                --text-soft:#98a2b3;

                --border:#e6ebf2;
                --border-strong:#d7dee8;

                --accent-pos:#67c6ff;
                --accent-neg:#ff8fb1;

                --shadow-sm:0 8px 20px rgba(16,24,40,.05);
                --shadow-md:0 18px 36px rgba(16,24,40,.08);
            }

            * { box-sizing:border-box; }

            body {
                background:
                    radial-gradient(circle at top left, rgba(103,198,255,.16), transparent 24%),
                    radial-gradient(circle at top right, rgba(192,132,252,.10), transparent 18%),
                    linear-gradient(180deg, var(--bg-accent) 0%, var(--bg-main) 100%);
                font-family:"Inter","Avenir Next","Segoe UI","SF Pro Display","SF Pro Text",-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;
                padding:24px;
                color:var(--text-main);
                font-size:17px;
                line-height:1.68;
                letter-spacing:0.005em;
                -webkit-font-smoothing:antialiased;
                -moz-osx-font-smoothing:grayscale;
                text-rendering:optimizeLegibility;
            }

            .card {
                background:var(--card-bg);
                padding:24px 24px 22px 24px;
                border-radius:24px;
                margin-bottom:26px;
                border:1px solid rgba(255,255,255,.65);
                box-shadow:var(--shadow-md);
                backdrop-filter:blur(10px);
                -webkit-backdrop-filter:blur(10px);
            }

            h2 {
                font-size:22px;
                margin-bottom:16px;
                font-weight:750;
                color:var(--text-main);
                letter-spacing:-0.02em;
            }

            h3 {
                font-size:17px;
                font-weight:720;
                color:var(--text-main);
                letter-spacing:-0.015em;
            }

            table {
                width:100%;
                border-collapse:separate;
                border-spacing:0;
                font-variant-numeric:tabular-nums;
            }

            th, td {
                padding:14px 12px;
                border-bottom:1px solid var(--border);
                font-size:15px;
                line-height:1.55;
                text-align:right;
                color:var(--text-main);
            }

            th {
                font-weight:700;
                font-size:12px;
                letter-spacing:0.07em;
                text-transform:uppercase;
                color:var(--text-soft);
            }

            td { font-weight:580; }

            tr:hover td {
                background:rgba(103,198,255,.035);
            }

            th:first-child,
            td:first-child { text-align:left; }

            .chart-container {
                width:100%;
                height:420px;
                margin-top:8px;
                padding:14px 12px 8px 12px;
                border-radius:18px;
                background:linear-gradient(180deg, rgba(255,255,255,.82) 0%, rgba(248,250,252,.92) 100%);
                border:1px solid var(--border);
                box-shadow:var(--shadow-sm) inset;
            }

            .chart-container canvas {
                width:100% !important;
                height:100% !important;
            }

            summary {
                cursor:pointer;
                font-size:18px;
                font-weight:720;
                color:var(--text-main);
                list-style:none;
                letter-spacing:-0.015em;
            }

            summary::-webkit-details-marker {
                display:none;
            }

            .highlight {
                font-weight:720;
                color:var(--text-main);
            }

            .section-title {
                position:relative;
                padding-left:16px;
                font-size:22px;
                font-weight:750;
                color:var(--text-main);
                letter-spacing:-0.02em;
            }

            .section-title::before {
                content:"";
                position:absolute;
                left:0;
                top:0.18em;
                width:5px;
                height:1.15em;
                border-radius:999px;
                background:linear-gradient(180deg, #67c6ff 0%, #8b9dff 100%);
                box-shadow:0 0 0 1px rgba(103,198,255,.14);
            }

            /* ✅Update History 用（inline style 排除） */
            .history-item { margin-top:16px; }
            .history-title { font-weight:720; color:var(--text-main); letter-spacing:-0.01em; }
            .history-summary { color:var(--text-sub); font-size:15px; margin-top:4px; }

            /* ✅ +/- coloring */
            .pos { color: var(--accent-pos); font-weight: 760; }
            .neg { color: var(--accent-neg); font-weight: 760; }

            /* ✅ key metrics (iDeCo) */
            .key-metric { font-size: 18px; font-weight: 820; color: var(--text-main); letter-spacing:-0.015em; }
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

    html += chart(f"Weekly Performance ({YEAR})", "w1", weekly_labels, bar_ds(weekly), AXIS_BAR_WIDE)
    html += chart(f"Weekly Cumulative ({YEAR})", "w2", weekly_labels_cum, line_ds(cum_weekly), AXIS_LINE)

    html += chart(f"Monthly Performance ({MONTHLY_YEAR_LABEL})", "m1", monthly_labels, bar_ds(monthly), AXIS_BAR_WIDE)
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
