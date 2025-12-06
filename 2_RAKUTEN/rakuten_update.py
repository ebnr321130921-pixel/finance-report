#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import re

# ==========================================================
# PATH
# ==========================================================
BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "daily_raw.csv")
RECORDS = os.path.join(BASE, "daily_records.csv")

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
# 文字 → 日付変換
# ==========================================================
def normalize_date(x):
    if pd.isna(x):
        return None
    x = str(x).replace("/", "-")
    dt = pd.to_datetime(x, errors="coerce")
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


# ==========================================================
# RECORDS を全て正規化
# ==========================================================
def normalize_records(df):
    # ゴミ列削除
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

    # fetch_time
    df["fetch_time"] = pd.to_datetime(df["fetch_time"], errors="coerce")

    for s in SHORTS:
        # price
        if s in df.columns:
            df[s] = pd.to_numeric(df[s], errors="coerce").astype("Int64")

        # market_date
        mcol = f"{s}_market_date"
        if mcol in df.columns:
            df[mcol] = df[mcol].apply(normalize_date)

        # 前日比（円）
        dcol = f"{s}_prev_diff"
        if dcol in df.columns:
            df[dcol] = pd.to_numeric(df[dcol], errors="coerce")

        # 前日比（％）
        pcol = f"{s}_prev_pct"
        if pcol in df.columns:
            df[pcol] = pd.to_numeric(df[pcol], errors="coerce")

    # global market date
    if "global_market_date" in df.columns:
        df["global_market_date"] = df["global_market_date"].apply(normalize_date)

    return df


# ==========================================================
# スクレイピング（値段 + 日付のみ）
# ==========================================================
def fetch_fund(url):
    r = requests.get(url)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    # 基準価額
    pm = re.search(r"基準価額\s*([\d,]+)\s*円", text)
    if not pm:
        raise ValueError("基準価額が取得できません:" + url)

    price = int(pm.group(1).replace(",", ""))

    # 市場日 (MM/DD)
    dm = re.search(r"[（(]\s*(\d{1,2})/(\d{1,2})\s*[）)]", text)
    if not dm:
        raise ValueError("市場日が取得できません:" + url)

    y = datetime.now().year
    mdate = datetime(y, int(dm.group(1)), int(dm.group(2))).strftime("%Y-%m-%d")

    return price, mdate


# ==========================================================
# RAW（スクレイピング結果）作成
# ==========================================================
def fetch_raw():
    row = {}
    row["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mdates = []

    for m in MASTER:
        price, mdate = fetch_fund(m["url"])
        short = m["short"]

        row[short] = price
        row[f"{short}_market_date"] = mdate
        mdates.append(mdate)

    row["global_market_date"] = max(mdates)

    df = pd.DataFrame([row])
    df.to_csv(RAW, index=False, encoding="utf-8-sig")

    print("RAW updated:", RAW)
    return df


# ==========================================================
# 前日比計算（ファンドごとに market_date を基準に）
# ==========================================================
def calc_prev_diff(df):
    for s in SHORTS:
        price_col = s
        mdate_col = f"{s}_market_date"

        if price_col not in df.columns or mdate_col not in df.columns:
            continue

        # ファンドごとに market_date 昇順に並べ替えて差分計算
        temp = df[[price_col, mdate_col]].copy()
        temp = temp.sort_values(mdate_col)

        df[f"{s}_prev_diff"] = temp[price_col].diff().reindex(df.index).fillna(0)
        df[f"{s}_prev_pct"] = (temp[price_col].pct_change() * 100).reindex(df.index).fillna(0)

    return df


# ==========================================================
# RECORDS 更新処理
# ==========================================================
def update_records(raw):
    # 新しい行
    new_row = raw.iloc[0].to_dict()
    new_row["fetch_time"] = pd.to_datetime(new_row["fetch_time"])
    gmd = new_row["global_market_date"]

    # 初回
    if not os.path.exists(RECORDS):
        pd.DataFrame([new_row]).to_csv(RECORDS, index=False, encoding="utf-8-sig")
        print("Created:", RECORDS)
        return

    # 既存読み込み
    rec = pd.read_csv(RECORDS)
    rec = normalize_records(rec)

    # 追加
    rec = pd.concat([rec, pd.DataFrame([new_row])], ignore_index=True)

    # 同じ market_date で古い fetch_time の行を削除（最新だけ残す）
    for s in SHORTS:
        mcol = f"{s}_market_date"
        if mcol not in rec.columns:
            continue

        same = rec[rec[mcol] == new_row[mcol]]
        if len(same) > 1:
            newest_idx = same["fetch_time"].idxmax()
            drop_idx = [i for i in same.index if i != newest_idx]
            rec = rec.drop(drop_idx)

    # 日付順に並べる
    rec = rec.sort_values(["global_market_date", "fetch_time"]).reset_index(drop=True)

    # 前日比を計算
    rec = calc_prev_diff(rec)

    # 保存
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

    print("\n=== COMPLETED UPDATE ===")

    # ============================================
    # RUN BUILD AFTER UPDATE
    # ============================================
    import subprocess
    import sys
    import os

    build_script = os.path.join(os.path.dirname(__file__), "build.py")

    print("\n=== RUN BUILD ===")
    try:
        subprocess.run([sys.executable, build_script], check=True)
        print("Build completed successfully.")
    except Exception as e:
        print(f"Build failed: {e}")