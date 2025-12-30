#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Market State Analyzer（FINAL / ROBUST / FAST / REG SAFE + DATE）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.covariance import LedoitWolf
from scipy.spatial.distance import mahalanobis

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RAW_PATH = DATA_DIR / "market_factors_raw.csv"

FEATURE_PATH = DATA_DIR / "market_factors_features.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"
LATEST_POS_PATH = DATA_DIR / "latest_cluster_position.csv"
REG_DATA_PATH = DATA_DIR / "market_regression_dataset.csv"

# =========================================================
# CONFIG
# =========================================================
RET_COLS = [
    "QQQ", "SP500", "NASDAQ", "DOW",
    "VIX", "US10Y", "USDJPY", "GOLD", "TLT"
]

LEVEL_COLS = ["VIX", "US10Y", "USDJPY"]

SHORT_WINDOW = 60
LONG_WINDOW = 252 * 3
MA_WINDOWS = [20, 60]
TARGET_HORIZON = 20

# =========================================================
# LOAD RAW
# =========================================================
df = pd.read_csv(RAW_PATH)

date_candidates = ["date", "Date", "datetime", "timestamp", "trade_date"]
date_col = next((c for c in date_candidates if c in df.columns), None)
if date_col is None:
    raise ValueError(f"No date column found. columns={df.columns.tolist()}")

df[date_col] = pd.to_datetime(df[date_col])
df = df.rename(columns={date_col: "date"}).sort_values("date").reset_index(drop=True)

# =========================================================
# FEATURE BASE
# =========================================================
feat = df[["date"]].copy()

for c in LEVEL_COLS:
    feat[c] = df[c] if c in df.columns else np.nan

for c in RET_COLS:
    feat[f"RET_{c}"] = df[c].pct_change() if c in df.columns else np.nan

RET_STD_COLS = [f"RET_{c}" for c in RET_COLS]

# =========================================================
# MA RETURN
# =========================================================
for w in MA_WINDOWS:
    for c in RET_COLS:
        feat[f"RET_{c}_MA{w}"] = feat[f"RET_{c}"].rolling(w).mean()

# =========================================================
# MRDI FUNCTION
# =========================================================
def compute_mrdi(ret_df: pd.DataFrame, window: int):
    mrdi = [np.nan] * len(ret_df)
    for i in range(window, len(ret_df)):
        hist = ret_df.iloc[i - window:i].dropna()
        cur = ret_df.iloc[i]
        if hist.shape[0] < window * 0.8 or cur.isna().any():
            continue
        mean = hist.mean()
        std = hist.std().replace(0, np.nan)
        hist_z = (hist - mean) / std
        cur_z = (cur - mean) / std
        if hist_z.isna().any().any() or cur_z.isna().any():
            continue
        try:
            cov = LedoitWolf().fit(hist_z).covariance_
            mrdi[i] = mahalanobis(
                cur_z.values,
                np.zeros(len(cur_z)),
                np.linalg.inv(cov)
            )
        except Exception:
            continue
    return mrdi

# =========================================================
# MRDI
# =========================================================
feat["MRDI_Short"] = compute_mrdi(feat[RET_STD_COLS], SHORT_WINDOW)
feat["MRDI_Long"]  = compute_mrdi(feat[RET_STD_COLS], LONG_WINDOW)

for w in MA_WINDOWS:
    feat[f"MA{w}_MRDI"] = compute_mrdi(
        feat[[f"RET_{c}_MA{w}" for c in RET_COLS]],
        LONG_WINDOW
    )

MRDI_COLS = ["MRDI_Short", "MRDI_Long", "MA20_MRDI", "MA60_MRDI"]

# =========================================================
# RiskScore & Regime
# =========================================================
feat["RiskScore"] = (
    0.5 * (feat["MRDI_Short"] / feat["MRDI_Short"].rolling(252).quantile(0.95)) +
    0.5 * (feat["MRDI_Long"]  / feat["MRDI_Long"].rolling(252 * 3).quantile(0.95))
)

feat["Regime"] = pd.cut(
    feat["RiskScore"],
    bins=[-np.inf, 0.35, 0.65, np.inf],
    labels=["Low", "Neutral", "High"]
)

# =========================================================
# TARGET（FORWARD SUM ONLY）
# =========================================================

# --- daily returns (already exist as RET_QQQ / RET_SP500, but explicit for safety) ---
ret_qqq    = df["QQQ"].pct_change()
ret_sp500 = df["SP500"].pct_change()

# =========================================================
# 1W FORWARD : t+5 ~ t+9 (5 business days)
# =========================================================
feat["QQQ_1W_FWD_SUM"] = (
    ret_qqq.shift(-5).rolling(5).sum()
)

feat["SP500_1W_FWD_SUM"] = (
    ret_sp500.shift(-5).rolling(5).sum()
)

# =========================================================
# 1M FORWARD : t+20 ~ t+39 (20 business days)
# =========================================================
feat["QQQ_1M_FWD_SUM"] = (
    ret_qqq.shift(-20).rolling(20).sum()
)

feat["SP500_1M_FWD_SUM"] = (
    ret_sp500.shift(-20).rolling(20).sum()
)

# =========================================================
# MONTH / WEEKDAY
# =========================================================
month_dummies = pd.get_dummies(feat["date"].dt.month, prefix="m")
weekday_dummies = pd.get_dummies(feat["date"].dt.weekday, prefix="wd")
feat = pd.concat([feat, month_dummies, weekday_dummies], axis=1)

# =========================================================
# INTERACTIONS（既存＋追加）
# =========================================================
feat["RET_QQQ_20D"]   = df["QQQ"].pct_change(20)
feat["RET_SP500_20D"] = df["SP500"].pct_change(20)

# Δ市場（★シングル項目追加）
feat["dQQQ_D"] = df["QQQ"].pct_change(1)
feat["dQQQ_W"] = df["QQQ"].pct_change(5)
feat["dQQQ_M"] = df["QQQ"].pct_change(20)

feat["dSP500_D"] = df["SP500"].pct_change(1)
feat["dSP500_W"] = df["SP500"].pct_change(5)
feat["dSP500_M"] = df["SP500"].pct_change(20)

# 既存：曜日交互作用（そのまま）
for wd in weekday_dummies.columns:
    feat[f"{wd}_x_MRDI_Short"] = feat[wd] * feat["MRDI_Short"]
    feat[f"{wd}_x_MRDI_Long"]  = feat[wd] * feat["MRDI_Long"]
    feat[f"{wd}_x_RET_QQQ"]    = feat[wd] * feat["RET_QQQ_20D"]
    feat[f"{wd}_x_RET_SP500"]  = feat[wd] * feat["RET_SP500_20D"]

# 既存：月 × 市場計数（そのまま）
for m in month_dummies.columns:
    feat[f"{m}_x_RET_QQQ"]   = feat[m] * feat["RET_QQQ_20D"]
    feat[f"{m}_x_RET_SP500"] = feat[m] * feat["RET_SP500_20D"]

# ★追加：月 × MRDI × 市場 / Δ市場 / Δ市場×市場
for m in month_dummies.columns:
    for c in MRDI_COLS:

        # 月 × MRDI × 市場計数
        feat[f"{m}_x_{c}_x_RET_QQQ"]   = feat[m] * feat[c] * feat["RET_QQQ_20D"]
        feat[f"{m}_x_{c}_x_RET_SP500"] = feat[m] * feat[c] * feat["RET_SP500_20D"]

        # 月 × MRDI × Δ市場
        for d in ["dQQQ_D", "dQQQ_W", "dQQQ_M"]:
            feat[f"{m}_x_{c}_x_{d}"] = feat[m] * feat[c] * feat[d]

        # 月 × MRDI × Δ市場 × 市場計数
        feat[f"{m}_x_{c}_x_dQQQ_W_x_RET_QQQ"] = (
            feat[m] * feat[c] * feat["dQQQ_W"] * feat["RET_QQQ_20D"]
        )

# =========================================================
# SAVE FEATURE SNAPSHOT
# =========================================================
feat.to_csv(FEATURE_PATH, index=False)

# =========================================================
# METRICS
# =========================================================
metrics = feat[
    ["date", "RiskScore", "Regime", "MRDI_Short", "MRDI_Long", "MA20_MRDI", "MA60_MRDI"]
]
metrics.to_csv(METRIC_PATH, index=False)

# =========================================================
# LATEST POSITION
# =========================================================
latest = metrics.iloc[-1]
pos = {
    col + "_pct": metrics[col].le(latest[col]).mean() * 100
    for col in ["MRDI_Short", "MRDI_Long", "MA20_MRDI", "MA60_MRDI"]
}
pd.DataFrame([pos]).to_csv(LATEST_POS_PATH, index=False)

# =========================================================
# REGRESSION DATASET
# =========================================================
reg_df = feat.drop(columns=["Regime"], errors="ignore")
X = reg_df.select_dtypes(include=[np.number])

TARGET_COLS = [
    # 1W
    "QQQ_1W_FWD_SUM",
    "SP500_1W_FWD_SUM",

    # 1M
    "QQQ_1M_FWD_SUM",
    "SP500_1M_FWD_SUM",
]


reg_df_final = pd.concat(
    [reg_df[["date"] + TARGET_COLS], X.drop(columns=TARGET_COLS)],
    axis=1
).dropna().reset_index(drop=True)


reg_df_final.to_csv(REG_DATA_PATH, index=False)

# =========================================================
# DONE
# =========================================================
print("=== ANALYZE COMPLETED (STRICT BASE + REQUIRED EXTENSIONS) ===")
print("Regression columns:", len(reg_df_final.columns))
