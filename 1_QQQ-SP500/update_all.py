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

plt.rcParams.update({
    "figure.facecolor": "none",
    "axes.facecolor": "#0f172a",
    "axes.edgecolor": "#334155",
    "axes.labelcolor": "#cbd5e1",
    "axes.titlecolor": "#f8fafc",
    "xtick.color": "#94a3b8",
    "ytick.color": "#94a3b8",
    "grid.color": "#334155",
    "text.color": "#e2e8f0",
    "legend.facecolor": "#0f172a",
    "legend.edgecolor": "#334155",
    "legend.framealpha": 0.92,
    "savefig.facecolor": "none",
    "savefig.edgecolor": "none"
})

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
    fig.savefig(
        buf,
        format="png",
        bbox_inches="tight",
        dpi=140,
        transparent=True,
        facecolor=fig.get_facecolor()
    )
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

    qqq_raw = yf.download(
        "QQQ",
        start="2000-01-01",
        auto_adjust=False,
        progress=False
    )
    spy_raw = yf.download(
        "SPY",
        start="2000-01-01",
        auto_adjust=False,
        progress=False
    )

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
        df = yf.download(
            tic,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False
        ).dropna()

        last_ser = df["Close"].iloc[-1]
        last = float(last_ser.iloc[0]) if hasattr(last_ser, "iloc") else float(last_ser)

        if len(df) >= 2:
            prev_ser = df["Close"].iloc[-2]
            prev = float(prev_ser.iloc[0]) if hasattr(prev_ser, "iloc") else float(prev_ser)
            diff = last - prev
            diffp = diff / prev * 100
        else:
            diff = diffp = 0.0

        out[key] = {
            "last": float(last),
            "diff": float(diff),
            "diffp": float(diffp)
        }
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
:root {
    --bg-1: #07111f;
    --bg-2: #0d1a2b;
    --bg-3: #14243b;
    --card: linear-gradient(180deg, rgba(12, 22, 38, 0.90) 0%, rgba(10, 18, 32, 0.82) 100%);
    --card-border: rgba(255, 255, 255, 0.08);
    --panel-bg: rgba(255, 255, 255, 0.035);
    --panel-border: rgba(255, 255, 255, 0.06);
    --text-main: #eef4ff;
    --text-sub: #9fb0ca;
    --accent: #6ea8fe;
    --accent-2: #8ef0d2;
    --shadow: 0 18px 46px rgba(0, 0, 0, 0.34);
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 28px;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
    background:
        radial-gradient(circle at top left, rgba(63, 131, 248, 0.22), transparent 24%),
        radial-gradient(circle at 85% 10%, rgba(45, 212, 191, 0.10), transparent 18%),
        linear-gradient(135deg, var(--bg-1) 0%, var(--bg-2) 52%, var(--bg-3) 100%);
    color: var(--text-main);
}

.card {
    background: var(--card);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border-radius: 26px;
    padding: 26px 26px 24px 26px;
    margin-bottom: 24px;
    border: 1px solid var(--card-border);
    box-shadow: var(--shadow);
}

h1 {
    font-size: 32px;
    line-height: 1.1;
    margin: 0 0 24px 0;
    letter-spacing: 0.01em;
    font-weight: 800;
    color: #f8fbff;
}

h2 {
    font-size: 17px;
    line-height: 1.35;
    margin: 0 0 16px 0;
    color: #f8fbff;
    font-weight: 750;
}

.section {
    display: flex;
    gap: 18px;
    align-items: stretch;
    flex-wrap: wrap;
}

.imghalf {
    width: calc(50% - 9px);
    min-width: 320px;
    border-radius: 18px;
    overflow: hidden;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    padding: 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
}

img {
    display: block;
    width: 100%;
    height: auto;
}

@media (max-width: 900px) {
    body {
        padding: 18px;
    }

    .card {
        padding: 18px;
        border-radius: 20px;
    }

    .imghalf {
        width: 100%;
        min-width: 0;
    }
}
"""


def style_ticks(ax):
    ax.set_facecolor("#0f172a")
    ax.tick_params(labelsize=8, colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_color("#334155")
        spine.set_linewidth(1.1)
    ax.grid(color="#334155", linewidth=0.8, alpha=0.55)
    ax.set_axisbelow(True)


# =========================================
#  β / R² 時系列
# =========================================
def plot_beta_r2_20years(beta_list, r2_list, years20):
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    x = np.arange(len(years20))

    ax.plot(
        x, beta_list,
        color="#2f76ff", marker="o", markersize=7, linewidth=2.8,
        label="Beta vs SP500"
    )
    ax.plot(
        x, r2_list,
        color="#ff3b30", marker="o", markersize=7, linewidth=2.8,
        label="R²"
    )

    ax.fill_between(x, beta_list, 0, color="#2f76ff", alpha=0.08)
    ax.fill_between(x, r2_list, 0, color="#ff3b30", alpha=0.06)

    ax.set_xticks(x)
    ax.set_xticklabels(years20, rotation=45, ha="right", fontsize=8)

    ax.set_ylim(0, 1.6)
    ax.set_yticks(np.arange(0, 1.61, 0.2))

    style_ticks(ax)
    ax.set_title("Beta / R² Trend (Last 20 Years)", fontsize=14, pad=12, fontweight="bold")
    ax.set_xlabel("Year", fontsize=10, labelpad=8)
    ax.set_ylabel("Value", fontsize=10, labelpad=8)
    ax.legend(
        loc="upper left",
        fontsize=9,
        frameon=True,
        borderpad=0.6,
        labelspacing=0.45
    )

    fig.tight_layout(pad=1.1)
    return fig_to_base64(fig)


# =========================================
#  Correlation Scatter
# =========================================
def plot_correlation(x, y, label):
    fig, ax = plt.subplots(figsize=(4.3, 4.1))

    # =========================
    # Guard: empty / insufficient data
    # =========================
    if x is None or y is None or len(x) < 2 or len(y) < 2:
        ax.set_xlim(-15, 15)
        ax.set_ylim(-15, 15)
        style_ticks(ax)
        ax.set_title(f"{label} Correlation\nN/A", fontsize=12, pad=10, fontweight="bold")
        ax.set_xlabel("SP500 Monthly Return (%)", fontsize=10, labelpad=8)
        ax.set_ylabel("QQQ Monthly Return (%)", fontsize=10, labelpad=8)
        ax.text(
            0.5, 0.5, "No sufficient data",
            ha="center", va="center",
            transform=ax.transAxes,
            fontsize=10, color="#94a3b8"
        )
        fig.tight_layout(pad=1.1)
        return fig_to_base64(fig)

    slope, intercept = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0,1] ** 2

    ax.scatter(
        x * 100, y * 100,
        s=28, color="#74b3ff", alpha=0.72,
        edgecolors="#dbeafe", linewidths=0.5
    )
    xr = np.array([-15, 15])
    yr = slope * (xr / 100) * 100 + intercept * 100
    ax.plot(xr, yr, color="#ff5a5f", linewidth=2.3)

    ax.set_xlim(-15, 15)
    ax.set_ylim(-15, 15)
    style_ticks(ax)
    ax.set_title(f"{label} Correlation\nβ={slope:.3f}, R²={r2:.3f}", fontsize=12, pad=10, fontweight="bold")
    ax.set_xlabel("SP500 Monthly Return (%)", fontsize=10, labelpad=8)
    ax.set_ylabel("QQQ Monthly Return (%)", fontsize=10, labelpad=8)

    fig.tight_layout(pad=1.1)
    return fig_to_base64(fig)

# =========================================
#  Monthly plot
# =========================================
def plot_monthly(sp_arr, q_arr, title1, title2, ylimit, is_overall=False):
    fig, ax = plt.subplots(figsize=(4.5, 4.1))

    x = np.arange(1, 13)
    diff = (q_arr - sp_arr) * 100

    ax.bar(x - 0.19, sp_arr * 100, width=0.34, color="#f59ac2", alpha=0.92, label="SP500")
    ax.bar(x + 0.19, q_arr * 100, width=0.34, color="#7db8ff", alpha=0.92, label="QQQ")
    ax.plot(x, diff, color="#ff5a5f", marker="o", markersize=4.2, linewidth=2.1, label="QQQ - SP500")

    if is_overall:
        ax.set_ylim(-5, 5)
        ax.set_yticks(np.arange(-5, 6, 1))
    else:
        ax.set_ylim(-ylimit * 100, ylimit * 100)
        ax.set_yticks(np.arange(-ylimit * 100, ylimit * 100 + 1, 5))

    ax.set_xlim(0.5, 12.5)
    ax.set_xticks(np.arange(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])

    style_ticks(ax)
    ax.set_xlabel("Month", fontsize=10, labelpad=8)
    ax.set_ylabel("Return (%)", fontsize=10, labelpad=8)

    if title2:
        ax.set_title(f"{title1}\n{title2}", fontsize=11, pad=10, fontweight="bold")
    else:
        ax.set_title(title1, fontsize=11, pad=10, fontweight="bold")

    ax.legend(
        loc="upper left",
        fontsize=8.5,
        frameon=True,
        borderpad=0.5,
        handlelength=1.8,
        labelspacing=0.45
    )
    fig.tight_layout(pad=1.1)
    return fig_to_base64(fig)


# =========================================
#  Annual Summary
# =========================================
def plot_annual_summary(ann_q, ann_s, years20):
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    years = years20
    x = np.arange(len(years))

    aq = np.array([ann_q[y] * 100 for y in years])
    asv = np.array([ann_s[y] * 100 for y in years])
    diff = aq - asv

    ax.bar(x - 0.18, asv, width=0.34, color="#f472b6", alpha=0.88, label="SP500")
    ax.bar(x + 0.18, aq, width=0.34, color="#60a5fa", alpha=0.88, label="QQQ")
    ax.plot(x, diff, color="#f87171", marker="o", markersize=4, linewidth=2.0, label="QQQ - SP500")

    ax.set_ylim(-60, 60)
    ax.set_yticks(np.arange(-60, 61, 10))
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, ha="right")

    style_ticks(ax)
    ax.set_title("Annual Return Summary (20 years)", fontsize=13, pad=12)
    ax.set_xlabel("Year", fontsize=10, labelpad=8)
    ax.set_ylabel("Return (%)", fontsize=10, labelpad=8)
    ax.legend(loc="upper left", fontsize=8, frameon=True)

    fig.tight_layout()
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

    monthly_all = df.resample("ME").last().pct_change().dropna()
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

        monthly_y = df[df.index.year == y].resample("ME").last().pct_change().dropna()
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
.indexwrap {{ max-width:1080px; margin:0 auto; }}
.indexcard {{
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.78) 0%, rgba(17, 24, 39, 0.70) 100%);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border-radius: 26px;
    padding: 28px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.32);
    border: 1px solid rgba(255,255,255,0.10);
    margin-bottom: 34px;
}}
.index_title {{
    font-size: 30px;
    font-weight: 800;
    margin-bottom: 10px;
    letter-spacing: 0.02em;
    color: #f8fafc;
}}
.timestamp {{
    font-size: 14px;
    color: #94a3b8;
    margin: 0 0 24px 0;
}}
.section_header {{
    font-size: 13px;
    font-weight: 700;
    color: #cbd5e1;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    margin: 26px 0 12px 2px;
}}
.index_list {{
    border-radius: 18px;
    overflow: hidden;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(10px);
}}
.index_row {{
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding:16px 18px;
    font-size:16px;
    border-bottom:1px solid rgba(255,255,255,0.08);
    transition: background 0.18s ease, transform 0.18s ease;
}}
.index_row:hover {{
    background: rgba(255,255,255,0.05);
}}
.index_row:last-child {{ border-bottom:none; }}
.index_row_left {{ display:flex; align-items:center; gap:12px; }}
.index_row_icon {{
    font-size:18px;
    width:34px;
    height:34px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border-radius:10px;
    background: rgba(255,255,255,0.07);
    text-align:center;
}}
.index_row_arrow {{ font-size:18px; color:#94a3b8; }}
.index_row a {{ text-decoration:none; color:#e5edf9; font-weight:600; }}

.index_row_disabled {{ opacity:0.45; pointer-events:none; }}

.market_val_up {{ color:#86efac; font-weight:700; }}
.market_val_down {{ color:#fca5a5; font-weight:700; }}
.market_val_flat {{ color:#cbd5e1; font-weight:700; }}
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

    monthly_raw = df.resample("ME").last().pct_change()
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
                arr_sp[m-1] = float(row["SP500"].iloc[0])
                arr_qq[m-1] = float(row["QQQ"].iloc[0])
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
