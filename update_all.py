#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import yfinance as yf

# =========================================
#  カレントディレクトリを BASE_DIR に設定
# =========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_ANNUAL = os.path.join(BASE_DIR, "annual_returns.csv")
CSV_MONTHLY = os.path.join(BASE_DIR, "monthly_returns.csv")
HTML_REPORT = os.path.join(BASE_DIR, "analysis_report.html")
HTML_INDEX = os.path.join(BASE_DIR, "index.html")

# =========================================
#  matplotlib base64 変換
# =========================================
def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# =========================================
#  ★ yfinance MultiIndex 完全対応 Close 抽出
# =========================================
def safe_close_multi(df_raw, name):
    # ('Price','Ticker') MultiIndex 専用処理
    if isinstance(df_raw.columns, pd.MultiIndex):
        # MultiIndex 中の (Price, Ticker) を走査
        for price, ticker in df_raw.columns:
            if str(price).lower() in ("close", "adj close"):
                return df_raw[(price, ticker)]

        raise ValueError(f"{name}: no price columns in MultiIndex")

    # 単一 Index の場合
    for c in df_raw.columns:
        if str(c).lower() in ("close", "adj close"):
            return df_raw[c]

    raise ValueError(f"{name}: no usable price columns")


# =========================================
#  Yahoo Finance からデータ取得（MultiIndexのまま扱う）
# =========================================
def load_data():
    print("Downloading QQQ / SP500 …")

    qqq_raw = yf.download("QQQ", start="2000-01-01", progress=False)
    spy_raw = yf.download("SPY", start="2000-01-01", progress=False)

    # MultiIndex のまま safe 関数で抽出
    qqq_close = safe_close_multi(qqq_raw, "QQQ")
    spy_close = safe_close_multi(spy_raw, "SP500")

    df = pd.DataFrame({
        "QQQ": qqq_close,
        "SP500": spy_close
    })

    df.index = pd.to_datetime(df.index)
    df = df.dropna().sort_index()

    return df


# =========================================
#  年次リターン計算
# =========================================
def compute_annual(df: pd.DataFrame):
    out_q = {}
    out_s = {}

    years = sorted(set(df.index.year))
    for y in years:
        d = df[df.index.year == y]

        first_q = d["QQQ"].iloc[0]
        first_s = d["SP500"].iloc[0]

        d12 = d[d.index.month == 12]
        if len(d12) > 0:
            last_q = d12["QQQ"].iloc[-1]
            last_s = d12["SP500"].iloc[-1]
        else:
            last_q = d["QQQ"].iloc[-1]
            last_s = d["SP500"].iloc[-1]

        out_q[y] = last_q / first_q - 1
        out_s[y] = last_s / first_s - 1

    return out_q, out_s


# =========================================
#  金属ヘアライン背景 CSS
# =========================================
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
    color: #222;
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

h1 { font-size: 22px; font-weight: 600; margin: 0 0 18px 0; }
h2 { font-size: 14px; font-weight: 500; margin: 0 0 10px 0; }

.section { display: flex; gap: 18px; justify-content: space-between; }
.imghalf { width: 48%; border-radius: 10px; overflow: hidden; }
img { width: 100%; display: block; }

a {
    display: block;
    padding: 14px;
    margin: 16px 0;
    text-align: center;
    background: linear-gradient(#ffffff 0%, #eeeeee 40%, #d6d6d6 100%);
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.25);
    text-decoration: none;
    color: #222;
}
"""


# =========================================
#  グラフ系
# =========================================
def style_ticks(ax, small=True):
    ax.tick_params(labelsize=6 if small else 8)


def plot_correlation(x, y, label):
    fig, ax = plt.subplots(figsize=(3.4,3.4))

    slope, intercept = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0, 1] ** 2

    ax.scatter(x*100, y*100, s=14, color="#7bb0ff", alpha=0.7)

    xr = np.array([-15, 15])
    yr = slope*(xr/100)*100 + intercept*100
    ax.plot(xr, yr, color="#d43f3a", linewidth=1.7)

    ax.set_xlim(-15,15)
    ax.set_ylim(-15,15)
    ax.grid(color="#cccccc", linewidth=0.6)
    style_ticks(ax)
    ax.set_title(f"{label}\nβ={slope:.3f}, α={intercept:.3f}, R²={r2:.3f}", fontsize=8)

    return fig_to_base64(fig)


def plot_monthly(sp_arr, q_arr, title1, title2, ylimit, overall=False):
    fig, ax = plt.subplots(figsize=(3.4,3.4))

    x = np.arange(1,13)
    diff = (q_arr - sp_arr)*100

    ax.bar(x-0.2, sp_arr*100, width=0.4, color="#ff9ec6")
    ax.bar(x+0.2, q_arr*100, width=0.4, color="#a9d4ff")
    ax.plot(x, diff, color="#d43f3a", marker="o", linewidth=1.7)

    if overall:
        ax.set_ylim(-5,5)
        ax.set_yticks(np.arange(-5,6,1))
    else:
        ax.set_ylim(-ylimit*100, ylimit*100)

    ax.set_xlim(0.5,12.5)
    ax.set_xticks(np.arange(1,13))
    style_ticks(ax)
    ax.grid(color="#cccccc", linewidth=0.6)

    if title2:
        ax.set_title(f"{title1}\n{title2}", fontsize=8)
    else:
        ax.set_title(title1, fontsize=8)

    return fig_to_base64(fig)


def plot_annual_summary(ann_q, ann_s):
    fig, ax = plt.subplots(figsize=(5.2,3.2))

    years = sorted(ann_q.keys())
    x = np.arange(len(years))
    aq = np.array([ann_q[y]*100 for y in years])
    asv = np.array([ann_s[y]*100 for y in years])
    diff = aq - asv

    ax.bar(x-0.15, asv, width=0.3, color="#ff9ec6")
    ax.bar(x+0.15, aq, width=0.3, color="#a9d4ff")
    ax.plot(x, diff, color="#d43f3a", marker="o", linewidth=1.7)

    ax.set_ylim(-60,60)
    ax.set_yticks(np.arange(-60,61,10))
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(color="#cccccc", linewidth=0.6)
    style_ticks(ax)
    ax.set_title("Annual Return Summary", fontsize=9)

    return fig_to_base64(fig)


# =========================================
#  analysis_report.html を生成
# =========================================
def build_analysis_html(df, monthly_map, ann_q, ann_s):

    years = sorted(monthly_map.keys())
    sp_all = np.array([monthly_map[y]["SP500"] for y in years])
    q_all = np.array([monthly_map[y]["QQQ"] for y in years])
    mean_sp = sp_all.mean(axis=0)
    mean_q = q_all.mean(axis=0)

    overall_month_img = plot_monthly(
        mean_sp, mean_q,
        "Overall\nMonthly (Mean)", "",
        ylimit=0.05,
        overall=True
    )

    monthly_all = df.resample("M").last().pct_change().dropna()
    corr_overall_img = plot_correlation(
        monthly_all["SP500"].values,
        monthly_all["QQQ"].values,
        "Overall"
    )

    ann_img = plot_annual_summary(ann_q, ann_s)

    html = []
    html.append("<html><head><meta charset='utf-8'><style>")
    html.append(METAL_CSS)
    html.append("</style></head><body>")
    html.append("<h1>Finance Report</h1>")

    # Overall card
    html.append(f"""
<div class="card">
<h2>Overall Summary</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_overall_img}">
  <img class="imghalf" src="data:image/png;base64,{overall_month_img}">
</div>
</div>
""")

    # Annual
    html.append(f"""
<div class="card">
<h2>Annual Return Summary</h2>
<img style="width:100%;" src="data:image/png;base64,{ann_img}">
</div>
""")

    # Per-year
    all_years = sorted(monthly_map.keys(), reverse=True)
    for y in all_years:
        sp_arr = monthly_map[y]["SP500"]
        q_arr = monthly_map[y]["QQQ"]

        aq = ann_q[y]*100
        asv = ann_s[y]*100
        diff = aq - asv

        monthly_year = df[df.index.year == y].resample("M").last().pct_change().dropna()
        if len(monthly_year) > 0:
            corr_img = plot_correlation(
                monthly_year["SP500"].values,
                monthly_year["QQQ"].values,
                str(y)
            )
        else:
            corr_img = ""

        title1 = f"{y} Monthly"
        title2 = f"SP500 {asv:+.1f}% / QQQ {aq:+.1f}% / Diff {diff:+.1f}%"

        bar_img = plot_monthly(
            sp_arr, q_arr,
            title1, title2,
            ylimit=0.15
        )

        html.append(f"""
<div class="card">
<h2>{y}</h2>
<div class="section">
  <img class="imghalf" src="data:image/png;base64,{corr_img}">
  <img class="imghalf" src="data:image/png;base64,{bar_img}">
</div>
</div>
""")

    html.append("</body></html>")

    with open(HTML_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(html))


# =========================================
#  index.html を生成
# =========================================
def build_index_html():
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Finance Dashboard</title>
<style>
{METAL_CSS}
.indexwrap {{ max-width: 900px; margin: 0 auto; }}
.indexcard {{
    background: rgba(255,255,255,0.28);
    backdrop-filter: blur(10px);
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.55);
    margin-bottom: 28px;
}}
.index_title {{ font-size: 20px; font-weight:600; margin-bottom:18px; }}
.index_btns {{ display:flex; flex-direction:column; gap:14px; }}
</style>
</head>

<body>
<div class="indexwrap">

<div class="indexcard">
    <div class="index_title">Finance Dashboard</div>

    <div class="index_btns">
        <a href="analysis_report.html">📈 Analysis Report</a>
        <a href="run_update.command">🔄 更新する（CSV & HTML 再生成）</a>
    </div>
</div>

</div>
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

    monthly_raw = df.resample("M").last().pct_change()
    monthly_map = {}
    years = sorted(set(monthly_raw.index.year))

    for y in years:
        mm = monthly_raw[monthly_raw.index.year == y]
        arr_sp = np.zeros(12)
        arr_qq = np.zeros(12)

        for m in range(1,13):
            row = mm[mm.index.month == m]
            if len(row) == 1:
                arr_sp[m-1] = float(row["SP500"].values[0])
                arr_qq[m-1] = float(row["QQQ"].values[0])
            else:
                arr_sp[m-1] = 0.0
                arr_qq[m-1] = 0.0

        monthly_map[y] = {"SP500": arr_sp, "QQQ": arr_qq}

    # monthly CSV
    df_month = []
    for y in years:
        sp = monthly_map[y]["SP500"]
        q = monthly_map[y]["QQQ"]
        df_month.append([y] + list(sp) + list(q))

    cols = ["Year"] + [f"SP_m{i}" for i in range(1,13)] + [f"QQQ_m{i}" for i in range(1,13)]
    pd.DataFrame(df_month, columns=cols).to_csv(CSV_MONTHLY, index=False)

    # annual CSV
    ann_q, ann_s = compute_annual(df)
    df_annual = []
    for y in sorted(ann_q.keys()):
        df_annual.append([y, ann_s[y], ann_q[y], ann_q[y] - ann_s[y]])

    pd.DataFrame(df_annual, columns=["Year","SP500","QQQ","Diff"]).to_csv(CSV_ANNUAL, index=False)

    # HTML
    build_analysis_html(df, monthly_map, ann_q, ann_s)
    build_index_html()

    print("✔ Metallic Finance Dashboard updated successfully.")
