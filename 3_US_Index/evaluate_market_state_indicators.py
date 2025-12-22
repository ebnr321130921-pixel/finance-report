#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market State Indicator Validity Evaluation (FINAL / ROBUST)

Purpose:
- MRDI / RiskScore が本当に「効いている指標」かを事後検証する
- 方向性ではなく「イベント検知能力」を評価
- lag（当日〜数日前）の有効性を確認

NO fitting / NO prediction
Pure empirical evaluation
"""

import pandas as pd
import numpy as np
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RAW_PATH    = DATA_DIR / "market_factors_raw.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"

OUT_SUMMARY = DATA_DIR / "mrdi_validity_summary.csv"
OUT_LAG     = DATA_DIR / "mrdi_lag_evaluation.csv"

# =========================================================
# LOAD RAW（date揺れ完全耐性）
# =========================================================
raw = pd.read_csv(RAW_PATH)

date_candidates = ["date", "Date", "datetime", "timestamp", "trade_date"]
date_col = next((c for c in date_candidates if c in raw.columns), None)

if date_col is None:
    raise ValueError(
        f"[ERROR] No date column found in RAW. columns={raw.columns.tolist()}"
    )

raw[date_col] = pd.to_datetime(raw[date_col])
raw = (
    raw.rename(columns={date_col: "date"})
       .sort_values("date")
       .reset_index(drop=True)
)

print(f"[INFO] RAW date column detected as '{date_col}'")

# =========================================================
# LOAD METRICS（date必須）
# =========================================================
metrics = pd.read_csv(METRIC_PATH)

if "date" not in metrics.columns:
    raise ValueError("[ERROR] metrics CSV must contain 'date' column")

metrics["date"] = pd.to_datetime(metrics["date"])
metrics = metrics.sort_values("date").reset_index(drop=True)

# =========================================================
# MERGE
# =========================================================
df = pd.merge(raw, metrics, on="date", how="inner")

print(f"[INFO] merged rows: {len(df)}")

# =========================================================
# RETURNS
# =========================================================
df["RET_QQQ_1D"]  = df["QQQ"].pct_change()
df["RET_QQQ_5D"]  = df["QQQ"].pct_change(5)
df["RET_QQQ_20D"] = df["QQQ"].pct_change(20)

# =========================================================
# BIG MOVE DEFINITIONS
# =========================================================
thr_1d  = df["RET_QQQ_1D"].abs().quantile(0.99)
thr_5d  = df["RET_QQQ_5D"].abs().quantile(0.97)
thr_20d = df["RET_QQQ_20D"].abs().quantile(0.95)

df["BigMove_1D"]  = df["RET_QQQ_1D"].abs()  > thr_1d
df["BigMove_5D"]  = df["RET_QQQ_5D"].abs()  > thr_5d
df["BigMove_20D"] = df["RET_QQQ_20D"].abs() > thr_20d

BASE_1D  = df["BigMove_1D"].mean()
BASE_5D  = df["BigMove_5D"].mean()
BASE_20D = df["BigMove_20D"].mean()

# =========================================================
# VALIDITY SUMMARY
# =========================================================
def eval_block(mask, label):
    return {
        "Signal": label,
        "Count": int(mask.sum()),
        "BigMove_1D_ratio": df.loc[mask, "BigMove_1D"].mean(),
        "BigMove_5D_ratio": df.loc[mask, "BigMove_5D"].mean(),
        "BigMove_20D_ratio": df.loc[mask, "BigMove_20D"].mean(),
        "Lift_1D": df.loc[mask, "BigMove_1D"].mean() / BASE_1D if BASE_1D > 0 else np.nan,
        "Lift_5D": df.loc[mask, "BigMove_5D"].mean() / BASE_5D if BASE_5D > 0 else np.nan,
        "Lift_20D": df.loc[mask, "BigMove_20D"].mean() / BASE_20D if BASE_20D > 0 else np.nan,
        "Mean_|RET|_1D": df.loc[mask, "RET_QQQ_1D"].abs().mean(),
        "Mean_|RET|_5D": df.loc[mask, "RET_QQQ_5D"].abs().mean(),
    }

summary = []

summary.append(
    eval_block(
        df["MRDI_Short"] > df["MRDI_Short"].quantile(0.9),
        "MRDI_Short > P90"
    )
)

summary.append(
    eval_block(
        df["MRDI_Long"] > df["MRDI_Long"].quantile(0.9),
        "MRDI_Long > P90"
    )
)

summary.append(
    eval_block(
        df["RiskScore"] > 0.8,
        "RiskScore > 0.8"
    )
)

summary_df = pd.DataFrame(summary)
summary_df.to_csv(OUT_SUMMARY, index=False)

# =========================================================
# LAG EFFECT EVALUATION
# =========================================================
lag_rows = []

thr_mrdi = df["MRDI_Short"].quantile(0.9)

for lag in range(0, 11):
    col = f"MRDI_lag{lag}"
    df[col] = df["MRDI_Short"].shift(lag)

    mask = df[col] > thr_mrdi

    lag_rows.append({
        "lag": lag,
        "Count": int(mask.sum()),
        "BigMove_1D_ratio": df.loc[mask, "BigMove_1D"].mean(),
        "BigMove_5D_ratio": df.loc[mask, "BigMove_5D"].mean(),
        "Lift_1D": df.loc[mask, "BigMove_1D"].mean() / BASE_1D if BASE_1D > 0 else np.nan,
        "Mean_|RET|_1D": df.loc[mask, "RET_QQQ_1D"].abs().mean(),
    })

lag_df = pd.DataFrame(lag_rows)
lag_df.to_csv(OUT_LAG, index=False)

# =========================================================
# DONE
# =========================================================
print("\n=== MARKET STATE INDICATOR VALIDITY EVALUATION COMPLETED ===")
print("Summary :", OUT_SUMMARY)
print("Lag Eval:", OUT_LAG)
