#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime
import re
import subprocess
from pathlib import Path
import sys

# ==========================================================
# WHAT THIS SCRIPT DOES（機能メモ / 設計意図）
# ==========================================================
# 1. 楽天証券サイトから投資信託データを自動取得
#    - 基準価額（円）
#    - 市場日（MM/DD 表記を YYYY-MM-DD に正規化）
#    - 対象：楽天SP500 / 楽天QQQ / 楽天VTI / 楽天レバナス
#
# 2. 日次の生データを daily_raw.csv に保存
#    - fetch_time（取得時刻）
#    - 各銘柄の基準価額
#    - 各銘柄の市場日
#    - global_market_date（当日の最新市場日）
#
# 3. daily_records.csv を中核データとして管理
#    - 既存データに新行を追加
#    - 同一市場日の重複行は fetch_time が最新のものだけ残す
#    - 日付・数値を正規化して時系列の整合性を保証
#
# 4. 前日比を自動計算（銘柄別）
#    - {銘柄}_prev_diff : 前日差分（円）
#    - {銘柄}_prev_pct  : 前日比（%）
#
# 5. iDeCo運用開始日基準の累積率を計算（重要）
#    - 起点：IDECO_START_DATE（例：2023-08-03）
#    - {銘柄}_cum_pct を運用開始日基準で算出
#      * 開始日前 → NaN
#      * 開始日当日 → 0.0%
#      * 以降 → 純粋な累積リターン
#    - スクレイピング開始日基準ではない点が重要
#
# 6. daily_records.csv は「市場データ層」として使用
#    - 個人資産情報（units / 初期投資額など）は含めない
#    - それらは build.py / holdings.csv 側で扱う設計
#
# 7. build.py との自動連携
#    - 本スクリプト実行後に build.py が存在すれば自動実行
#    - 取得 → 計算 → 可視化 のパイプラインを一気通貫で回す
#
# 8. 後段（build.py）で可能になること
#    - 日次 / 週次 / 月次（18ヶ月固定）パフォーマンス表示
#    - 運用開始金額（holdings.csv）を使った資産配分・寄与度分析
#    - iDeCo運用の可視化・意思決定用ダッシュボード構築
#
# 設計思想：
# - このスクリプトは「正しい基準での市場データ生成」に専念する
# - 個人ポートフォリオ計算やUIは build.py 側に責務分離する
# ==========================================================


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
# IDECO START DATE（累積率の起点）
# ==========================================================
IDECO_START_DATE = "2023-08-03"


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

    now = datetime.now()

    m = int(dm.group(1))
    d = int(dm.group(2))

    # 年候補（今年・去年）
    candidates = [
        datetime(now.year, m, d),
        datetime(now.year - 1, m, d),
    ]

    # fetch_time（now）より未来でないものに限定
    past_candidates = [c for c in candidates if c <= now]

    if past_candidates:
        # now に最も近い過去日を採用
        chosen = max(past_candidates)
    else:
        # 念のための保険（理論上ほぼ起きない）
        chosen = min(candidates)

    mdate = chosen.strftime("%Y-%m-%d")

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
    df["global_market_date"] = pd.to_datetime(df["global_market_date"], errors="coerce")
    df = df.sort_values("global_market_date").reset_index(drop=True)

    base_date = pd.to_datetime(IDECO_START_DATE)


    for s in SHORTS:
        price_col = s
        mdate_col = f"{s}_market_date"

        if price_col not in df.columns or mdate_col not in df.columns:
            continue

        # ---- 前日比 ----
        df[f"{s}_prev_diff"] = df[price_col].diff()
        df[f"{s}_prev_pct"] = df[price_col].pct_change() * 100

        # ---- 累積率（運用開始日基準）----
        df[mdate_col] = pd.to_datetime(df[mdate_col], errors="coerce")

        base_row = df[df[mdate_col] == base_date]

        if base_row.empty:
            df[f"{s}_cum_pct"] = np.nan
        else:
            base_price = base_row.iloc[0][price_col]
            df[f"{s}_cum_pct"] = np.where(
                df[mdate_col] >= base_date,
                (df[price_col] / base_price - 1) * 100,
                np.nan
            )

        # ---- 累積率（年初リセット基準）----
        yearly_cum = []

        for _, row in df.iterrows():
            mdate = row[mdate_col]
            price = row[price_col]

            if pd.isna(mdate) or pd.isna(price):
                yearly_cum.append(np.nan)
                continue

            year_start = pd.Timestamp(year=mdate.year, month=1, day=1)

            base_rows = df[
                (df[mdate_col] >= year_start) &
                (df[mdate_col] <= mdate)
            ]

            base_price = base_rows.iloc[0][price_col]

            yearly_cum.append((price / base_price - 1) * 100)

        df[f"{s}_yearly_cum_pct"] = yearly_cum


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

    FORGE_PY = BASE / "rakuten_forge.py"

    print("\n=== RUN FORGE ===")
    if FORGE_PY.exists():
        subprocess.run([sys.executable, str(FORGE_PY)], check=True)
    else:
        print("rakuten_forge.py が存在しません")

    print("\n=== RUN BUILD ===")
    if BUILD_PY.exists():
        subprocess.run([sys.executable, str(BUILD_PY)], check=True)
    else:
        print("build.py が存在しません")

    print("\n=== COMPLETED ===\n")
