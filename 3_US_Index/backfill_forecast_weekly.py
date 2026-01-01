#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build Weekly Trend Dataset (Backfill / FULL HORIZONTAL)

- 1 row = week
- QQQ / SP500 are fully horizontal
- single + cumulative
"""

import pandas as pd
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

LOG_PATH = DATA_DIR / "forecast_evaluation_log_Backfill.csv"
OUT_PATH = DATA_DIR / "forecast_trend_weekly_Backfill.csv"

# =========================================================
# LOAD
# =========================================================
df = pd.read_csv(
    LOG_PATH,
    parse_dates=["as_of_date"]
)

df = df[df["target"].isin(["QQQ", "SP500"])].copy()

# =========================================================
# WEEK BUCKET
# =========================================================
df["week"] = (
    df["as_of_date"]
    .dt.to_period("W")
    .apply(lambda r: r.start_time)
)

# =========================================================
# FUNCTION : BUILD PER ASSET
# =========================================================
def build_asset_block(df_asset, prefix):
    p_pred = df_asset.pivot_table(
        index="week",
        columns="horizon",
        values="pred_sum",
        aggfunc="mean"
    ).rename(columns={
        "1W": f"{prefix}_pred_1w",
        "1M": f"{prefix}_pred_1m",
    })

    p_act = df_asset.pivot_table(
        index="week",
        columns="horizon",
        values="actual_sum",
        aggfunc="mean"
    ).rename(columns={
        "1W": f"{prefix}_actual_1w",
        "1M": f"{prefix}_actual_1m",
    })

    block = p_pred.join(p_act, how="outer").sort_index()

    # cumulative
    for c in block.columns:
        block[f"{c}_cum"] = block[c].cumsum()

    return block

# =========================================================
# BUILD BLOCKS
# =========================================================
qqq = build_asset_block(df[df["target"] == "QQQ"], "qqq")
sp  = build_asset_block(df[df["target"] == "SP500"], "sp")

# =========================================================
# MERGE HORIZONTAL
# =========================================================
trend = (
    qqq
    .join(sp, how="outer")
    .reset_index()
    .sort_values("week")
)

# =========================================================
# COLUMN ORDER（明示）
# =========================================================
trend = trend[[
    "week",

    "qqq_pred_1w", "qqq_pred_1w_cum",
    "qqq_actual_1w", "qqq_actual_1w_cum",

    "qqq_pred_1m", "qqq_pred_1m_cum",
    "qqq_actual_1m", "qqq_actual_1m_cum",

    "sp_pred_1w", "sp_pred_1w_cum",
    "sp_actual_1w", "sp_actual_1w_cum",

    "sp_pred_1m", "sp_pred_1m_cum",
    "sp_actual_1m", "sp_actual_1m_cum",
]]

# =========================================================
# SAVE
# =========================================================
trend.to_csv(
    OUT_PATH,
    index=False,
    encoding="utf-8-sig"
)

print("=== WEEKLY TREND (FULL HORIZONTAL) GENERATED ===")
print(f"File : {OUT_PATH.name}")
print(f"Rows : {len(trend)}")
print(f"From : {trend['week'].min().date()}")
print(f"To   : {trend['week'].max().date()}")
