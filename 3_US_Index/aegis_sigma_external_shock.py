#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Decision Tables Builder
(Aegis-Sigma Decision Layer / FINAL)

Input:
- forecast_trend_weekly.csv
- aegis_sigma_diagnostics.csv

Output:
- market_decision_current.csv
- market_decision_chart_weekly.csv

Purpose:
- Human-readable shock classification
- Noise suppression
- Yearly-level external event detection
"""

import pandas as pd
from pathlib import Path
from pandas.tseries.offsets import BDay

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

TREND_PATH = DATA_DIR / "forecast_trend_weekly.csv"
DIAG_PATH  = DATA_DIR / "aegis_sigma_diagnostics.csv"

OUT_CURRENT = DATA_DIR / "market_decision_current.csv"
OUT_CHART   = DATA_DIR / "market_decision_chart_weekly.csv"

ASSETS   = ["qqq", "sp"]
HORIZONS = ["1w", "1m"]

# =========================================================
# LOAD
# =========================================================
trend = pd.read_csv(TREND_PATH, parse_dates=["week"])
diag  = pd.read_csv(DIAG_PATH,  parse_dates=["week"])

df = (
    trend
    .merge(diag, on="week", how="left")
    .sort_values("week")
    .reset_index(drop=True)
)

# =========================================================
# HELPERS
# =========================================================

def shock_rank(score):
    """
    Human-readable shock classification

    < 2.0  : Normal (historical noise range)
    2.0-3.0: Early disturbance (warning)
    >= 3.0 : External shock (rare event)
    """
    if pd.isna(score):
        return "NORMAL RANGE"
    if score < 2.0:
        return "NORMAL RANGE"
    if score < 3.0:
        return "EARLY DISTURBANCE"
    return "EXTERNAL SHOCK"


# =========================================================
# BUILD BASE RECORDS
# =========================================================
records = []

for _, r in df.iterrows():

    week_start = r["week"]
    week_end   = week_start + 4 * BDay()  # Mon → Fri

    for asset in ASSETS:
        for hz in HORIZONS:

            err_col   = f"{asset}_{hz}_error"
            score_col = f"{asset}_{hz}_shock_score"

            if err_col not in df.columns:
                continue

            err   = r.get(err_col)
            score = r.get(score_col)

            rank = shock_rank(score)

            records.append({
                "week": week_start,
                "asset": asset.upper(),
                "horizon": hz.upper(),
                "start_date": week_start,
                "end_date": week_end,
                "shock_score": score,
                "shock_rank": rank,
            })

base_df = pd.DataFrame(records)

# =========================================================
# ① CURRENT WEEK TABLE（Viewer用）
# =========================================================
# 最新の「実績が確定している週」を取得
latest_week = (
    base_df
    .dropna(subset=["shock_score"])
    ["week"]
    .max()
)

current_df = (
    base_df[base_df["week"] == latest_week]
    .assign(
        asset_order=lambda x: x["asset"].map({"QQQ": 0, "SP": 1}),
        horizon_order=lambda x: x["horizon"].map({"1W": 0, "1M": 1}),
    )
    .sort_values(["asset_order", "horizon_order"])
    .reset_index(drop=True)
)

current_df[[
    "asset",
    "horizon",
    "start_date",
    "end_date",
    "shock_score",
    "shock_rank",
]].to_csv(
    OUT_CURRENT,
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# ② CHART WEEKLY TABLE（列分離・SP / QQQ）
# =========================================================
chart_df = (
    base_df
    .pivot_table(
        index="week",
        columns=["asset", "horizon"],
        values="shock_score"
    )
    .sort_index()
)

# --- flatten MultiIndex columns ---
chart_df.columns = [
    f"{asset}_{horizon}_shock_score"
    for asset, horizon in chart_df.columns
]

chart_df = chart_df.reset_index()

chart_df.to_csv(
    OUT_CHART,
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# LOG
# =========================================================
print("=== Market Decision Tables BUILT ===")
print(f"Current : {OUT_CURRENT.name}")
print(f"Chart   : {OUT_CHART.name}")
print(f"Latest week : {latest_week.date()}")
