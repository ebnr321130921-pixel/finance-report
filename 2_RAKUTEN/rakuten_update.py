#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import re
import subprocess
from pathlib import Path

# ==========================================================
# PATH
# ==========================================================
BASE = Path(__file__).resolve().parent
RAW = BASE / "daily_raw.csv"
RECORDS = BASE / "daily_records.csv"
BUILD_PY = BASE / "build.py"

# ==========================================================
# MASTER（銘柄マスタ）
# ==========================================================
MASTER = [
    {
        "fund_id": "JP90C000Q2U6",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000Q2U6",
        "short": "楽天SP500",
    },
    {
        "fund_id": "JP90C000QF22",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000QF22",
        "short": "楽天QQQ",
    },
    {
        "fund_id": "JP90C000FHD2",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000FHD2",
        "short": "楽天VTI",
    },
    {
        "fund_id": "JP90C000MLM1",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000MLM1",
        "short": "楽天レバナス",
    },
]

SHORTS = [m["short"] for m in MASTER]

# ==========================================================
# Utility
# ==========================================================
def normalize_date(x):
    if pd.isna(x):
        return None
    x = str(x).replace("/", "-")
    dt = pd.to_datetime(x, errors="coerce")
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


def normalize_records(df):
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    df["fetch_time"] = pd.to_datetime(df["fetch_time"], errors="coerce")

    for s in SHORTS:
        if s in df.columns:
            df[s] = pd.to_numeric(df[s], errors="coerce")

        mcol = f"{s}_market_date"
        if mcol in df.columns:
            df[mcol] = df[mcol].apply(normalize_date)

        for col in [f"{s}_prev_diff", f"{s}_prev_pct", f"{s}_cum_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    if "global_market_date" in df.columns:
        df["global_market_date"] = df["global_market_date"].apply(normalize_date)

    return df

# ==========================================================
# スクレイピング
# ==========================================================
def fetch_fund(url):
    r = requests.get(url)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    pm = re.search(r"基準価額\s*([\d,]+)\s*円", text)
    if not pm:
        raise ValueError("基準価額が取得できません:" + url)
    price = int(pm.group(1).replace(",", ""))

    dm = re.search(r"[（(]\s*(\d{1,2})/(\d{1,2})\s*[）)]", text)
    if not dm:
        raise ValueError("市場日が取得できません:" + url)
    y = datetime.now().year
    mdate = datetime(y, int(dm.group(1)), int(dm.group(2))).strftime("%Y-%m-%d")

    return price, mdate


def fetch_raw():
    row = {}
    row["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mdates = []
    for m in MASTER:
        price, mdate = fetch_fund(m["url"])
        s = m["short"]
        row[s] = price
        row[f"{s}_market_date"] = mdate
        mdates.append(mdate)

    row["global_market_date"] = max(mdates)

    df = pd.DataFrame([row])
    df.to_csv(RAW, index=False, encoding="utf-8-sig")

    print("RAW updated:", RAW)
    return df

# ==========================================================
# 差分 + 累積率
# ==========================================================
def calc_prev_and_cum(df):
    df = df.sort_values("global_market_date").reset_index(drop=True)

    for s in SHORTS:
        price_col = s
        mdate_col = f"{s}_market_date"

        if price_col not in df.columns:
            continue

        df[f"{s}_prev_diff"] = df[price_col].diff().fillna(0)
        df[f"{s}_prev_pct"] = df[price_col].pct_change().fillna(0) * 100

        base_price = df[price_col].iloc[0]
        df[f"{s}_cum_pct"] = (df[price_col] / base_price - 1) * 100

    return df


# ==========================================================
# RECORD UPDATE
# ==========================================================
def update_records(raw):
    new = raw.iloc[0].copy()
    new["fetch_time"] = pd.to_datetime(new["fetch_time"])

    if not RECORDS.exists():
        pd.DataFrame([new]).to_csv(RECORDS, index=False, encoding="utf-8-sig")
        print("Created:", RECORDS)
        return

    rec = pd.read_csv(RECORDS)
    rec = normalize_records(rec)

    rec = pd.concat([rec, pd.DataFrame([new])], ignore_index=True)

    # market_date が同じで古い fetch_time を削除
    for s in SHORTS:
        mcol = f"{s}_market_date"
        if mcol not in rec.columns:
            continue

        same = rec[rec[mcol] == new[mcol]]
        if len(same) > 1:
            newest = same["fetch_time"].idxmax()
            drop = [i for i in same.index if i != newest]
            rec = rec.drop(drop)

    rec = calc_prev_and_cum(rec)

    rec.to_csv(RECORDS, index=False, encoding="utf-8-sig")
    print("Updated:", RECORDS)


# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    print("\n=== FETCH RAW ===")
    raw = fetch_raw()

    print("\n=== UPDATE RECORDS ===")
    update_records(raw)

    print("\n=== BUILD HTML ===")
    if BUILD_PY.exists():
        subprocess.run(["python3", str(BUILD_PY)])
    else:
        print("build.py が存在しません。")

    print("\n=== COMPLETED ===\n")
