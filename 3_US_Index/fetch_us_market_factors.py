#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Factors Raw Data Fetcher (FINAL / SEMANTICALLY CORRECT)

【仕様】
1. US土日祝日はカレンダーで削除
2. 最新行のみ：
   - 為替・VIX以外で欠損が3以上なら削除
3. 残ったデータのみ前日で補完（ffill）
4. US市場開始後は最新日が自然に追加される
5. 毎回同じCSVに上書き
6. 更新時刻を保持

date = US取引日（ET）
updated_at_utc = 最終更新時刻（UTC）
"""

import yfinance as yf
import pandas as pd
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

US_EQUITY_COLS = ["SP500", "NASDAQ", "DOW", "SPY", "QQQ", "SOX"]
EXCLUDE_LATEST_CHECK = {"date", "USDJPY", "VIX"}
MAX_MISSING_LATEST = 3
MIN_HISTORY_ROWS = 252
MAX_DATA_AGE_DAYS = 10

TICKERS = {
    "QQQ":    {"ticker": "QQQ",   "kind": "ETF"},
    "SOX":    {"ticker": "^SOX",  "kind": "INDEX"},
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
# NYSE CALENDAR
# =========================================================
def get_nyse_holidays(start: str, end: str) -> set:
    """
    NYSE休場日を取得
    失敗時は土日判定のみ
    """
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        sched = nyse.schedule(start_date=start, end_date=end)
        open_days = sched.index.normalize()
        all_days = pd.date_range(start=start, end=end, freq="D")
        holidays = all_days.difference(open_days)
        return set(d.date() for d in holidays)
    except Exception:
        all_days = pd.date_range(start=start, end=end, freq="D")
        weekends = all_days[all_days.weekday >= 5]
        return set(d.date() for d in weekends)

# =========================================================
# UTIL
# =========================================================
def extract_price(raw: pd.DataFrame) -> pd.Series:
    for col in ("Adj Close", "Close"):
        if col in raw.columns:
            s = raw[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            if getattr(s.index, "tz", None) is not None:
                s.index = s.index.tz_localize(None)
            return s
    raise RuntimeError("Price column not found")

# =========================================================
# FETCH
# =========================================================
def fetch_one(name: str, info: dict) -> pd.DataFrame:
    try:
        if info["kind"] == "INDEX":
            raw = yf.Ticker(info["ticker"]).history(
                start=START_DATE,
                auto_adjust=False
            )
        else:
            raw = yf.download(
                info["ticker"],
                start=START_DATE,
                auto_adjust=True,
                progress=False
            )
    except Exception:
        return pd.DataFrame()

    if raw.empty:
        return pd.DataFrame()

    try:
        price = extract_price(raw)
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame({name: price}, index=price.index)

def fetch_full() -> pd.DataFrame:
    dfs = []
    missing = []
    for name, info in TICKERS.items():
        df = fetch_one(name, info)
        if not df.empty:
            dfs.append(df)
        else:
            missing.append(name)

    if not dfs:
        raise RuntimeError(
            "No market data could be fetched. Check network/DNS access to Yahoo Finance."
        )

    # A partial download must never replace the last known-good database.  Every
    # configured series is used by the feature/model pipeline, either directly
    # or through a derived return, so "warn and continue" creates an unusable
    # raw file and makes the following pipeline step fail.
    if missing:
        raise RuntimeError(
            "Incomplete market download; keeping the existing raw CSV. "
            f"Missing tickers: {', '.join(missing)}"
        )

    df = pd.concat(dfs, axis=1, sort=True).sort_index()

    df = df.reset_index()
    if df.columns[0] != "date":
        df = df.rename(columns={df.columns[0]: "date"})

    return df

# =========================================================
# FINALIZE
# =========================================================
def finalize_raw(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)

    # -------------------------------------------------
    # ① カレンダーでUS休場日削除
    # -------------------------------------------------
    holidays = get_nyse_holidays(
        df["date"].min().strftime("%Y-%m-%d"),
        df["date"].max().strftime("%Y-%m-%d"),
    )
    df = df[~df["date"].dt.date.isin(holidays)].reset_index(drop=True)

    # -------------------------------------------------
    # ② 最新行の中途半端チェック
    # -------------------------------------------------
    if len(df) > 0:
        latest = df.iloc[-1]
        check_cols = [
            c for c in df.columns
            if c not in EXCLUDE_LATEST_CHECK
        ]
        missing = latest[check_cols].isna().sum()
        if missing >= MAX_MISSING_LATEST:
            df = df.iloc[:-1]

    # -------------------------------------------------
    # ③ 残ったデータのみ ffill
    # -------------------------------------------------
    fill_cols = [c for c in df.columns if c != "date"]
    df[fill_cols] = df[fill_cols].ffill()

    required_cols = {"date", *TICKERS.keys()}
    missing_cols = sorted(required_cols.difference(df.columns))
    if missing_cols:
        raise RuntimeError(
            "Raw data validation failed; missing columns: "
            + ", ".join(missing_cols)
        )
    if len(df) < MIN_HISTORY_ROWS:
        raise RuntimeError(
            f"Raw data validation failed; only {len(df)} rows were fetched"
        )
    if df["date"].duplicated().any() or not df["date"].is_monotonic_increasing:
        raise RuntimeError("Raw data validation failed; dates are not unique and sorted")
    if df[list(TICKERS)].isna().any().any():
        bad = df[list(TICKERS)].columns[df[list(TICKERS)].isna().any()].tolist()
        raise RuntimeError(
            "Raw data validation failed; unfillable values remain in: "
            + ", ".join(bad)
        )

    return df


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV without exposing a partially written/invalid database."""
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_freshness(df: pd.DataFrame) -> None:
    latest = pd.Timestamp(df["date"].max()).date()
    today_utc = datetime.now(timezone.utc).date()
    if latest > today_utc + timedelta(days=1):
        raise RuntimeError(
            f"Raw data validation failed; latest date {latest} is in the future"
        )
    age = (today_utc - latest).days
    if age > MAX_DATA_AGE_DAYS:
        raise RuntimeError(
            f"Raw data validation failed; latest market date {latest} is "
            f"{age} days old. Keeping the existing raw CSV."
        )

# =========================================================
# MAIN
# =========================================================
def main():
    print("=== BUILD MARKET FACTORS RAW (SEMANTICALLY CORRECT) ===")

    df = fetch_full()
    df = finalize_raw(df)
    validate_freshness(df)

    updated_at = datetime.now(timezone.utc).isoformat()
    df["updated_at_utc"] = updated_at

    atomic_write_csv(df, DB_PATH)

    print(f"[SAVE] {DB_PATH}")
    print(f"[ROWS] {len(df)}")
    print(f"[UPDATED_AT_UTC] {updated_at}")
    print("======================================================")

if __name__ == "__main__":
    main()
