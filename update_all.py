#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from datetime import datetime
import pytz
import yfinance as yf

# -------------------------------
# Base directory
# -------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_ANNUAL = os.path.join(BASE_DIR, "annual_returns.csv")
CSV_MONTHLY = os.path.join(BASE_DIR, "monthly_returns.csv")
HTML_REPORT = os.path.join(BASE_DIR, "analysis_report.html")
HTML_INDEX = os.path.join(BASE_DIR, "index.html")


# -------------------------------
# JST timestamp
# -------------------------------
def get_jst_timestamp():
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    return now.strftime("%Y-%m-%d %H:%M JST")


# -------------------------------
# fig → base64
# -------------------------------
def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# -------------------------------
# yfinance MultiIndex safe close
# -------------------------------
def safe_close_multi(df_raw, name):
    if isinstance(df_raw.columns, pd.MultiIndex):
        for p, t in df_raw.columns:
            if str(p).lower() in ("close", "adj close"):
                return df_raw[(p, t)]
        raise ValueError(f"{name}: price not found")

    for c in df_raw.columns:
        if str(c).lower() in ("close", "adj close"):
            return df_raw[c]

    raise ValueError(f"{name}: price not found")


# -------------------------------
# Data Load
# -------------------------------
def load_data():
    print("Downloading QQQ / SPY ...")

    q_raw = yf.download("QQQ", start="2000-01-01", progress=False)
    s_raw = yf.download("SPY", start="2000-01-01", progress=False)

    q_close = safe_close_multi(q_raw, "QQQ")
    s_close = safe_close_multi(s_raw, "SPY")

    df = pd.DataFrame({"QQQ": q_close, "SP500": s_close})
    df.index = pd.to_datetime(df.index)
    df = df.dropna().sort_index()
    return df


# -------------------------------
# Annual
# -------------------------------
def compute_annual(df):
    out_q = {}
    out_s = {}
    years = sorted(set(df.index.year))

    for y in years:
        d = df[df.index.year == y]
        fq = d["QQQ"].iloc[0]
        fs = d["SP500"].iloc[0]

        d12 = d[d.index.month == 12]
        if len(d12) > 0:
            lq = d12["QQQ"].iloc[-1]
            ls = d12["SP500"].iloc[-1]
        else:
            lq = d["QQQ"].iloc[-1]
            ls = d["SP500"].iloc[-1]

        out_q[y] = lq / fq - 1
        out_s[y] = ls / fs - 1

    return out_q, out_s


# -------------------------------
# Apple-style CSS
# -------------------------------
METAL_CSS = """
body {
    margin: 0;
    padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial;

    background: linear-gradient(
        to bottom,
        #d7d7d7 0%,
        #cfcfcf 40%,
        #c5c5c5 55%,
        #dcdcdc 100%
    ),
    repeating-linear-gradient(
        to right,
        rgba(255,255,255,0.18) 0px,
        rgba(255,255,255,0.18) 2px,
        rgba(0,0,0,0.09) 4px,
        rgba(0,0,0,0.09) 6px
    );
    background-blend-mode: overlay;
    background-size: 100% 100%, 6px 100%;
    color: #333;
}

.card {
    background: rgba(255,255,255,0.28);
    backdrop-filter: blur(10px);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 28px;
    border: 1px solid rgba(255,255,255,0.55);
    box-shadow:
        0 1px 3px rgba(255,255,255,0.6) inset,
        0 4px 14px rgba(0,0,0,0.28);
}

h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px 0; color:#333; }
h2 { font-size: 14px; font-weight: 500; margin: 0 0 10px 0; color:#444; }

.time {
    margin-bottom: 16px;
    font-size: 13px;
    color: #555;
}

.section { display: flex; gap: 18px; justify-content: space-between; }
.imghalf { width: 48%; border-radius: 10px; overflow: hidden; }
img { width: 100%; display: block; }

a {
    display: block;
    padding: 14px;
    margin: 10px 0;
    text-align: center;
    background: linear-gradient(#ffffff 0%, #eeeeee 40%, #d6d6d6 100%);
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.25);
    text-decoration: none;
    color: #333;
}
"""


# -------------------------------
# Apple-style graph decoration
# -------------------------------
def apply_apple_style(ax):
    # スパイン薄灰色
    for s in ax.spines.values():
        s.set_color("#cccccc")
        s.set_linewidth(0.6)

    # 目盛り
    ax.tick_params(colors="#666666", labelsize=7)

    # グリッド
    ax.grid(color="#e6e6e6", linewidth=0.6)

    return ax


# -------------------------------
# Correlation
# -------------------------------
def plot_correlation(x, y, label):
    fig, ax = plt.subplots(figsize=(3.4, 3.4))

    slope, intercept = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0, 1] ** 2

    ax.scatter(x*100, y*100, s=16, color="#8cb7ff", alpha=0.6)

    xr = np.array([-15, 15])
    yr = slope*(xr/100)*100 + intercept*100

    ax.plot(xr, yr, color="#d43f3a", linewidth=1.0)

    ax.set_xlim(-15, 15)
    ax.set_ylim(-15, 15)

    ax.set_xlabel("SP500 Return (%)", fontsize=8, color="#555")
    ax.set_ylabel("QQQ Return (%)", fontsize=8, color="#555")

    apply_apple_style(ax)

    ax.set_title(
        f"{label}\nβ={slope:.3f}, α={intercept:.3f}, R²={r2:.3f}",
        fontsize=9, fontweight='400', color="#333"
    )

    plt.tight_layout(pad=1.4)
    return fig_to_base64(fig)


# -------------------------------
# Monthly (20年)
# -------------------------------
def plot_monthly(sp_arr, q_arr, title1, title2, ylimit):
    fig, ax = plt.subplots(figsize=(3.4, 3.4))

    x = np.arange(1, 13)
    diff = (q_arr - sp_arr) * 100

    ax.bar(x-0.15, sp_arr*100, width=0.3, color="#f7b6c2", label="SP500")
    ax.bar(x+0.15, q_arr*100, width=0.3, color="#bcd7ff", label="QQQ")
    ax.plot(x, diff, color="#d43f3a", linewidth=1.0, marker="o", markersize=3.5, label="Diff")


    # Y 軸固定
    ax.set_ylim(-ylimit, ylimit)

    if ylimit == 5:
        ax.set_yticks(np.arange(-5, 6, 1))
    else:
        ax.set_yticks(np.arange(-15, 16, 5))

    ax.set_xlabel("Month", fontsize=8, color="#555")
    ax.set_ylabel("Return (%)", fontsize=8, color="#555")

    ax.legend(fontsize=6, facecolor="white", edgecolor="#ccc", labelcolor="#555")

    ax.set_xticks(np.arange(1, 13))

    apply_apple_style(ax)

    ax.set_title(f"{title1}\n{title2}", fontsize=9, fontweight='400', color="#333")

    plt.tight_layout(pad=1.4)
    return fig_to_base64(fig)


# -------------------------------
# Annual Summary（20年）
# -------------------------------
def plot_annual_summary(ann_q, ann_s, years):
    fig, ax = plt.subplots(figsize=(5.2, 3.2))

    aq = np.array([ann_q[y]*100 for y in years])
    asv = np.array([ann_s[y]*100 for y in years])
    diff = aq - asv
    x = np.arange(len(years))

    ax.bar(x-0.15, asv, width=0.3, color="#f7b6c2", label="SP500")
    ax.bar(x+0.15, aq, width=0.3, color="#bcd7ff", label="QQQ")
    ax.plot(x, diff, color="#d43f3a", linewidth=1.0, marker="o", markersize=3.5, label="Diff")

    ax.set_xlabel("Year", fontsize=8, color="#555")
    ax.set_ylabel("Return (%)", fontsize=8, color="#555")

    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, color="#555")

    ax.legend(fontsize=6, facecolor="white", edgecolor="#ccc", labelcolor="#555")

    apply_apple_style(ax)

    ax.set_title("Annual Return Summary (20 years)", fontsize=9, fontweight='400', color="#333")

    plt.tight_layout(pad=1.4)
    return fig_to_base64(fig)


# -------------------------------
# analysis_report.html
# -------------------------------
def build_analysis_html(df20, monthly_map20, ann_q20, ann_s20, years20, timestamp):

    # Overall（20年）
    monthly_all = df20.resample("M").last().pct_change().dropna()

    corr_overall_img = plot_correlation(
        monthly_all["SP500"].values,
        monthly_all["QQQ"].values,
        "Overall (20 years)"
    )

    # 月次平均
    sp_all = np.array([monthly_map20[y]["SP500"] for y in years20])
    q_all = np.array([monthly_map20[y]["QQQ"] for y in years20])
    mean_sp = sp_all.mean(axis=0)
    mean_q = q_all.mean(axis=0)

    overall_month_img = plot_monthly(
        mean_sp, mean_q,
        "Overall Monthly Mean (20 years)",
        "",
        ylimit=5
    )

    ann_img = plot_annual_summary(ann_q20, ann_s20, years20)

    html = []
    html.append("<html><head><meta charset='utf-8'><style>")
    html.append(METAL_CSS)
    html.append("</style></head><body>")

    html.append("<h1>Finance Report</h1>")
    html.append(f"<div class='time'>最終更新：{timestamp}</div>")

    # Overall
    html.append(f"""
<div class="card">
<h2>Overall (20 years)</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_overall_img}">
  <img class="imghalf" src="data:image/png;base64,{overall_month_img}">
</div>
</div>
""")

    # Annual
    html.append(f"""
<div class="card">
<h2>Annual Return Summary (20 years)</h2>
<img style="width:100%;" src="data:image/png;base64,{ann_img}">
</div>
""")

    # 年次
    for y in years20[::-1]:
        sp_arr = monthly_map20[y]["SP500"]
        q_arr = monthly_map20[y]["QQQ"]

        aq = ann_q20[y]*100
        asv = ann_s20[y]*100
        diff = aq - asv

        title2 = f"SP500 {asv:+.1f}% / QQQ {aq:+.1f}% / Diff {diff:+.1f}%"

        month_img = plot_monthly(sp_arr, q_arr, f"{y}", title2, ylimit=15)

        monthly_y = df20[df20.index.year == y].resample("M").last().pct_change().dropna()
        if len(monthly_y) > 0:
            corr_img = plot_correlation(
                monthly_y["SP500"].values,
                monthly_y["QQQ"].values,
                f"{y}"
            )
        else:
            corr_img = ""

        html.append(f"""
<div class="card">
<h2>{y}</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_img}">
  <img class="imghalf" src="data:image/png;base64,{month_img}">
</div>
</div>
""")

    html.append("</body></html>")

    with open(HTML_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(html))


# -------------------------------
# index.html
# -------------------------------
def build_index_html(timestamp):
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Finance Dashboard</title>
<style>
{METAL_CSS}
.wrap {{ max-width: 900px; margin: 0 auto; }}
.cardx {{
    background: rgba(255,255,255,0.28);
    backdrop-filter: blur(10px);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 28px;
    border: 1px solid rgba(255,255,255,0.55);
}}
.title {{ font-size: 20px; font-weight:600; margin-bottom:6px; color:#333; }}
</style>
</head>

<body>
<div class="wrap">
<div class="cardx">
    <div class="title">Finance Dashboard</div>
    <div class="time">最終更新：{timestamp}</div>

    <a href="analysis_report.html">📈 Analysis Report</a>
    <a href="us_market.html">📊 US Market (coming soon)</a>
    <a href="rakuten.html">🏦 Rakuten (coming soon)</a>
</div>
</div>
</body>
</html>
"""
    with open(HTML_INDEX, "w", encoding="utf-8") as f:
        f.write(html)


# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    timestamp = get_jst_timestamp()

    df = load_data()

    monthly_raw = df.resample("M").last().pct_change()
    years = sorted(set(monthly_raw.index.year))

    years20 = years[-20:]

    monthly_map20 = {}
    for y in years20:
        mm = monthly_raw[monthly_raw.index.year == y]
        arr_sp = np.zeros(12)
        arr_qq = np.zeros(12)

        for m in range(1, 13):
            row = mm[mm.index.month == m]
            if len(row) == 1:
                arr_sp[m-1] = float(row["SP500"].values[0])
                arr_qq[m-1] = float(row["QQQ"].values[0])
            else:
                arr_sp[m-1] = 0.0
                arr_qq[m-1] = 0.0

        monthly_map20[y] = {"SP500": arr_sp, "QQQ": arr_qq}

    # CSV (monthly)
    df_month = []
    for y in years20:
        sp = monthly_map20[y]["SP500"]
        q = monthly_map20[y]["QQQ"]
        df_month.append([y] + list(sp) + list(q))

    cols = ["Year"] + [f"SP_m{i}" for i in range(1, 13)] + [f"QQQ_m{i}" for i in range(1, 13)]
    pd.DataFrame(df_month, columns=cols).to_csv(CSV_MONTHLY, index=False)

    # annual
    ann_q, ann_s = compute_annual(df)
    ann_q20 = {y: ann_q[y] for y in years20}
    ann_s20 = {y: ann_s[y] for y in years20}

    df_annual = []
    for y in years20:
        df_annual.append([y, ann_s20[y], ann_q20[y], ann_q20[y] - ann_s20[y]])

    pd.DataFrame(df_annual, columns=["Year", "SP500", "QQQ", "Diff"]).to_csv(CSV_ANNUAL, index=False)

    df20 = df[df.index.year.isin(years20)]
    build_analysis_html(df20, monthly_map20, ann_q20, ann_s20, years20, timestamp)

    build_index_html(timestamp)

    print("✔ Finance Dashboard (Apple Edition, 20-year version) updated successfully.")
