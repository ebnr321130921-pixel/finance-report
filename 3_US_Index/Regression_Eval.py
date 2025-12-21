#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression Evaluation & Forecast Pipeline (FINAL)

- 毎日実行
- window別回帰を実施
- 予測は日次ログ（横持ち）
- 回帰の中身（係数・p値・指標）は Summary 用に毎回スナップショット保存
"""

import pandas as pd
import numpy as np
from pathlib import Path
import statsmodels.api as sm

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

REG_DATA_PATH = DATA_DIR / "market_regression_dataset.csv"

FORECAST_DIR = DATA_DIR / "forecast"
FORECAST_DIR.mkdir(exist_ok=True)

# =========================================================
# LOAD DATA
# =========================================================
df = pd.read_csv(REG_DATA_PATH, parse_dates=["date"])

TARGET = "QQQ_20D_RETURN"

FEATURE_COLS = [c for c in df.columns if c not in ["date", TARGET]]
MA60_COLS = [c for c in FEATURE_COLS if "MA60" in c]

# dtype 最終防衛
df[FEATURE_COLS] = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")
df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")

# =========================================================
# DATE CONTROL
# =========================================================
forecast_date = pd.Timestamp.today().normalize()
data_date = df["date"].max()
is_market_day = bool(forecast_date == data_date)
record_year = forecast_date.year

# =========================================================
# WINDOW SETTINGS
# =========================================================
WINDOWS = {
    "all": None,
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
    "10y": 365 * 10,
}

# =========================================================
# CONTAINERS
# =========================================================
forecast_row = {
    "forecast_date": forecast_date,
    "data_date": data_date,
    "is_market_day": is_market_day,
}

metrics_rows = []
coef_rows = []

# =========================================================
# MAIN LOOP : REGRESSION
# =========================================================
for label, days in WINDOWS.items():

    work_df = df.copy()

    # ---- window filter
    if days is not None:
        cutoff = data_date - pd.Timedelta(days=days)
        work_df = work_df[work_df["date"] >= cutoff]

    # ---- feature selection
    if label in ["1y", "3y"]:
        use_cols = [c for c in FEATURE_COLS if c not in MA60_COLS]
    else:
        use_cols = FEATURE_COLS

    train_df = work_df.dropna(subset=[TARGET]).copy()

    X = sm.add_constant(train_df[use_cols])
    y = train_df[TARGET]

    model = sm.OLS(y, X).fit()

    # ---- latest prediction
    pred_df = work_df.dropna(subset=use_cols).copy()
    X_all = sm.add_constant(pred_df[use_cols], has_constant="add")
    pred_df["y_pred"] = model.predict(X_all)

    latest_pred = float(pred_df.iloc[-1]["y_pred"])
    forecast_row[f"pred_{label}"] = latest_pred

    # ---- metrics snapshot
    metrics_rows.append({
        "window": label,
        "n_obs": int(model.nobs),
        "R2": float(model.rsquared),
        "Adj_R2": float(model.rsquared_adj),
        "AIC": float(model.aic),
        "BIC": float(model.bic),
        "n_features": len(use_cols),
    })

    # ---- coefficient snapshot
    coef_df = pd.DataFrame({
        "window": label,
        "variable": model.params.index,
        "coef": model.params.values,
        "p_value": model.pvalues.values,
        "t_value": model.tvalues.values,
    })
    coef_rows.append(coef_df)

    # ---- console log
    print(
        f"[{label}] "
        f"R2={model.rsquared:.3f} "
        f"AdjR2={model.rsquared_adj:.3f} "
        f"Pred={latest_pred:.3%}"
    )

# =========================================================
# SAVE REGRESSION SNAPSHOT (FOR SUMMARY)
# =========================================================
metrics_latest = pd.DataFrame(metrics_rows)
metrics_latest.to_csv(
    DATA_DIR / "regression_metrics_latest.csv",
    index=False,
    encoding="utf-8-sig"
)

coef_latest = pd.concat(coef_rows, ignore_index=True)
coef_latest.to_csv(
    DATA_DIR / "regression_coefficients_latest.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n=== REGRESSION SNAPSHOT UPDATED ===")

# =========================================================
# SAVE DAILY FORECAST LOG（SCHEMA SAFE）
# =========================================================
yearly_path = FORECAST_DIR / f"forecast_{record_year}.csv"
new_df = pd.DataFrame([forecast_row])

if yearly_path.exists():
    old = pd.read_csv(yearly_path)

    required_cols = {
        "forecast_date",
        "data_date",
        "is_market_day",
        "pred_all",
        "pred_1y",
        "pred_3y",
        "pred_5y",
        "pred_10y",
    }

    if not required_cols.issubset(set(old.columns)):
        merged = new_df
    else:
        old["forecast_date"] = pd.to_datetime(old["forecast_date"])
        old["data_date"] = pd.to_datetime(old["data_date"])

        merged = pd.concat([old, new_df], ignore_index=True)
        merged = (
            merged
            .sort_values("forecast_date")
            .drop_duplicates(subset=["forecast_date"], keep="last")
        )
else:
    merged = new_df

merged.to_csv(yearly_path, index=False, encoding="utf-8-sig")

print("=== FORECAST LOG UPDATED ===")
print(f"Saved to : {yearly_path.name}")
print("\n=== PIPELINE COMPLETED ===")
