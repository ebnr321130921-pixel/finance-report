#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression Evaluation & Forecast Pipeline (FINAL)

- 毎日実行
- window別回帰を実施
- 予測は日次ログ（横持ち）
- 回帰の中身（係数・p値・指標）は Summary 用に毎回スナップショット保存
- 追加：
    * 今日の指数 × 回帰係数 × t値 から
    * 1W / 1M の未来方向性を出力
    * US市場営業日ベースの日付（祝日除外）
    * 日本語コメント
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

FORECAST_DIR = DATA_DIR / "forecast"
FORECAST_DIR.mkdir(exist_ok=True)

# =========================================================
# LOAD DATA
# =========================================================
df = pd.read_csv(REG_DATA_PATH, parse_dates=["date"])

TARGET = "QQQ_20D_RETURN"

FEATURE_COLS = [c for c in df.columns if c not in ["date", TARGET]]
MA60_COLS = [c for c in FEATURE_COLS if "MA60" in c]

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

    if days is not None:
        cutoff = data_date - pd.Timedelta(days=days)
        work_df = work_df[work_df["date"] >= cutoff]

    if label in ["1y", "3y"]:
        use_cols = [c for c in FEATURE_COLS if c not in MA60_COLS]
    else:
        use_cols = FEATURE_COLS

    train_df = work_df.dropna(subset=[TARGET]).copy()

    X = sm.add_constant(train_df[use_cols])
    y = train_df[TARGET]

    model = sm.OLS(y, X).fit()

    pred_df = work_df.dropna(subset=use_cols).copy()
    X_all = sm.add_constant(pred_df[use_cols], has_constant="add")
    pred_df["y_pred"] = model.predict(X_all)

    latest_pred = float(pred_df.iloc[-1]["y_pred"])
    forecast_row[f"pred_{label}"] = latest_pred

    metrics_rows.append({
        "window": label,
        "n_obs": int(model.nobs),
        "R2": float(model.rsquared),
        "Adj_R2": float(model.rsquared_adj),
        "AIC": float(model.aic),
        "BIC": float(model.bic),
        "n_features": len(use_cols),
    })

    coef_df = pd.DataFrame({
        "window": label,
        "variable": model.params.index,
        "coef": model.params.values,
        "p_value": model.pvalues.values,
        "t_value": model.tvalues.values,
    })
    coef_rows.append(coef_df)

    print(
        f"[{label}] "
        f"R2={model.rsquared:.3f} "
        f"AdjR2={model.rsquared_adj:.3f} "
        f"Pred={latest_pred:.3%}"
    )

# =========================================================
# SAVE REGRESSION SNAPSHOT
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
# FORWARD DIRECTION FORECAST
# =========================================================
FORWARD_HORIZONS = {
    "1W": {"keywords": ["RET_QQQ", "MA20", "MRDI_Short", "m_"], "bdays": 5},
    "1M": {"keywords": ["MA60", "MRDI_Long", "RiskScore", "m_"], "bdays": 20},
}

T_STRONG = 3.0
T_MID = 2.0

def make_jp_comment(direction, confidence):
    if direction == "DOWN" and confidence == "HIGH":
        return "下方向バイアスが強い"
    if direction == "DOWN" and confidence == "MID":
        return "下方向だが確信は中程度"
    if direction == "UP" and confidence == "HIGH":
        return "上方向バイアスが強い"
    if direction == "UP" and confidence == "MID":
        return "上方向だが確信は中程度"
    if direction == "WEAK":
        return "方向感が弱く様子見"
    return "方向性なし"

latest_row = df.sort_values("date").iloc[-1]
forward_rows = []

for horizon, cfg in FORWARD_HORIZONS.items():

    # ★ US市場営業日で未来日付を算出
    target_date = forecast_date + cfg["bdays"] * US_BDAY

    for window in coef_latest["window"].unique():

        sub = coef_latest[
            (coef_latest["window"] == window)
            & (coef_latest["variable"] != "const")
        ]

        sub = sub[sub["variable"].str.contains("|".join(cfg["keywords"]))]

        score = 0.0
        dominant = []

        for _, r in sub.iterrows():
            var = r["variable"]
            if var not in latest_row:
                continue

            x = latest_row[var]
            t = r["t_value"]

            score += np.sign(t) * abs(t) * np.sign(x)

            if abs(t) >= T_STRONG:
                dominant.append(var)

        if score >= T_STRONG:
            direction = "UP"
            action = "QQQ"
            confidence = "HIGH"
        elif score <= -T_STRONG:
            direction = "DOWN"
            action = "SP500"
            confidence = "HIGH"
        elif abs(score) >= T_MID:
            direction = "WEAK"
            action = "HOLD"
            confidence = "MID"
        else:
            direction = "NEUTRAL"
            action = "HOLD"
            confidence = "LOW"

        forward_rows.append({
            "as_of_date": forecast_date,
            "target_date": target_date.date(),
            "horizon": horizon,
            "window": window,
            "direction_score": round(score, 2),
            "direction": direction,
            "recommended_action": action,
            "confidence": confidence,
            "jp_comment": make_jp_comment(direction, confidence),
            "dominant_factors": ";".join(dominant[:5]),
        })

forward_df = pd.DataFrame(forward_rows)
forward_df.to_csv(
    DATA_DIR / "forward_direction_forecast.csv",
    index=False,
    encoding="utf-8-sig"
)

print("=== FORWARD DIRECTION FORECAST UPDATED ===")

# =========================================================
# APPEND DAILY LOG FOR VERIFICATION
# =========================================================
LOG_PATH = DATA_DIR / "forward_direction_forecast_log.csv"

if LOG_PATH.exists():
    old_log = pd.read_csv(LOG_PATH, parse_dates=["as_of_date"])
    merged_log = pd.concat([old_log, forward_df], ignore_index=True)
    merged_log = merged_log.drop_duplicates(
        subset=["as_of_date", "horizon", "window"],
        keep="last"
    )
else:
    merged_log = forward_df.copy()

merged_log = merged_log.sort_values(
    ["as_of_date", "horizon", "window"]
)

merged_log.to_csv(
    LOG_PATH,
    index=False,
    encoding="utf-8-sig"
)

print("=== FORWARD DIRECTION LOG UPDATED ===")
print(f"Saved to : {LOG_PATH.name}")
print("\n=== PIPELINE COMPLETED ===")
