#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import yfinance as yf
from datetime import datetime, timedelta

# =========================================
#  BASE_DIR
# =========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_ANNUAL = os.path.join(BASE_DIR, "annual_returns.csv")
CSV_MONTHLY = os.path.join(BASE_DIR, "monthly_returns.csv")
HTML_REPORT = os.path.join(BASE_DIR, "analysis_report.html")
HTML_INDEX = os.path.join(BASE_DIR, "index.html")
MANIFEST = os.path.join(BASE_DIR, "manifest.json")
SW_JS = os.path.join(BASE_DIR, "sw.js")

# =========================================
#  PWA Files
# =========================================
def write_manifest():
    content = """{
  "name": "Finance Report",
  "short_name": "Finance",
  "start_url": "./index.html",
  "display": "standalone",
  "background_color": "#d7d7d7",
  "theme_color": "#d7d7d7",
  "icons": [
    { "src": "icon.png", "sizes": "512x512", "type": "image/png" }
  ]
}
"""
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(content)


def write_sw():
    content = """self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => clients.claim());
self.addEventListener('fetch', event => {
  event.respondWith(fetch(event.request, { cache: "no-store" }));
});
"""
    with open(SW_JS, "w", encoding="utf-8") as f:
        f.write(content)


# =========================================
#  matplotlib base64
# =========================================
def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# =========================================
#  Yahoo Finance helper
# =========================================
def safe_close_multi(df_raw, name):
    if isinstance(df_raw.columns, pd.MultiIndex):
        for price, ticker in df_raw.columns:
            if str(price).lower() in ("close", "adj close"):
                return df_raw[(price, ticker)]
    for c in df_raw.columns:
        if str(c).lower() in ("close", "adj close"):
            return df_raw[c]
    raise ValueError(f"{name}: no price columns")


# =========================================
#  Load Market Data (QQQ / SP500)
# =========================================
def load_data():
    print("Downloading data QQQ / SPY …")

    qqq_raw = yf.download("QQQ", start="2000-01-01", progress=False)
    spy_raw = yf.download("SPY", start="2000-01-01", progress=False)

    qqq_close = safe_close_multi(qqq_raw, "QQQ")
    spy_close = safe_close_multi(spy_raw, "SP500")

    df = pd.DataFrame({"QQQ": qqq_close, "SP500": spy_close})
    df.index = pd.to_datetime(df.index)
    return df.dropna().sort_index()


# =========================================
#  Load US Market (today)
# =========================================
def load_us_market():
    tickers = {
        "SP500": "^GSPC",
        "NDX": "^NDX",
        "USDJPY": "JPY=X"
    }

    out = {}
    for key, tic in tickers.items():
        df = yf.download(tic, period="5d", interval="1d", progress=False).dropna()
        last = df["Close"].iloc[-1]
        if len(df) >= 2:
            prev = df["Close"].iloc[-2]
            diff = last - prev
            diffp = diff / prev * 100
        else:
            diff = diffp = 0

        out[key] = {"last": float(last), "diff": float(diff), "diffp": float(diffp)}
    return out


# =========================================
#  Annual Return
# =========================================
def compute_annual(df):
    out_q, out_s = {}, {}
    years = sorted(set(df.index.year))

    for y in years:
        d = df[df.index.year == y]
        first_q = d["QQQ"].iloc[0]
        first_s = d["SP500"].iloc[0]

        d12 = d[d.index.month == 12]
        if len(d12):
            last_q = d12["QQQ"].iloc[-1]
            last_s = d12["SP500"].iloc[-1]
        else:
            last_q = d["QQQ"].iloc[-1]
            last_s = d["SP500"].iloc[-1]

        out_q[y] = last_q / first_q - 1
        out_s[y] = last_s / first_s - 1

    return out_q, out_s


# =========================================
#  Compute Beta / R²
# =========================================
def compute_beta_alpha_r2(df, years20):
    beta_list = []
    alpha_list = []
    r2_list = []

    for y in years20:
        year_df = df[df.index.year == y].pct_change().dropna()
        if len(year_df) < 5:
            beta_list.append(0)
            alpha_list.append(0)
            r2_list.append(0)
            continue

        x = year_df["SP500"].values
        yv = year_df["QQQ"].values

        slope, intercept = np.polyfit(x, yv, 1)
        r2 = np.corrcoef(x, yv)[0, 1] ** 2

        beta_list.append(slope)
        alpha_list.append(intercept)
        r2_list.append(r2)

    return beta_list, alpha_list, r2_list


# =========================================
#  CSS
# =========================================
METAL_CSS = """
body {
    margin: 0;
    padding: 28px;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial;
    background: linear-gradient(to bottom,#d7d7d7 0%,#cfcfcf 40%,#c5c5c5 55%,#dcdcdc 100%),
                repeating-linear-gradient(to right,rgba(255,255,255,0.20) 0px,
                rgba(255,255,255,0.20) 2px,rgba(0,0,0,0.10) 4px,rgba(0,0,0,0.10) 6px);
    background-blend-mode: overlay;
    background-size: 100% 100%, 6px 100%;
    color: #222;
}
.card {
    background: rgba(255,255,255,0.28);
    backdrop-filter: blur(10px);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 28px;
    border: 1px solid rgba(255,255,255,0.55);
    box-shadow: 0 1px 3px rgba(255,255,255,0.6) inset,
                0 4px 14px rgba(0,0,0,0.28);
}
h1 { font-size: 22px; margin-bottom:18px; }
.section { display:flex; gap:18px; }
.imghalf { width:48%; border-radius:10px; overflow:hidden; }
"""


def style_ticks(ax):
    ax.tick_params(labelsize=7, colors="#444")
    for spine in ax.spines.values():
        spine.set_color("#bbbbbb")
    ax.grid(color="#dddddd", linewidth=0.6)


# =========================================
#  β / R² 時系列
# =========================================
def plot_beta_r2_20years(beta_list, r2_list, years20):
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    x = np.arange(len(years20))

    ax.plot(x, beta_list, color="#4a90e2", marker="o", markersize=6, linewidth=1.8, label="Beta")
    ax.plot(x, r2_list,   color="#d43f3a", marker="o", markersize=6, linewidth=1.8, label="R²")

    ax.set_xticks(x)
    ax.set_xticklabels(years20, rotation=45, fontsize=7)

    ax.set_ylim(0, 1.6)
    ax.set_yticks(np.arange(0, 1.61, 0.2))

    style_ticks(ax)
    ax.set_title("Beta / R² (20 years)", fontsize=10)
    ax.legend(fontsize=8)

    return fig_to_base64(fig)


# =========================================
#  Correlation Scatter
# =========================================
def plot_correlation(x, y, label):
    fig, ax = plt.subplots(figsize=(3.4,3.4))
    slope, intercept = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0,1] ** 2

    ax.scatter(x*100, y*100, s=10, color="#7bb0ff", alpha=0.6)
    xr = np.array([-15, 15])
    yr = slope*(xr/100)*100 + intercept*100
    ax.plot(xr, yr, color="#d43f3a", linewidth=1.2)

    ax.set_xlim(-15,15)
    ax.set_ylim(-15,15)
    style_ticks(ax)
    ax.set_title(f"{label}\nβ={slope:.3f}, R²={r2:.3f}", fontsize=7)

    return fig_to_base64(fig)


# =========================================
#  Monthly plot
# =========================================
def plot_monthly(sp_arr, q_arr, title1, title2, ylimit, is_overall=False):
    fig, ax = plt.subplots(figsize=(3.4,3.4))

    x = np.arange(1,13)
    diff = (q_arr - sp_arr)*100

    ax.bar(x-0.2, sp_arr*100, width=0.4, color="#ffb3cc")
    ax.bar(x+0.2, q_arr*100, width=0.4, color="#bcdfff")
    ax.plot(x, diff, color="#d43f3a", marker="o", markersize=3, linewidth=1.2)

    if is_overall:
        ax.set_ylim(-5,5)
        ax.set_yticks(np.arange(-5,6,1))
    else:
        ax.set_ylim(-ylimit*100, ylimit*100)
        ax.set_yticks(np.arange(-ylimit*100, ylimit*100+1, 5))

    ax.set_xlim(0.5,12.5)
    ax.set_xticks(np.arange(1,13))

    style_ticks(ax)

    if title2:
        ax.set_title(f"{title1}\n{title2}", fontsize=7)
    else:
        ax.set_title(title1, fontsize=7)

    return fig_to_base64(fig)


# =========================================
#  Annual Summary
# =========================================
def plot_annual_summary(ann_q, ann_s, years20):
    fig, ax = plt.subplots(figsize=(5.2,3.2))
    years = years20
    x = np.arange(len(years))

    aq = np.array([ann_q[y]*100 for y in years])
    asv = np.array([ann_s[y]*100 for y in years])
    diff = aq - asv

    ax.bar(x-0.15, asv, width=0.3, color="#ffb3cc", label="SP500")
    ax.bar(x+0.15, aq, width=0.3, color="#bcdfff", label="QQQ")
    ax.plot(x, diff, color="#d43f3a", marker="o", markersize=3, linewidth=1.2, label="Diff")

    ax.set_ylim(-60,60)
    ax.set_yticks(np.arange(-60,61,10))
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45)

    style_ticks(ax)
    ax.set_title("Annual Return Summary (20 years)", fontsize=8)
    ax.legend(fontsize=6)

    return fig_to_base64(fig)


# =========================================
#  analysis_report.html
# =========================================
def build_analysis_html(df, monthly_map, ann_q, ann_s, years20, beta_list, r2_list):

    html = []
    html.append("<html><head><meta charset='utf-8'><style>")
    html.append(METAL_CSS)
    html.append("</style></head><body>")
    html.append("<h1>Finance Report</h1>")

    monthly_all = df.resample("M").last().pct_change().dropna()
    corr_overall = plot_correlation(
        monthly_all["SP500"].values,
        monthly_all["QQQ"].values,
        "Overall (20 years)"
    )

    sp_all = np.array([monthly_map[y]["SP500"] for y in years20])
    q_all = np.array([monthly_map[y]["QQQ"] for y in years20])
    sp_mean = sp_all.mean(axis=0)
    q_mean = q_all.mean(axis=0)

    overall_month = plot_monthly(
        sp_mean, q_mean,
        "Overall (20 years)\nMonthly Mean",
        "",
        ylimit=0.05,
        is_overall=True
    )

    html.append(f"""
<div class="card">
<h2>Overall (20 years)</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_overall}">
  <img class="imghalf" src="data:image/png;base64,{overall_month}">
</div>
</div>
""")

    bar_img = plot_beta_r2_20years(beta_list, r2_list, years20)
    html.append(f"""
<div class="card">
<h2>Beta / R² (20 years)</h2>
<img style="width:100%;" src="data:image/png;base64,{bar_img}">
</div>
""")

    ann_img = plot_annual_summary(ann_q, ann_s, years20)
    html.append(f"""
<div class="card">
<h2>Annual Return Summary (20 years)</h2>
<img style="width:100%;" src="data:image/png;base64,{ann_img}">
</div>
""")

    for y in reversed(years20):
        sp_arr = monthly_map[y]["SP500"]
        q_arr = monthly_map[y]["QQQ"]

        aq = ann_q[y]*100
        asv = ann_s[y]*100
        diff = aq - asv

        monthly_y = df[df.index.year == y].resample("M").last().pct_change().dropna()
        corr_y = plot_correlation(
            monthly_y["SP500"].values,
            monthly_y["QQQ"].values,
            str(y)
        )

        t1 = f"{y} Monthly"
        t2 = f"SP500 {asv:+.1f}% / QQQ {aq:+.1f}% / Diff {diff:+.1f}%"

        bar_y = plot_monthly(sp_arr, q_arr, t1, t2, ylimit=0.15)

        html.append(f"""
<div class="card">
<h2>{y}</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_y}">
  <img class="imghalf" src="data:image/png;base64,{bar_y}">
</div>
</div>
""")

    html.append("</body></html>")

    with open(HTML_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(html))


# =========================================
#  index.html
# =========================================
def build_index_html(timestamp_str, us_market):

    sp = us_market["SP500"]
    nd = us_market["NDX"]
    uj = us_market["USDJPY"]

    def fmt(v): return f"{v:,.2f}"
    def pm(v): return f"{v:+.2f}"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Finance Dashboard</title>

<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
<meta http-equiv="Pragma" content="no-cache" />
<meta http-equiv="Expires" content="0" />
<link rel="manifest" href="manifest.json">

<style>
{METAL_CSS}
.indexwrap {{ max-width:900px; margin:0 auto; }}
.indexcard {{
    background:rgba(255,255,255,0.32);
    backdrop-filter:blur(18px);
    border-radius:20px;
    padding:24px 26px;
    box-shadow:0 2px 6px rgba(0,0,0,0.12),0 10px 25px rgba(0,0,0,0.10);
    border:1px solid rgba(255,255,255,0.45);
    margin-bottom:34px;
}}
.index_title {{
    font-size:22px; font-weight:700; margin-bottom:22px;
}}
.timestamp {{
    font-size:15px; color:#666; margin:0 0 22px 0;
}}
.section_header {{
    font-size:14px; font-weight:600; color:#888; margin:22px 0 10px 2px;
}}
.index_list {{
    border-radius:14px; overflow:hidden;
    background:rgba(255,255,255,0.35);
    border:1px solid rgba(255,255,255,0.5);
    backdrop-filter:blur(14px);
}}
.index_row {{
    display:flex; align-items:center; justify-content:space-between;
    padding:14px 18px; font-size:16px;
    border-bottom:1px solid rgba(255,255,255,0.55);
}}
.index_row:last-child {{ border-bottom:none; }}
.index_row_left {{ display:flex; align-items:center; gap:10px; }}
.index_row_icon {{ font-size:20px; width:22px; text-align:center; }}
.index_row_arrow {{ font-size:18px; color:#888; }}
.index_row a {{ text-decoration:none; color:#222; }}

.index_row_disabled {{ opacity:0.45; pointer-events:none; }}

.market_val_up {{ color:#008000; font-weight:600; }}
.market_val_down {{ color:#b00000; font-weight:600; }}
.market_val_flat {{ color:#444; font-weight:600; }}
</style>
</head>

<body>
<div class="indexwrap">

<div class="indexcard">
    <div class="index_title">Finance Dashboard</div>
    <div class="timestamp">Last Updated: {timestamp_str}</div>

    <div class="section_header">US Market Today</div>
    <div class="index_list">

        <div class="index_row">
            <div class="index_row_left"><span class="index_row_icon">🇺🇸</span><span>S&P 500</span></div>
            <span class="market_val_{'up' if sp['diff']>0 else 'down' if sp['diff']<0 else 'flat'}">
                {fmt(sp['last'])} ({pm(sp['diffp'])}%)
            </span>
        </div>

        <div class="index_row">
            <div class="index_row_left"><span class="index_row_icon">💹</span><span>NASDAQ 100</span></div>
            <span class="market_val_{'up' if nd['diff']>0 else 'down' if nd['diff']<0 else 'flat'}">
                {fmt(nd['last'])} ({pm(nd['diffp'])}%)
            </span>
        </div>

        <div class="index_row">
            <div class="index_row_left"><span class="index_row_icon">💱</span><span>USD / JPY</span></div>
            <span class="market_val_{'up' if uj['diff']>0 else 'down' if uj['diff']<0 else 'flat'}">
                {fmt(uj['last'])}
            </span>
        </div>

    </div>

    <div class="section_header">Reports</div>
    <div class="index_list">

        <div class="index_row">
            <div class="index_row_left"><span class="index_row_icon">📈</span>
                <a href="analysis_report.html">Analysis Report</a>
            </div>
            <span class="index_row_arrow">›</span>
        </div>

        <div class="index_row index_row_disabled">
            <div class="index_row_left"><span class="index_row_icon">📊</span>
                <span>US Market Details (coming)</span>
            </div>
            <span class="index_row_arrow">›</span>
        </div>

        <div class="index_row index_row_disabled">
            <div class="index_row_left"><span class="index_row_icon">💰</span>
                <span>Rakuten Data (coming)</span>
            </div>
            <span class="index_row_arrow">›</span>
        </div>

    </div>

</div>

</div>

<script>
if ("serviceWorker" in navigator) {{
    navigator.serviceWorker.register("sw.js");
}}
</script>

</body>
</html>
"""

    with open(HTML_INDEX, "w", encoding="utf-8") as f:
        f.write(html)


# =========================================
#  MAIN
# =========================================
if __name__ == "__main__":

    df = load_data()
    us_market = load_us_market()

    monthly_raw = df.resample("M").last().pct_change()
    monthly_map = {}
    years = sorted(set(monthly_raw.index.year))
    years20 = years[-20:]

    for y in years:
        mm = monthly_raw[monthly_raw.index.year == y]
        arr_sp = np.zeros(12)
        arr_qq = np.zeros(12)

        for m in range(1, 13):
            row = mm[mm.index.month == m]
            if len(row) == 1:
                arr_sp[m-1] = float(row["SP500"])
                arr_qq[m-1] = float(row["QQQ"])
            else:
                arr_sp[m-1] = arr_qq[m-1] = 0.0

        monthly_map[y] = {"SP500": arr_sp, "QQQ": arr_qq}

    df_month = []
    for y in years:
        df_month.append([y] + list(monthly_map[y]["SP500"]) + list(monthly_map[y]["QQQ"]))

    cols = ["Year"] + [f"SP_m{i}" for i in range(1,13)] + [f"QQQ_m{i}" for i in range(1,13)]
    pd.DataFrame(df_month, columns=cols).to_csv(CSV_MONTHLY, index=False)

    ann_q, ann_s = compute_annual(df)
    df_annual = [[y, ann_s[y], ann_q[y], ann_q[y] - ann_s[y]] for y in sorted(ann_q.keys())]
    pd.DataFrame(df_annual, columns=["Year","SP500","QQQ","Diff"]).to_csv(CSV_ANNUAL, index=False)

    beta_list, alpha_list, r2_list = compute_beta_alpha_r2(df, years20)

    write_manifest()
    write_sw()

    now = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M JST")

    build_analysis_html(df, monthly_map, ann_q, ann_s, years20, beta_list, r2_list)
    build_index_html(now, us_market)

    print("✔ Finance Dashboard updated (with US Market & Beta/R²)")
