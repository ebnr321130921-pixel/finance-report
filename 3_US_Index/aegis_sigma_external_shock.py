#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Decision Tables Builder
(Aegis-Sigma Decision Layer / FINAL)

Input:
- forecast_trend_weekly.csv

Generated (single source of truth):
- aegis_sigma_diagnostics.csv

Output:
- market_decision_current.csv
- market_decision_chart_weekly.csv

Purpose:
- Human-readable shock classification
- Noise suppression
- External shock detection (historical-invariant score)
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
trend = pd.read_csv(TREND_PATH, parse_dates=["week"]).sort_values("week")

# =========================================================
# BUILD AEGIS-SIGMA DIAGNOSTICS (REPRODUCIBLE / NO RESET)
#   - source : forecast_trend_weekly.csv
#   - method : global sigma on cumulative error (validated)
# =========================================================

sigma_records = []

for asset in ["qqq", "sp"]:
    for hz in ["1w", "1m"]:

        pred_col = f"{asset}_pred_{hz}_cum_nrst"
        act_col  = f"{asset}_actual_{hz}_cum_nrst"

        if pred_col not in trend.columns or act_col not in trend.columns:
            continue

        # --- cumulative error (no reset) ---
        err = trend[act_col] - trend[pred_col]

        # --- rolling sigma (26 weeks, legacy-compatible) ---
        sigma_26 = err.rolling(26, min_periods=26).std()

        # --- shock score ---
        shock_score = err.abs() / sigma_26

        # --- rolling percentile base (last 5 years = 260 weeks) ---
        WINDOW_PCTL = 260
        p95 = shock_score.rolling(WINDOW_PCTL, min_periods=WINDOW_PCTL).quantile(0.95)
        p99 = shock_score.rolling(WINDOW_PCTL, min_periods=WINDOW_PCTL).quantile(0.99)

        tmp = pd.DataFrame({
            "week": trend["week"],
            f"{asset}_{hz}_error": err,
            f"{asset}_{hz}_sigma": sigma_26,
            f"{asset}_{hz}_shock_score": shock_score,
            f"{asset}_{hz}_p95": p95,
            f"{asset}_{hz}_p99": p99,
            f"{asset}_{hz}_shock_p95_flag": shock_score >= p95,
            f"{asset}_{hz}_shock_p99_flag": shock_score >= p99,
        })

        sigma_records.append(tmp)

# --- 横結合 ---
diag = sigma_records[0]
for d in sigma_records[1:]:
    diag = diag.merge(d, on="week", how="outer")

diag = diag.sort_values("week").reset_index(drop=True)

# --- SAVE (single source of truth) ---
# aegis_sigma_diagnostics.csv contains:
# - *_error
# - *_shock_score
# - *_external_shock (legacy-compatible boolean flag)
diag.to_csv(
    DIAG_PATH,
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# MERGE TREND × SIGMA
# =========================================================
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


def shock_flag(score, threshold=3.0):
    """
    Binary external shock flag (legacy-compatible)
    """
    if pd.isna(score):
        return False
    return score >= threshold


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

            p95_col = f"{asset}_{hz}_p95"
            p99_col = f"{asset}_{hz}_p99"

            p95_val = r.get(p95_col)
            p99_val = r.get(p99_col)

            if pd.isna(score) or pd.isna(p95_val) or pd.isna(p99_val):
                ext_flag = False
                rank_adj = "NORMAL RANGE"
            elif score >= p99_val:
                ext_flag = True
                rank_adj = "EXTREME DISTORTION (P99)"
            elif score >= p95_val:
                ext_flag = False
                rank_adj = "ELEVATED DISTORTION (P95)"
            else:
                ext_flag = False
                rank_adj = "NORMAL RANGE"

            records.append({
                "week": week_start,
                "asset": asset.upper(),
                "horizon": hz.upper(),
                "start_date": week_start,
                "end_date": week_end,
                "shock_score": score,
                "shock_rank": rank_adj,               
            })


base_df = pd.DataFrame(records)

# =========================================================
# ① CURRENT WEEK TABLE（Viewer用）
# =========================================================
# 最新の「実績が確定している週」を取得
# shock_score が NaN でない行だけを見る（列存在前提を捨てる）
# --- guard: shock_score 列 or 有効データが存在しない場合 ---
if "shock_score" not in base_df.columns:
    latest_week = pd.NaT
else:
    valid = base_df.loc[base_df["shock_score"].notna(), "week"]
    latest_week = valid.max() if not valid.empty else pd.NaT


if pd.isna(latest_week):
    current_df = pd.DataFrame(columns=[
        "asset",
        "horizon",
        "start_date",
        "end_date",
        "shock_score",
        "shock_rank",
    ])
else:
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
    .sort_index()   # ← 累積しない（ノーリセット＝元系列をそのまま）
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
