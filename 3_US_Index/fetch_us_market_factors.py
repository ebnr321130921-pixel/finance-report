#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Factors Raw Data Fetcher (FINAL / FACT ONLY)

【Raw の定義】
- US市場で実際に取引され、データが存在する日だけ
- 土日・祝日・未確定日は結果ベースで除外
- 前日コピー（ffill）で行を作らない
- Raw は「事実テーブル」

【除外ルール】
- 為替以外の指数が前日と完全一致している行は削除
"""

import yfinance as yf
import pandas as pd
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "market_factors_raw.csv"

# =========================================================
# CONFIG
# =========================================================
START_DATE = "2005-01-01"
FX_COL = "USDJPY"

TICKERS = {
    "QQQ":    {"ticker": "QQQ",   "kind": "ETF"},
    "SP500":  {"ticker": "^GSPC", "kind": "INDEX"},
    "VIX":    {"ticker": "^VIX",  "kind": "INDEX"},
    "US10Y":  {"ticker": "^TNX",  "kind": "INDEX"},
    "USDJPY": {"ticker": "JPY=X", "kind": "FX"},
    "GOLD":   {"ticker": "GLD",   "kind": "ETF"},
    "TLT":    {"ticker": "TLT",   "kind": "ETF"},
    "DOW":    {"ticker": "^DJI",  "kind": "INDEX"},
    "NASDAQ": {"ticker": "^IXIC", "kind": "INDEX"},
    "SPY":    {"ticker": "SPY",   "kind": "ETF"},
}

# =========================================================
# UTIL
# =========================================================
def extract_price(raw: pd.DataFrame) -> pd.Series:
    for col in ("Close", "Adj Close"):
        if col in raw.columns:
            s = raw[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            return s
    raise RuntimeError("Price column not found")

# =========================================================
# FETCH
# =========================================================
def fetch_one(name: str, info: dict, start_date: str) -> pd.DataFrame:
    print(f"  - downloading {name}")

    try:
        if info["kind"] == "INDEX":
            raw = yf.Ticker(info["ticker"]).history(
                start=start_date,
                auto_adjust=False
            )
        else:
            raw = yf.download(
                info["ticker"],
                start=start_date,
                auto_adjust=True,
                progress=False
            )
    except Exception as e:
        print(f"    ⚠ fetch failed: {e}")
        return pd.DataFrame()

    if raw.empty:
        return pd.DataFrame()

    try:
        price = extract_price(raw)
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame({name: price.values}, index=price.index)


def fetch_full() -> pd.DataFrame:
    dfs = []

    print(f"[FETCH] {START_DATE} -> latest available")

    for name, info in TICKERS.items():
        df = fetch_one(name, info, START_DATE)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        raise RuntimeError("No data fetched")

    return pd.concat(dfs, axis=1)

# =========================================================
# RAW FINALIZE（ここが肝）
# =========================================================
def finalize_raw(df: pd.DataFrame) -> pd.DataFrame:
    """
    Raw = 実データが存在する日だけ
    + 為替以外が前日と同じ行は削除
    """
    df = df.sort_index()

    # 全列 NaN の日は除外
    df = df.dropna(how="all")

    # 為替以外の列
    non_fx_cols = [c for c in df.columns if c != FX_COL]

    # 前日との差分
    diff = df[non_fx_cols].diff()

    # 「全て差分ゼロ or NaN」= 市場が動いていない
    same_as_prev = diff.fillna(0).eq(0).all(axis=1)

    # 先頭行は必ず残す
    same_as_prev.iloc[0] = False

    # 不要行を削除
    df = df.loc[~same_as_prev]

    return (
        df.reset_index()
          .rename(columns={"index": "date"})
    )

# =========================================================
# MAIN
# =========================================================
def main():
    print("=== BUILD MARKET FACTORS RAW (FACT ONLY) ===")

    # ① フル取得
    df = fetch_full()

    # ② Raw を確定（結果ベースで除外）
    df = finalize_raw(df)

    # ③ 保存
    df.to_csv(DB_PATH, index=False)
    print(f"[SAVE] {DB_PATH}")
    print(f"[ROWS] {len(df)}")
    print("===========================================")


if __name__ == "__main__":
    main()
