#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import argparse
import json
import os
import re

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
MASTER_JSON = BASE / "fund_master.json"
HOLDINGS_JSON = BASE / "holdings.json"
RECORDS = BASE / "daily_records.json"
LEGACY_RECORDS_CSV = BASE / "daily_records.csv"
WRITE_OUTPUTS = False


def write_output(df, filename):
    if WRITE_OUTPUTS:
        df.to_csv(BASE / filename, index=False, encoding="utf-8-sig")


def load_records():
    if RECORDS.exists():
        return pd.read_json(RECORDS, orient="records")
    if LEGACY_RECORDS_CSV.exists():
        return pd.read_csv(LEGACY_RECORDS_CSV)
    return pd.DataFrame()


def save_records(df):
    df.to_json(RECORDS, orient="records", force_ascii=False, indent=2, date_format="iso")

@dataclass(frozen=True)
class Product:
    broker: str
    fund_id: str
    short: str
    display_name: str
    color: str
    source_url: str
    added_on: str = ""
    notes: str = ""
    show_in_viewer: bool = True


def load_master():
    with MASTER_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def load_products(enabled_only=True):
    master = load_master()
    products = []

    for row in master.get("products", []):
        if enabled_only and not row.get("enabled", True):
            continue
        products.append(Product(
            broker=row.get("broker", ""),
            fund_id=row.get("fund_id", ""),
            short=row["short"],
            display_name=row["display_name"],
            color=row.get("color", "#888888"),
            source_url=row["source_url"],
            added_on=row.get("added_on", ""),
            notes=row.get("notes", ""),
            show_in_viewer=row.get("show_in_viewer", True),
        ))

    if not products:
        raise ValueError(f"No enabled products in {MASTER_JSON}")

    return products


def load_settings():
    return load_master().get("settings", {})


def product_display_map():
    return {p.short: p.display_name for p in load_products()}


def product_color_map():
    return {p.display_name: p.color for p in load_products()}


def viewer_products():
    return [p.display_name for p in load_products() if p.show_in_viewer]


def load_holdings():
    raw = os.environ.get("RAKUTEN_HOLDINGS_JSON")
    if raw:
        data = json.loads(raw)
    elif HOLDINGS_JSON.exists():
        with HOLDINGS_JSON.open(encoding="utf-8") as f:
            data = json.load(f)
    else:
        legacy_csv = BASE / "holdings.csv"
        if legacy_csv.exists():
            return pd.read_csv(legacy_csv)
        data = []

    if isinstance(data, dict):
        data = data.get("holdings", [])

    return pd.DataFrame(data, columns=[
        "product",
        "account",
        "units",
        "status",
        "change_date",
        "change_value",
        "Zero_date",
        "start",
        "start_value",
    ])


# ==========================================================
# WHAT THIS SCRIPT DOES（機能メモ / 設計意図）
# ==========================================================
# 1. fund_master.json に定義した投資信託データを自動取得
#    - 基準価額（円）
#    - 市場日（MM/DD 表記を YYYY-MM-DD に正規化）
#    - 対象：fund_master.json の enabled=true 商品
#
# 2. 取得値をそのまま daily_records.json に統合
#
# 3. daily_records.json を中核データとして管理
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
# 6. daily_records.json は「市場データ層」として使用
#    - 個人資産情報（units / 初期投資額など）は含めない
#    - それらは holdings.json 側で扱う
#
# 7. 本ファイルだけで可能になること
#    - 日次 / 週次 / 月次（18ヶ月固定）パフォーマンス表示
#    - 運用開始金額（holdings.json）を使った資産配分・寄与度分析
#    - iDeCo運用の可視化・意思決定用ダッシュボード構築
#
# 設計思想：
# - このスクリプトを唯一の実行入口にする
# - 商品マスタは fund_master.json、保有情報は holdings.json に分離する
# ==========================================================

# ==========================================================
# MASTER（銘柄マスタ）
# ==========================================================
PRODUCTS = load_products()
SHORTS = [p.short for p in PRODUCTS]

# ==========================================================
# IDECO START DATE（累積率の起点）
# ==========================================================
IDECO_START_DATE = load_settings().get("ideco_start_date", "2023-08-03")


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
def fetch_fund(product):
    r = requests.get(product.source_url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    pm = re.search(r"基準価額\s*([\d,]+)\s*円", text)
    if not pm:
        raise ValueError(f"基準価額が取得できません: {product.short}")
    price = int(pm.group(1).replace(",", ""))

    dm = re.search(r"[（(]\s*(\d{1,2})/(\d{1,2})\s*[）)]", text)
    if not dm:
        raise ValueError(f"市場日が取得できません: {product.short}")

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


def extract_js_array(text, start_pos):
    start = text.find("[", start_pos)
    if start == -1:
        raise ValueError("data array start not found")

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    raise ValueError("data array end not found")


def fetch_nav_history(product):
    r = requests.get(product.source_url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    text = r.text

    marker = "name: '基準価額'"
    marker_pos = text.find(marker)
    if marker_pos == -1:
        raise ValueError(f"基準価額チャートが見つかりません: {product.short}")

    data_pos = text.find("data", marker_pos)
    if data_pos == -1:
        raise ValueError(f"基準価額チャートデータが見つかりません: {product.short}")

    data_array = extract_js_array(text, data_pos)
    pairs = re.findall(r"\[\s*(\d{12,13})\s*,\s*([0-9.]+)\s*\]", data_array)
    if not pairs:
        raise ValueError(f"基準価額チャートデータが空です: {product.short}")

    history = pd.DataFrame(
        [(int(ts), float(nav)) for ts, nav in pairs],
        columns=["timestamp_ms", "nav"]
    )
    history["market_date"] = (
        pd.to_datetime(history["timestamp_ms"], unit="ms", utc=True)
        .dt.tz_convert("Asia/Tokyo")
        .dt.strftime("%Y-%m-%d")
    )
    history["nav"] = history["nav"].astype(int)
    return history[["market_date", "nav"]].drop_duplicates("market_date", keep="last")


def fetch_raw():
    row = {}
    row["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mdates = []
    for product in PRODUCTS:
        price, mdate = fetch_fund(product)
        s = product.short
        row[s] = price
        row[f"{s}_market_date"] = mdate
        mdates.append(mdate)

    row["global_market_date"] = max(mdates)

    df = pd.DataFrame([row])

    print("Online data fetched")
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
        valid_price = df[price_col].notna()
        df[f"{s}_prev_diff"] = np.nan
        df[f"{s}_prev_pct"] = np.nan
        df.loc[valid_price, f"{s}_prev_diff"] = df.loc[valid_price, price_col].diff()
        df.loc[valid_price, f"{s}_prev_pct"] = df.loc[valid_price, price_col].pct_change(fill_method=None) * 100

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
                (df[mdate_col] <= mdate) &
                (df[price_col].notna())
            ]
            if base_rows.empty:
                yearly_cum.append(np.nan)
                continue

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
        rec = calc_prev_and_cum(pd.DataFrame([new]))
        save_records(rec)
        print("Created:", RECORDS)
        return

    rec = load_records()
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

    save_records(rec)
    print("Updated:", RECORDS)


def product_by_short(short):
    for product in PRODUCTS:
        if product.short == short or product.display_name == short or product.fund_id == short:
            return product
    raise ValueError(f"Unknown product: {short}")


def ensure_product_columns(rec, product):
    s = product.short
    for col in [
        s,
        f"{s}_market_date",
        f"{s}_prev_diff",
        f"{s}_prev_pct",
        f"{s}_cum_pct",
        f"{s}_yearly_cum_pct",
    ]:
        if col not in rec.columns:
            rec[col] = np.nan
    return rec


def backfill_product_history(product):
    history = fetch_nav_history(product)

    if RECORDS.exists():
        rec = normalize_records(load_records())
    elif LEGACY_RECORDS_CSV.exists():
        rec = normalize_records(load_records())
    else:
        rec = pd.DataFrame(columns=["fetch_time", "global_market_date"])

    rec = ensure_product_columns(rec, product)
    rec["global_market_date"] = rec["global_market_date"].apply(normalize_date)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_dates = set(rec["global_market_date"].dropna().astype(str))
    add_rows = []
    for mdate in history["market_date"]:
        if mdate not in existing_dates:
            add_rows.append({
                "fetch_time": now,
                "global_market_date": mdate,
            })

    if add_rows:
        rec = pd.concat([rec, pd.DataFrame(add_rows)], ignore_index=True)

    date_to_nav = history.set_index("market_date")["nav"].to_dict()
    s = product.short
    mask = rec["global_market_date"].isin(date_to_nav.keys())
    rec.loc[mask, s] = rec.loc[mask, "global_market_date"].map(date_to_nav)
    rec.loc[mask, f"{s}_market_date"] = rec.loc[mask, "global_market_date"]

    rec = calc_prev_and_cum(rec)
    save_records(rec)
    print(f"Backfilled {product.short}: {len(history)} rows")


def backfill_histories(targets):
    if not targets or "all" in targets:
        products = PRODUCTS
    else:
        products = [product_by_short(target) for target in targets]

    for product in products:
        backfill_product_history(product)



# ------------------------------------------------------------
# Product mapping
# ------------------------------------------------------------
PRODUCT_MAP = product_display_map()

JP_PRODUCTS = list(PRODUCT_MAP.keys())

# ------------------------------------------------------------
# Load source data
# ------------------------------------------------------------
def load_source():
    raw = load_records()

    rows = []
    for jp in JP_PRODUCTS:
        required = [jp, f"{jp}_market_date", f"{jp}_prev_pct"]
        missing = [col for col in required if col not in raw.columns]
        if missing:
            print(f"[WARN] skip {jp}: missing columns {missing}")
            continue

        cum_col = f"{jp}_cum_pct"
        rows.append(pd.DataFrame({
            "product": PRODUCT_MAP[jp],
            "market_date": pd.to_datetime(raw[f"{jp}_market_date"]),
            "nav": pd.to_numeric(raw[jp], errors="coerce"),
            "pct": pd.to_numeric(raw[f"{jp}_prev_pct"], errors="coerce"),
            "cum_pct": pd.to_numeric(raw[cum_col], errors="coerce") if cum_col in raw.columns else np.nan
        }))

    if not rows:
        raise ValueError("No product columns found in daily_records.json")

    records = pd.concat(rows).reset_index(drop=True)

    # --- holdings.json 読み込み ---
    holdings = load_holdings()
    if "account" not in holdings.columns:
        holdings["account"] = holdings.get("status", "Personal")
        holdings["status"] = np.where(
            holdings["account"].astype(str).str.lower().isin(["ideco", "nisa", "personal"]),
            "active",
            holdings.get("status", "active")
        )

    holdings["product"] = holdings["product"].map(PRODUCT_MAP)
    holdings["account"] = holdings["account"].fillna("Personal")
    holdings["status"] = holdings["status"].fillna("active")

    # ★ 型を強制的に数値化（重要）
    holdings["units"] = pd.to_numeric(holdings["units"], errors="coerce").fillna(0)

    return records, holdings

# ------------------------------------------------------------
# Today summary (P/L)
# ------------------------------------------------------------
def build_summary_market_daily(records):
    latest=records["market_date"].max()
    today=records[records["market_date"]==latest].copy()
    today["date"]=latest.strftime("%Y-%m-%d")
    today["prod_diff_yen_per_10k"]=today["nav"]*today["pct"]/100
    out=today[["product","date","nav","pct","prod_diff_yen_per_10k"]].rename(columns={"pct":"daily_pct"})
    write_output(out, "summary_market_daily.csv")
    return out

def build_summary_portfolio_pnl(records, holdings):
    latest = records["market_date"].max()
    today = records[records["market_date"] == latest]

    # 型正規化
    holdings = holdings.copy()
    # --- 起点日（Zero_date） ---
    holdings["Zero_date"] = pd.to_datetime(holdings["Zero_date"], errors="coerce")
    holdings["change_date"] = pd.to_datetime(holdings["change_date"], errors="coerce")
    holdings["change_value"] = pd.to_numeric(holdings["change_value"], errors="coerce")
    holdings["units"] = pd.to_numeric(holdings["units"], errors="coerce").fillna(0)


    # 通常商品行のみ
    holdings_prod = holdings[holdings["product"].notna()]

    df = today.merge(holdings_prod, on="product", how="inner")
    df = df[df["units"] > 0]

    # 現在評価額
    df["value"] = df["units"] * df["nav"] / 10000

    # 今日の損益（円）
    df["daily_pnl_yen"] = df["units"] * df["nav"] * df["pct"] / 100 / 10000

    # 前日比率（％）
    # = 今日の損益 ÷ 前日評価額
    # 前日評価額 = value - daily_pnl_yen
    df["daily_pnl_pct"] = np.where(
        (df["value"] - df["daily_pnl_yen"]) != 0,
        df["daily_pnl_yen"] / (df["value"] - df["daily_pnl_yen"]) * 100,
        np.nan
    )

    nav_by_product = records.sort_values("market_date")

    def lookup_base_nav(row):
        base_date = row["change_date"]
        if pd.isna(base_date):
            base_date = row["Zero_date"]
        if pd.isna(base_date):
            return np.nan

        available = nav_by_product[
            (nav_by_product["product"] == row["product"]) &
            (nav_by_product["market_date"] >= base_date) &
            (nav_by_product["nav"].notna())
        ]
        return available.iloc[0]["nav"] if not available.empty else np.nan

    df["base_nav"] = df.apply(lookup_base_nav, axis=1)

    # change_date 時点の評価額（CSV優先）
    df["base_value"] = np.where(
        df["change_value"].notna(),
        df["change_value"],
        df["units"] * df["base_nav"] / 10000
    )

    # スイッチング以降の損益
    df["since_change_pnl_yen"] = df["value"] - df["base_value"]
    df["since_change_pnl_pct"] = df["since_change_pnl_yen"] / df["base_value"] * 100

    out = df.assign(
        date = latest.strftime("%Y-%m-%d")
    )[[
        "product","account","status","date","units",
        "value",
        "daily_pnl_yen","daily_pnl_pct",
        "since_change_pnl_yen","since_change_pnl_pct"
    ]]

    write_output(out, "summary_portfolio_pnl.csv")
    return out

# ------------------------------------------------------------
# Daily trend (20)
# ------------------------------------------------------------
def build_daily_trend(records):
    p = records.pivot_table(
        index="market_date",
        columns="product",
        values="pct"
    ).sort_index().reindex(columns=PRODUCT_MAP.values())

    p = p.tail(10)

    # ★ date を先頭列に
    p = p.reset_index()
    p.insert(0, "date", p["market_date"].dt.strftime("%Y-%m-%d"))
    p = p.drop(columns=["market_date"])

    write_output(p, "daily_chart_data.csv")
    return p

def build_cum_daily_trend(records, holdings):
    df=records.sort_values("market_date")
    nav=df.pivot_table(index="market_date",columns="product",values="nav").sort_index()
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        s=nav[prod]
        base=s.groupby(s.index.year).transform("first")
        cum[prod]=(s/base-1)*100
    cum=cum.tail(10).reset_index()
    cum.insert(0,"date",cum["market_date"].dt.strftime("%Y-%m-%d"))
    cum=cum.drop(columns=["market_date"])
    write_output(cum, "cum_daily_chart_data.csv")
    return cum

# ------------------------------------------------------------
# Weekly trend
# ------------------------------------------------------------
def build_weekly_trend(records):
    df = records.copy()
    df["week"] = df["market_date"].dt.to_period("W-MON")

    weekly = df.groupby(["week","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product")

    latest_week = weekly.index.max()
    weeks = pd.period_range(end=latest_week, periods=12, freq="W-MON")
    weekly = weekly.reindex(weeks)

    weekly = weekly.reset_index()
    weekly.rename(columns={weekly.columns[0]: "week"}, inplace=True)
    weekly["week"] = weekly["week"].apply(lambda p: f"{p.start_time.strftime('%Y-%m-%d')} ~ {(p.start_time + pd.Timedelta(days=4)).strftime('%Y-%m-%d')}")

    write_output(weekly, "weekly_chart_data.csv")
    return weekly

def build_cum_weekly_trend(records, holdings):
    df=records.copy()
    df["week"]=df["market_date"].dt.to_period("W-MON")
    nav=df.groupby(["week","product"])["nav"].last().unstack("product")
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        s=nav[prod]
        years=s.index.to_timestamp().year
        base=s.groupby(years).transform("first")
        cum[prod]=(s/base-1)*100
    latest_week = nav.index.max()
    weeks = pd.period_range(end=latest_week, periods=12, freq="W-MON")
    cum = cum.reindex(weeks).reset_index()
    cum.rename(columns={cum.columns[0]: "week"}, inplace=True)
    cum["week"] = cum["week"].apply(lambda p: f"{p.start_time.strftime('%Y-%m-%d')} ~ {(p.start_time + pd.Timedelta(days=4)).strftime('%Y-%m-%d')}")

    write_output(cum, "cum_weekly_chart_data.csv")
    return cum


# ------------------------------------------------------------
# Monthly trend
# ------------------------------------------------------------
def build_monthly_trend(records):
    df = records.copy()
    df["month"] = df["market_date"].dt.to_period("M")

    monthly = df.groupby(["month","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product")

    monthly = monthly.reset_index()
    latest_month = monthly["month"].max()
    months = pd.period_range(end=latest_month, periods=12, freq="M")

    monthly = monthly.set_index("month").reindex(months).reset_index()
    monthly.rename(columns={monthly.columns[0]: "month"}, inplace=True)
    monthly["month"] = monthly["month"].apply(lambda p: p.strftime("%Y/%m"))

    write_output(monthly, "monthly_chart_data.csv")
    return monthly

def build_cum_monthly_trend(records, holdings):
    df=records.copy()
    df["month"]=df["market_date"].dt.to_period("M")
    nav=df.groupby(["month","product"])["nav"].last().unstack("product")
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        s=nav[prod]
        years=s.index.to_timestamp().year
        base=s.groupby(years).transform("first")
        cum[prod]=(s/base-1)*100
    latest_month = nav.index.max()
    months = pd.period_range(end=latest_month, periods=12, freq="M")
    cum = cum.reindex(months).reset_index()
    cum.rename(columns={cum.columns[0]: "month"}, inplace=True)
    cum["month"] = cum["month"].apply(lambda p: p.strftime("%Y/%m"))

    write_output(cum, "cum_monthly_chart_data.csv")

    return cum

# ------------------------------------------------------------
# iDeCo return (start_value -> current, CAGR)
# ------------------------------------------------------------

def build_ideco_return(records, holdings):
    latest = records["market_date"].max()

    account = holdings.get("account", holdings.get("status", "")).astype(str).str.lower()
    ideco = holdings[account == "ideco"].copy()
    if ideco.empty:
        return None

    ideco["units"] = pd.to_numeric(ideco["units"], errors="coerce").fillna(0)
    ideco["start"] = pd.to_datetime(ideco["start"], errors="coerce")

    ideco["start_value"] = pd.to_numeric(
        ideco["start_value"].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )

    start_date = ideco["start"].min()
    start_value = ideco["start_value"].sum()

    if pd.isna(start_date) or pd.isna(start_value):
        print("[WARN] iDeCo start_date or start_value is invalid")
        return None

    # ======================================================
    # 最新評価額
    # ======================================================
    nav_map = (
        records[records["market_date"] == latest]
        .set_index("product")["nav"]
        .to_dict()
    )

    ideco["nav"] = ideco["product"].map(nav_map)
    ideco["current_value"] = ideco["units"] * ideco["nav"] / 10000
    end_value = ideco["current_value"].sum()

    # ======================================================
    # CAGR（理論値）
    # ======================================================
    years = (latest - start_date).days / 365.25
    if years <= 0:
        return None

    total_return = (end_value / start_value - 1) * 100
    cagr = (end_value / start_value) ** (1 / years) - 1

    # ======================================================
    # XIRR（月次拠出キャッシュフロー）
    # ======================================================
    # 月数算出
    months = (
        (latest.year - start_date.year) * 12
        + (latest.month - start_date.month)
        + 1
    )

    if months <= 0:
        return None

    monthly_contribution = start_value / months

    cashflows = []

    # 月次拠出（マイナスCF）
    for i in range(months):
        d = (start_date + pd.DateOffset(months=i)).replace(day=1)
        if d <= latest:
            cashflows.append((d, -monthly_contribution))

    # 最終評価額（プラスCF）
    cashflows.append((latest, end_value))

    def xirr(flows, guess=0.05):
        def npv(rate):
            return sum(
                cf / (1 + rate) ** ((d - flows[0][0]).days / 365.25)
                for d, cf in flows
            )

        rate = guess
        for _ in range(100):
            f = npv(rate)
            df = sum(
                -cf * ((d - flows[0][0]).days / 365.25)
                / (1 + rate) ** (((d - flows[0][0]).days / 365.25) + 1)
                for d, cf in flows
            )
            if df == 0:
                break
            rate -= f / df
        return rate

    xirr_rate = xirr(cashflows)

    # ======================================================
    # 出力
    # ======================================================
    out = pd.DataFrame([{
        "type": "iDeCo",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": latest.strftime("%Y-%m-%d"),
        "years": round(years, 2),
        "months": months,
        "start_value": round(start_value, 0),
        "end_value": round(end_value, 0),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr * 100, 2),
        "xirr_monthly_cf_pct": round(xirr_rate * 100, 2)
    }])

    write_output(out, "summary_ideco_return.csv")

    return out

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------


# ============================================================
# Color
# ============================================================
COLOR_MAP = product_color_map()
VIEWER_PRODUCTS = viewer_products()

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
    records, holdings = load_source()
    ideco = build_ideco_return(records, holdings)
    if ideco is None:
        ideco = pd.DataFrame()

    return (
        build_summary_market_daily(records),
        build_summary_portfolio_pnl(records, holdings),
        build_daily_trend(records),
        build_cum_daily_trend(records, holdings),
        build_weekly_trend(records),
        build_cum_weekly_trend(records, holdings),
        build_monthly_trend(records),
        build_cum_monthly_trend(records, holdings),
        ideco,
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
    market = market[market["product"].isin(VIEWER_PRODUCTS)].copy()
    portfolio = portfolio[portfolio["product"].isin(VIEWER_PRODUCTS)].copy()
    products = [c for c in daily.columns if c != "date" and c in VIEWER_PRODUCTS]
    daily = daily[["date"] + products]
    cum_daily = cum_daily[["date"] + products]
    weekly = weekly[["week"] + products]
    cum_weekly = cum_weekly[["week"] + products]
    monthly = monthly[["month"] + products]
    cum_monthly = cum_monthly[["month"] + products]

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
        "elements:{bar:{borderRadius:0,borderSkipped:false}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'rectRounded',boxWidth:10,color:'#667085',font:{size:12,weight:'400'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:true,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:11,weight:'400'}}"
        "},"
        "y:{"
        "min:-6,"
        "max:6,"
        "ticks:{stepSize:1,color:'#98a2b3',font:{size:11,weight:'400'},callback:function(v){return (v>0?'+':'')+v.toFixed(0)+'%';}},"
        "title:{display:true,text:'Performance (%)',color:'#667085',font:{size:11,weight:'400'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false}"
        "}"
        "}"
        "}"
    )

    # ---------- BAR WEEKLY（±15% 固定・5%刻み） ----------
    AXIS_BAR_WEEKLY = (
        "options:{"
        "responsive:true,"
        "maintainAspectRatio:false,"
        "interaction:{mode:'index',intersect:false},"
        "layout:{padding:{top:18,bottom:12,left:6,right:10}},"
        "elements:{bar:{borderRadius:0,borderSkipped:false}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'rectRounded',boxWidth:10,color:'#667085',font:{size:12,weight:'400'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:true,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:11,weight:'400'}}"
        "},"
        "y:{"
        "min:-15,"
        "max:15,"
        "ticks:{stepSize:5,color:'#98a2b3',font:{size:11,weight:'400'},callback:function(v){return (v>0?'+':'')+v.toFixed(0)+'%';}},"
        "title:{display:true,text:'Performance (%)',color:'#667085',font:{size:11,weight:'400'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false}"
        "}"
        "}"
        "}"
    )

    # ---------- BAR MONTHLY（±25% 固定・5%刻み） ----------
    AXIS_BAR_MONTHLY = AXIS_BAR_WEEKLY.replace("min:-15,", "min:-25,").replace("max:15,", "max:25,")


    # ---------- LINE（Auto・Edge FIX） ----------
    AXIS_LINE = (
        "options:{"
        "responsive:true,"
        "maintainAspectRatio:false,"
        "interaction:{mode:'index',intersect:false},"
        "layout:{padding:{top:18,bottom:12,left:6,right:10}},"
        "elements:{line:{tension:0.28,borderWidth:3},point:{radius:0,hoverRadius:5,hitRadius:12}},"
        "plugins:{"
            "legend:{position:'top',align:'start',labels:{usePointStyle:true,pointStyle:'circle',boxWidth:10,color:'#667085',font:{size:12,weight:'400'},padding:16}},"
            "tooltip:{backgroundColor:'rgba(255,255,255,0.96)',titleColor:'#344054',bodyColor:'#344054',borderColor:'#d7dee8',borderWidth:1,padding:12,displayColors:true,cornerRadius:12,callbacks:{label:function(ctx){return ctx.dataset.label+': '+(ctx.parsed.y>0?'+':'')+ctx.parsed.y.toFixed(2)+'%';}}}"
        "},"
        "scales:{"
        "x:{"
        "offset:false,"
        "grid:{display:false,drawBorder:false},"
        "border:{display:false},"
        "ticks:{autoSkip:false,maxRotation:0,minRotation:0,color:'#98a2b3',font:{size:11,weight:'400'}}"
        "},"
        "y:{"
        "title:{display:true,text:'Cumulative (%)',color:'#667085',font:{size:11,weight:'400'}},"
        "grid:{display:true,color:'#edf2f7',lineWidth:1},"
        "border:{display:false},"
        "ticks:{color:'#98a2b3',font:{size:11,weight:'400'},callback:function(v){return (v>0?'+':'')+v.toFixed(1)+'%';}}"
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
                --bg-main:#f5f6f8;
                --card-bg:#ffffff;

                --text-main:#1f2933;
                --text-sub:#5f6b7a;
                --text-soft:#7b8794;

                --border:#d9dee7;
                --border-strong:#c5ccd8;

                --accent-pos:#2563eb;
                --accent-neg:#b42318;

                --shadow-sm:none;
                --shadow-md:none;
            }

            * { box-sizing:border-box; }

            body {
                background:var(--bg-main);
                font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif;
                padding:24px;
                color:var(--text-main);
                font-size:14px;
                line-height:1.55;
                letter-spacing:0;
                -webkit-font-smoothing:antialiased;
                -moz-osx-font-smoothing:grayscale;
                text-rendering:optimizeLegibility;
            }

            .card {
                background:var(--card-bg);
                padding:20px 22px;
                border-radius:4px;
                margin-bottom:18px;
                border:1px solid var(--border);
                box-shadow:var(--shadow-md);
            }

            h2 {
                font-size:18px;
                margin-bottom:14px;
                font-weight:400;
                color:var(--text-main);
                letter-spacing:0;
            }

            h3 {
                font-size:15px;
                font-weight:400;
                color:var(--text-main);
                letter-spacing:0;
            }

            table {
                width:100%;
                border-collapse:separate;
                border-spacing:0;
                font-variant-numeric:tabular-nums;
            }

            th, td {
                padding:10px 12px;
                border-bottom:1px solid var(--border);
                font-size:14px;
                line-height:1.45;
                text-align:right;
                color:var(--text-main);
            }

            th {
                font-weight:400;
                font-size:12px;
                letter-spacing:0;
                text-transform:none;
                color:var(--text-soft);
            }

            td { font-weight:400; }

            tr:hover td {
                background:#f8fafc;
            }

            th:first-child,
            td:first-child { text-align:left; }

            .chart-container {
                width:100%;
                height:420px;
                margin-top:8px;
                padding:14px 12px 8px 12px;
                border-radius:4px;
                background:#ffffff;
                border:1px solid var(--border);
                box-shadow:var(--shadow-sm) inset;
            }

            .chart-container canvas {
                width:100% !important;
                height:100% !important;
            }

            summary {
                cursor:pointer;
                font-size:16px;
                font-weight:400;
                color:var(--text-main);
                list-style:none;
                letter-spacing:0;
            }

            summary::-webkit-details-marker {
                display:none;
            }

            .highlight {
                font-weight:400;
                color:var(--text-main);
            }

            .section-title {
                position:relative;
                display:inline-flex;
                align-items:center;
                gap:8px;
                padding:4px 10px 4px 0;
                font-size:18px;
                font-weight:400;
                color:var(--text-main);
                letter-spacing:0;
                border-bottom:1px solid var(--border-strong);
            }

            .section-title::before {
                content:"";
                display:inline-block;
                width:3px;
                height:18px;
                background:#2563eb;
            }

            /* +/- coloring */
            .pos { color: var(--accent-pos); font-weight: 400; }
            .neg { color: var(--accent-neg); font-weight: 400; }

            /* key metrics (iDeCo) */
            .key-metric { font-size: 16px; font-weight: 400; color: var(--text-main); letter-spacing:0; }
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
<tr><th>Product</th><th>Account</th><th>Units</th><th>Value ¥</th><th>Daily ¥</th><th>Since ¥</th><th>Since %</th></tr>"""
    for _, r in portfolio.iterrows():
        cls_daily = sign_class(r.get("daily_pnl_yen"))
        cls_since_y = sign_class(r.get("since_change_pnl_yen"))
        cls_since_p = sign_class(r.get("since_change_pnl_pct"))

        html += (
            f"<tr><td>{r['product']}</td>"
            f"<td>{r.get('account', '')}</td>"
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

    html += chart(f"Weekly Performance ({YEAR})", "w1", weekly_labels, bar_ds(weekly), AXIS_BAR_WEEKLY)
    html += chart(f"Weekly Cumulative ({YEAR})", "w2", weekly_labels_cum, line_ds(cum_weekly), AXIS_LINE)

    html += chart(f"Monthly Performance ({MONTHLY_YEAR_LABEL})", "m1", monthly_labels, bar_ds(monthly), AXIS_BAR_MONTHLY)
    html += chart(f"Monthly Cumulative ({MONTHLY_YEAR_LABEL})", "m2", cum_monthly_labels, line_ds(cum_monthly), AXIS_LINE)

    html += "</body></html>"

    (BASE / "dashboard.html").write_text(html, encoding="utf-8")


# ============================================================
# MAIN
# ============================================================


# ==========================================================
# Unified CLI
# ==========================================================
def generate_dashboard():
    build_html(*load_data())
    print("=== DASHBOARD HTML GENERATED ===")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        nargs="*",
        metavar="PRODUCT",
        help="Backfill historical NAV from embedded Rakuten chart data. Use product short name, display name, fund_id, or all.",
    )
    parser.add_argument(
        "--skip-latest",
        action="store_true",
        help="Skip latest online fetch and only rebuild dashboard/backfill.",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only rebuild dashboard.html from local records.",
    )
    args = parser.parse_args()

    if args.backfill is not None:
        print("\n=== BACKFILL HISTORY ===")
        backfill_histories(args.backfill)

    if not args.skip_latest and not args.build_only:
        print("\n=== FETCH ONLINE DATA ===")
        raw = fetch_raw()

        print("\n=== UPDATE RECORDS ===")
        update_records(raw)

    print("\n=== BUILD DASHBOARD ===")
    generate_dashboard()

    print("\n=== COMPLETED ===\n")


if __name__ == "__main__":
    main()
