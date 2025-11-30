#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime
from io import BytesIO
import base64

##############################################################################
# パス
##############################################################################

BASE = os.path.dirname(os.path.abspath(__file__))

CSV_DAILY = os.path.join(BASE, "us_index_daily.csv")
CSV_DAILY_BK = os.path.join(BASE, "us_index_daily_backup.csv")

CSV_MONTH = os.path.join(BASE, "us_index_monthly.csv")
CSV_MONTH_BK = os.path.join(BASE, "us_index_monthly_backup.csv")

HTML_OUT = os.path.join(BASE, "us_index.html")

##############################################################################
# 対象指数
##############################################################################

INDEX_LIST = [
    ("SP500", "^GSPC"),
    ("NASDAQ100", "^NDX"),
    ("DOW", "^DJI"),
    ("RUSSELL2000", "^RUT"),
    ("VIX", "^VIX"),
    ("USDJPY", "JPY=X"),
    ("US10Y", "^TNX"),
]

##############################################################################
# Utility
##############################################################################

def encode_plot(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

##############################################################################
# ★ daily.csv の完全修復（不要列全部削除・6列のみ残す）
##############################################################################

def repair_daily_columns(df):

    keep = ["MarketDate", "CollectDate", "Name", "Last", "Diff", "DiffP"]

    # 必要列が無い場合は作成
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan

    # 数値列統一
    df["Last"] = pd.to_numeric(df["Last"], errors="coerce")
    df["Diff"] = pd.to_numeric(df["Diff"], errors="coerce")
    df["DiffP"] = pd.to_numeric(df["DiffP"], errors="coerce")

    # ★ 空白文字列を NaN に強制変換
    df["MarketDate"].replace("", np.nan, inplace=True)
    df["CollectDate"].replace("", np.nan, inplace=True)
    df["Name"].replace("", np.nan, inplace=True)

    # ★ 必須列欠損はすべて削除
    df = df.dropna(subset=["MarketDate", "Name", "Last"])

    # 不要列削除
    df = df[keep]

    return df

##############################################################################
# 1. Fetch Daily
##############################################################################

def fetch_daily():
    rows = []
    collect_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, tic in INDEX_LIST:

        try:
            df = yf.download(tic, period="7d", interval="1d", progress=False).dropna()
        except Exception:
            continue

        if df.empty:
            continue

        df = df.sort_index()
        last_date = df.index[-1].strftime("%Y-%m-%d")
        last_close = float(df["Close"].iloc[-1])

        # 前日
        if len(df) >= 2:
            prev = float(df["Close"].iloc[-2])
        else:
            prev = last_close

        diff = last_close - prev
        diffp = (diff / prev * 100) if prev != 0 else 0

        rows.append([
            last_date, collect_dt, name,
            last_close, diff, diffp
        ])

    df_new = pd.DataFrame(rows, columns=[
        "MarketDate", "CollectDate", "Name",
        "Last", "Diff", "DiffP"
    ])
    return df_new

##############################################################################
# 2. Update Daily
##############################################################################

def update_daily(df_new):

    df_new = repair_daily_columns(df_new)

    if not os.path.exists(CSV_DAILY):
        df_new.to_csv(CSV_DAILY, index=False)
        df_new.to_csv(CSV_DAILY_BK, index=False)
        return df_new

    old = pd.read_csv(CSV_DAILY, dtype=str)
    old = repair_daily_columns(old)

    key_old = old["MarketDate"].astype(str) + "_" + old["Name"].astype(str)
    key_new = df_new["MarketDate"].astype(str) + "_" + df_new["Name"].astype(str)

    mask = ~key_new.isin(key_old)
    merged = pd.concat([old, df_new[mask]], ignore_index=True)

    merged = merged.sort_values(["MarketDate", "Name"])
    merged.to_csv(CSV_DAILY, index=False)
    merged.to_csv(CSV_DAILY_BK, index=False)

    return merged

##############################################################################
# 3. Update Monthly
##############################################################################

def update_monthly(df_daily):

    df_daily["Last"] = pd.to_numeric(df_daily["Last"], errors="coerce")
    df_daily["DiffP"] = pd.to_numeric(df_daily["DiffP"], errors="coerce")
    df_daily = df_daily.dropna(subset=["Last"])

    df_daily["Month"] = pd.to_datetime(df_daily["MarketDate"]).dt.strftime("%Y-%m")

    rows = []
    for (mon, name), grp in df_daily.groupby(["Month", "Name"]):
        grp = grp.sort_values("MarketDate")
        if grp.empty:
            continue

        first = grp["Last"].iloc[0]
        last = grp["Last"].iloc[-1]
        avg = grp["Last"].mean()
        mn = grp["Last"].min()
        mx = grp["Last"].max()
        change_pct = (last - first) / first * 100 if first != 0 else 0
        avg_dp = grp["DiffP"].mean()
        vol = grp["Last"].std()

        rows.append([
            mon, name,
            first, last, change_pct,
            avg, mn, mx,
            avg_dp, vol
        ])

    df_month = pd.DataFrame(rows, columns=[
        "Month", "Name",
        "Open", "Close", "ChangePct",
        "Avg", "Min", "Max",
        "AvgDiffP", "Volatility"
    ])

    df_month.to_csv(CSV_MONTH, index=False)
    df_month.to_csv(CSV_MONTH_BK, index=False)
    return df_month

##############################################################################
# 4. HTML
##############################################################################

def build_html(df_daily, df_month):

    # ---------- 上段：昨日→今日 ----------
    df_sorted = df_daily.sort_values("MarketDate")
    latest = df_sorted.groupby("Name").tail(1)
    yest = df_sorted.groupby("Name").nth(-2)

    compare = []
    for name in latest["Name"].unique():
        t = latest[latest["Name"] == name].iloc[0]
        p = yest.loc[name] if name in yest.index else None

        prev_last = float(p["Last"]) if p is not None else float(t["Last"])
        diff = t["Last"] - prev_last
        diffp = (diff / prev_last * 100) if prev_last != 0 else 0

        compare.append([name, prev_last, t["Last"], diff, diffp])

    # ---------- Daily Chart ----------
    df_daily["Day"] = pd.to_datetime(df_daily["MarketDate"]).dt.day
    pivot_daily = df_daily.pivot(index="Name", columns="Day", values="DiffP")

    daily_imgs = {}
    for name in pivot_daily.index:
        fig, ax = plt.subplots(figsize=(4,2))
        ax.plot(pivot_daily.columns, pivot_daily.loc[name], marker="o")
        ax.set_title(name, fontsize=8)
        ax.grid(True)
        daily_imgs[name] = encode_plot(fig)
        plt.close(fig)

    # ---------- Monthly ----------
    df_month["Mon"] = pd.to_datetime(df_month["Month"] + "-01").dt.month
    pivot_m = df_month.pivot(index="Name", columns="Mon", values="ChangePct")

    monthly_imgs = {}
    for name in pivot_m.index:
        fig, ax = plt.subplots(figsize=(4,2))
        ax.plot(pivot_m.columns, pivot_m.loc[name], marker="o")
        ax.set_title(name + " Monthly", fontsize=8)
        ax.grid(True)
        monthly_imgs[name] = encode_plot(fig)
        plt.close(fig)

    # ---------- HTML ----------
    html = []
    html.append("""
<html><head>
<meta charset='UTF-8'>
<title>US Index</title>
<style>
body { font-family:-apple-system,BlinkMacSystemFont; background:#f5f5f7; padding:20px; }
.box { background:white; padding:15px; margin-bottom:20px; border-radius:12px;
       box-shadow:0 2px 6px rgba(0,0,0,0.05); }
table { width:100%; border-collapse:collapse; margin-top:10px; }
th,td { border:1px solid #ddd; padding:6px 10px; font-size:12px; }
th { background:#fafafa; }
</style>
</head><body>
<h2>US Index Dashboard</h2>
""")

    html.append("<div class='box'><h3>Yesterday → Today</h3>")
    html.append("<table><tr><th>Name</th><th>Prev</th><th>Today</th><th>Diff</th><th>Diff%</th></tr>")
    for n, p, t, d, dp in compare:
        html.append(f"<tr><td>{n}</td><td>{p:.2f}</td><td>{t:.2f}</td>"
                    f"<td>{d:.2f}</td><td>{dp:.2f}%</td></tr>")
    html.append("</table></div>")

    html.append("<div class='box'><h3>Daily Trend</h3>")
    for n, img in daily_imgs.items():
        html.append(f"<b>{n}</b><br><img src='data:image/png;base64,{img}'><br><br>")
    html.append("</div>")

    html.append("<div class='box'><h3>Monthly Trend</h3>")
    for n, img in monthly_imgs.items():
        html.append(f"<b>{n}</b><br><img src='data:image/png;base64,{img}'><br><br>")
    html.append("</div>")

    html.append("</body></html>")

    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(html))

    return HTML_OUT

##############################################################################
# MAIN
##############################################################################

if __name__ == "__main__":
    print("Fetching Daily...")
    df_new = fetch_daily()

    print("Updating Daily CSV...")
    df_daily = update_daily(df_new)

    print("Updating Monthly CSV...")
    df_month = update_monthly(df_daily)

    print("Building HTML...")
    out = build_html(df_daily, df_month)

    print("✔ Completed")
    print("HTML:", out)
