#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backfill Forecast Evaluation Log (SAFE / FULL)

- 過去3ヶ月分の予測を現行モデルで生成
- as_of_date は raw データ基準（今日まで）
- actual / error も Backfill 時点で計算
- 出力は Backfill 専用 CSV
"""

import pandas as pd
import numpy as np
from pathlib import Path
import statsmodels.api as sm
from pandas.tseries.offsets import CustomBusinessDay
from pandas.tseries.holiday import USFederalHolidayCalendar

# =========================================================
# BUSINESS DAY (US MARKET)
# =========================================================
US_BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

REG_DATA_PATH = DATA_DIR / "market_regression_dataset.csv"
RAW_DATA_PATH = DATA_DIR / "market_factors_raw.csv"
OUT_LOG_PATH  = DATA_DIR / "forecast_evaluation_log_Backfill.csv"

# =========================================================
# LOAD DATA
# =========================================================
df = pd.read_csv(REG_DATA_PATH, parse_dates=["date"]).sort_values("date")
raw = pd.read_csv(RAW_DATA_PATH, parse_dates=["date"]).sort_values("date")

raw_px = raw.set_index("date")

# =========================================================
# TARGET DEFINITIONS
# =========================================================
TARGET_MAP = {
    ("QQQ",   "1W"): "QQQ_1W_FWD_SUM",
    ("QQQ",   "1M"): "QQQ_1M_FWD_SUM",
    ("SP500", "1W"): "SP500_1W_FWD_SUM",
    ("SP500", "1M"): "SP500_1M_FWD_SUM",
}

TARGET_COLS = list(TARGET_MAP.values())

# =========================================================
# FEATURE COLUMNS
# =========================================================
FEATURE_COLS = [
    c for c in df.columns
    if c not in ["date"] and c not in TARGET_COLS
]

df[FEATURE_COLS] = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")

# =========================================================
# BACKFILL RANGE（raw 基準）
# =========================================================
end_date = raw["date"].max().normalize()

# ★ 固定開始日（過去予測を再現するため）
start_date = pd.Timestamp("2015-01-01")

as_of_dates = pd.date_range(
    start=start_date,
    end=end_date,
    freq=US_BDAY
)

# =========================================================
# TRAIN MODELS（1回のみ）
# =========================================================
models = {}
for (asset, horizon), target_col in TARGET_MAP.items():

    # --- y がある行に限定 ---
    train = df.dropna(subset=[target_col]).copy()

    # --- X / y を完全同期でクリーン ---
    train = train.replace([np.inf, -np.inf], np.nan)
    train = train.dropna(subset=FEATURE_COLS + [target_col])

    if train.empty:
        continue

    X = sm.add_constant(train[FEATURE_COLS], has_constant="add")
    y = train[target_col]

    models[(asset, horizon)] = sm.OLS(y, X).fit()

# =========================================================
# ACTUAL CALC FUNCTION
# =========================================================
def calc_actual_sum(start, end, col):
    try:
        px = raw_px.loc[start:end, col]
    except KeyError:
        return np.nan
    if px.isna().any() or len(px) < 2:
        return np.nan
    return px.pct_change().dropna().sum()

# =========================================================
# BUILD BACKFILL LOG
# =========================================================
rows = []

for as_of in as_of_dates:

    hist = df[df["date"] <= as_of]
    if len(hist) == 0:
        continue

    latest_X = sm.add_constant(
        hist[FEATURE_COLS].iloc[[-1]],
        has_constant="add"
    )

    p1w_start = as_of + 5 * US_BDAY
    p1w_end   = p1w_start + 4 * US_BDAY

    p1m_start = as_of + 20 * US_BDAY
    p1m_end   = p1m_start + 19 * US_BDAY

    for (asset, horizon), model in models.items():

        pred = float(model.predict(latest_X).iloc[0])

        if asset == "QQQ":
            col = "QQQ"
        else:
            col = "SP500"

        if horizon == "1W":
            actual = calc_actual_sum(p1w_start, p1w_end, col)
        else:
            actual = calc_actual_sum(p1m_start, p1m_end, col)

        error = actual - pred if pd.notna(actual) else np.nan

        rows.append({
            "as_of_date": as_of,
            "target": asset,
            "horizon": horizon,
            "start_date": p1w_start if horizon == "1W" else p1m_start,
            "end_date":   p1w_end   if horizon == "1W" else p1m_end,
            "pred_sum": pred,
            "actual_sum": actual,
            "error": error,
        })

# =========================================================
# SAVE
# =========================================================
MAIN_LOG_PATH = DATA_DIR / "forecast_evaluation_log.csv"

out_df = (
    pd.DataFrame(rows)
    .sort_values(["as_of_date", "target", "horizon"])
    .reset_index(drop=True)
)

if MAIN_LOG_PATH.exists():
    old = pd.read_csv(
        MAIN_LOG_PATH,
        parse_dates=["as_of_date", "start_date", "end_date"]
    )
    merged = pd.concat([old, out_df], ignore_index=True)
else:
    merged = out_df

merged = (
    merged
    .drop_duplicates(
        subset=["as_of_date", "target", "horizon"],
        keep="last"
    )
    .sort_values(["as_of_date", "target", "horizon"])
    .reset_index(drop=True)
)

merged.to_csv(
    MAIN_LOG_PATH,
    index=False,
    encoding="utf-8-sig"
)

print("=== BACKFILL COMPLETED & MERGED ===")
print(f"File : {MAIN_LOG_PATH.name}")
print(f"Rows : {len(merged)}")
print(f"From : {merged['as_of_date'].min().date()}")
print(f"To   : {merged['as_of_date'].max().date()}")
