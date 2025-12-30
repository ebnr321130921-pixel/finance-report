#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression Evaluation & Forecast Pipeline (3Y FIXED)

- 毎日実行
- 回帰 window は 3y に固定
- QQQ / SP500 を並列で回帰
- 予測は「Forward SUM（1W / 1M）」のみ使用
- コメント・confidence 等の主観表現は一切排除
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
DATA_DIR.mkdir(exist_ok=True)

# REG_DATA_PATH は廃止（in-memory 運用）
RAW_DATA_PATH  = DATA_DIR / "market_factors_raw.csv"

# =========================================================
# LOAD DATA (REGRESSION)
# =========================================================
def run_regression(train_df, predict_df, raw_df):

    # =========================================================
    # PREPARE DATA
    # =========================================================
    df = train_df.sort_values("date").reset_index(drop=True)
    raw_df = raw_df.sort_values("date").reset_index(drop=True)

    if "date" not in raw_df.columns:
        raise ValueError("raw_df must have 'date' column")

    # =========================================================
    # TARGETS
    # =========================================================
    TARGETS = {
        "QQQ_1W_FWD_SUM": "QQQ_1W_FWD_SUM",
        "QQQ_1M_FWD_SUM": "QQQ_1M_FWD_SUM",
        "SP500_1W_FWD_SUM": "SP500_1W_FWD_SUM",
        "SP500_1M_FWD_SUM": "SP500_1M_FWD_SUM",
    }

    FEATURE_COLS = [
        c for c in df.columns
        if c not in ["date"] + list(TARGETS.values())
    ]

    df[FEATURE_COLS] = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")
    for t in TARGETS.values():
        df[t] = pd.to_numeric(df[t], errors="coerce")

# =========================================================
# REGRESSION PIPELINE (MAIN)
# =========================================================

    # =========================================================
    # LOAD DATA (RAW / REALIZED CHECK)
    # =========================================================
    # ※ raw_df は analyze から受け取ったものをそのまま使用
    raw_df = raw_df.sort_values("date").reset_index(drop=True)

    # --- sanity ---
    if "date" not in raw_df.columns:
        raise ValueError("raw_df must have 'date' column")

    # =========================================================
    # TARGETS (8 forward targets)
    # =========================================================
    TARGETS = {
        "QQQ_1W_FWD_SUM": "QQQ_1W_FWD_SUM",
        "QQQ_1M_FWD_SUM": "QQQ_1M_FWD_SUM",
        "SP500_1W_FWD_SUM": "SP500_1W_FWD_SUM",
        "SP500_1M_FWD_SUM": "SP500_1M_FWD_SUM",
    }

    FEATURE_COLS = [c for c in df.columns if c not in ["date"] + list(TARGETS.values())]

    df[FEATURE_COLS] = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")
    for t in TARGETS.values():
        df[t] = pd.to_numeric(df[t], errors="coerce")

    # =========================================================
    # DATE CONTROL
    # =========================================================
    forecast_date = pd.Timestamp.today().normalize()
    data_date = df["date"].max()

    # --- evaluation dates (US business day based) ---
    # NOTE:
    # 評価期間の確定判定は calc_actual_sum() に一元化しているため、
    # ここでの target_date_* は定義しない

    # =========================================================
    # REALIZED DATA CHECK
    # =========================================================
    # 実績が揃ったかどうかの判定は calc_actual_sum() 内で一元管理する
    # eval_dates / is_ready 系は二重管理・誤解防止のため使用しない


    # =========================================================
    # WINDOW (FIXED : 3Y)
    # =========================================================
    WINDOW_LABEL = "3y"
    WINDOW_DAYS = 365 * 3

    cutoff = data_date - pd.Timedelta(days=WINDOW_DAYS)
    work_df = df[df["date"] >= cutoff].copy()

    # =========================================================
    # REGRESSION & FORECAST (8 TARGETS)
    # =========================================================
    results = {}

    for label, target_col in TARGETS.items():

        train_df = work_df.dropna(subset=[target_col]).copy()
        if train_df.empty:
            continue

        X = sm.add_constant(train_df[FEATURE_COLS])
        y = train_df[target_col]

        model = sm.OLS(y, X).fit()

        # today point prediction
        # --- use latest X from PREDICT dataset ---
        # predict_df は analyze 側から受け取る
        predict_df = predict_df.copy()

        # feature alignment (safety)
        predict_df[FEATURE_COLS] = predict_df[FEATURE_COLS].apply(
            pd.to_numeric, errors="coerce"
        )

        latest_X = sm.add_constant(
            predict_df.sort_values("date")[FEATURE_COLS].iloc[[-1]],
            has_constant="add"
        )

        point_pred = float(model.predict(latest_X).iloc[0])

        results[label] = {
            "model": model,
            "n_obs": int(model.nobs),
            "R2": float(model.rsquared),
            "Adj_R2": float(model.rsquared_adj),
            "AIC": float(model.aic),
            "BIC": float(model.bic),
            "point_prediction": point_pred,
        }

        print(
            f"[{label}] "
            f"R2={model.rsquared:.3f} "
            f"AdjR2={model.rsquared_adj:.3f} "
            f"Pred={point_pred:.3%}"
        )

    # =========================================================
    # SAVE REGRESSION SNAPSHOT
    # =========================================================
    metrics_rows = []
    coef_rows = []

    for target, r in results.items():
        m = r["model"]

        metrics_rows.append({
            "target": target,
            "window": WINDOW_LABEL,
            "n_obs": r["n_obs"],
            "R2": r["R2"],
            "Adj_R2": r["Adj_R2"],
            "AIC": r["AIC"],
            "BIC": r["BIC"],
            "point_prediction": r["point_prediction"],
            "n_features": len(FEATURE_COLS),
        })

        coef_rows.append(pd.DataFrame({
            "target": target,
            "window": WINDOW_LABEL,
            "variable": m.params.index,
            "coef": m.params.values,
            "p_value": m.pvalues.values,
            "t_value": m.tvalues.values,
        }))

    pd.concat(coef_rows, ignore_index=True).to_csv(
        DATA_DIR / "regression_coefficients_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("=== REGRESSION SNAPSHOT UPDATED ===")

    # =========================================================
    # FORECAST LOG (WITH PERIOD)  ※ FINAL / VERIFIABLE
    # =========================================================
    LOG_PATH = DATA_DIR / "forecast_evaluation_log.csv"

    log_rows = []

    as_of_date = forecast_date

    # --- 1W period ---
    pred_1w_start = as_of_date + 5 * US_BDAY
    pred_1w_end   = pred_1w_start + 4 * US_BDAY

    # --- 1M period ---
    pred_1m_start = as_of_date + 20 * US_BDAY
    pred_1m_end   = pred_1m_start + 19 * US_BDAY

    def row_for(target, horizon, start_date, end_date, key):
        r = results[key]
        m = r["model"]

        t_values = m.tvalues.drop("const", errors="ignore")
        p_values = m.pvalues.drop("const", errors="ignore")

        return {
            "as_of_date": as_of_date,
            "target": target,
            "horizon": horizon,
            "start_date": start_date,
            "end_date": end_date,

            # prediction
            "pred_sum": r["point_prediction"],

            # regression quality
            "R2": r["R2"],
            "Adj_R2": r["Adj_R2"],
            "n_obs": r["n_obs"],

            # statistical strength
            "t_max_abs": t_values.abs().max(),
            "p_min": p_values.min(),

            # realized (to be filled later)
            "actual_sum": np.nan,
            "error": np.nan,
        }

    # --- QQQ ---
    log_rows.append(
        row_for("QQQ", "1W", pred_1w_start, pred_1w_end, "QQQ_1W_FWD_SUM")
    )
    log_rows.append(
        row_for("QQQ", "1M", pred_1m_start, pred_1m_end, "QQQ_1M_FWD_SUM")
    )

    # --- SP500 ---
    log_rows.append(
        row_for("SP500", "1W", pred_1w_start, pred_1w_end, "SP500_1W_FWD_SUM")
    )
    log_rows.append(
        row_for("SP500", "1M", pred_1m_start, pred_1m_end, "SP500_1M_FWD_SUM")
    )

    new_df = pd.DataFrame(log_rows)

    if LOG_PATH.exists():
        old = pd.read_csv(
            LOG_PATH,
            parse_dates=["as_of_date", "start_date", "end_date"]
        )
        merged = pd.concat([old, new_df], ignore_index=True)
    else:
        merged = new_df

    merged = merged.drop_duplicates(
        subset=["as_of_date", "target", "horizon"],
        keep="last"
    )

    merged = merged.sort_values(
        ["as_of_date", "target", "horizon"]
    )

    # =========================================================
    # ACTUAL REALIZATION (AUTO FILL)
    # =========================================================
    raw_px = raw_df.set_index("date")

    def calc_actual_sum(row):
        # すでに埋まっている場合は触らない
        if pd.notna(row["actual_sum"]):
            return row["actual_sum"]

        start = row["start_date"]
        end   = row["end_date"]
        target = row["target"]

        # 対象列
        if target == "QQQ":
            col = "QQQ"
        elif target == "SP500":
            col = "SP500"
        else:
            return np.nan

        # 期間データが揃っているか
        try:
            px = raw_px.loc[start:end, col]
        except KeyError:
            return np.nan

        if px.isna().any() or len(px) == 0:
            return np.nan

        # 累積リターン（合計）
        # NOTE:
        # actual_sum は「日次リターンの単純和」
        # 回帰で使用した *_FWD_SUM（単純和定義）と整合させるため、
        # 複利 ((1+ret).prod()-1) はあえて使用しない
        ret = px.pct_change().dropna()
        if len(ret) == 0:
            return np.nan

        return ret.sum()


    merged["actual_sum"] = merged.apply(calc_actual_sum, axis=1)

    # error は一元定義（ここだけ）
    merged["error"] = merged["actual_sum"] - merged["pred_sum"]


    def sign(x):
        if pd.isna(x) or x == 0:
            return np.nan
        return np.sign(x)

    # NOTE:
    # pred_sign / actual_sign は統計検証用（sign_accuracy）にのみ使用。
    # Viewer では forecast_direction / actual_direction を使用する。
    merged["pred_sign"] = merged["pred_sum"].apply(sign)
    merged["actual_sign"] = merged["actual_sum"].apply(sign)

    merged["sign_correct"] = np.where(
        merged["actual_sum"].notna(),
        (merged["pred_sign"] == merged["actual_sign"]).astype(float),
        np.nan
    )

    merged.to_csv(
        LOG_PATH,
        index=False,
        encoding="utf-8-sig"
    )
    # =========================================================
    # BUILD TODAY FORECAST vs ACTUAL TABLE (FOR VIEWER)
    # =========================================================
    ACTUAL_COMPARE_PATH = DATA_DIR / "forecast_actual_comparison_today.csv"

    # 今日の実績日 = raw の最新日
    actual_date = raw_df["date"].max()

    compare_today = merged[
        (merged["end_date"] == actual_date) &
        (merged["target"].isin(["QQQ", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M"])) &
        (merged["actual_sum"].notna())
    ].copy()

    # --- 期間表現（予測と完全一致） ---
    compare_today["forecast_period"] = (
        compare_today["start_date"].dt.strftime("%Y-%m-%d")
        + " → "
        + compare_today["end_date"].dt.strftime("%Y-%m-%d")
    )

    # --- 方向一致のみ（ピーキー回避） ---
    compare_today["direction_correct"] = (
        np.sign(compare_today["pred_sum"])
        == np.sign(compare_today["actual_sum"])
    )

    # --- Viewer 用 最終形 ---
    compare_today_final = (
        compare_today[[
            "target",
            "horizon",
            "forecast_period",
            "pred_sum",
            "actual_sum",
            "direction_correct",
        ]]
        .rename(columns={
            "target": "asset",
            "horizon": "forecast_horizon",
            "pred_sum": "predicted_return",
            "actual_sum": "actual_return",
        })
        .sort_values(["asset", "forecast_horizon"])
        .reset_index(drop=True)
    )

    compare_today_final.to_csv(
        ACTUAL_COMPARE_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"=== TODAY FORECAST vs ACTUAL SAVED : {ACTUAL_COMPARE_PATH.name} ===")


    # =========================================================
    # BUILD WEEKLY TREND CSV (FOR VIEWER)  ※ END_DATE AXIS
    # =========================================================
    TREND_PATH = DATA_DIR / "forecast_trend_weekly.csv"

    trend_src = merged[
        (merged["target"].isin(["QQQ", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M"]))
    ].copy()

    # ---------------------------------------------------------
    # ★ future actual は無効化（意味的に未確定）
    # ---------------------------------------------------------
    latest_actual_date = raw_df["date"].max()

    trend_src.loc[
        trend_src["end_date"] > latest_actual_date,
        "actual_sum"
    ] = np.nan


    # ---------------------------------------------------------
    # ★時間軸は end_date（未来予測の帰着点）
    # ---------------------------------------------------------
    trend_src["week"] = (
        trend_src["end_date"]
        .dt.to_period("W")
        .apply(lambda r: r.start_time)
    )

    # ---------------------------------------------------------
    # ★同一 end_date に対しては「最新 as_of の予測」を採用
    # ---------------------------------------------------------
    trend_src = (
        trend_src
        .sort_values("as_of_date")
        .groupby(["week", "target", "horizon"], as_index=False)
        .tail(1)
    )

    # =========================================================
    # helper : build asset block
    # =========================================================
    def build_asset_block(df_asset, prefix):
        # prediction
        p_pred = df_asset.pivot_table(
            index="week",
            columns="horizon",
            values="pred_sum",
            aggfunc="mean"
        ).rename(columns={
            "1W": f"{prefix}_pred_1w",
            "1M": f"{prefix}_pred_1m",
        })

        # actual
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

        # cumulative (NO FILL / NO IMPUTE)
        for c in block.columns:
            block[f"{c}_cum"] = block[c].cumsum()

        return block

    # =========================================================
    # build blocks
    # =========================================================
    qqq_block = build_asset_block(
        trend_src[trend_src["target"] == "QQQ"],
        prefix="qqq"
    )

    sp_block = build_asset_block(
        trend_src[trend_src["target"] == "SP500"],
        prefix="sp"
    )

    # =========================================================
    # merge horizontal
    # =========================================================
    trend_out = (
        qqq_block
        .join(sp_block, how="outer")
        .reset_index()
        .sort_values("week")
    )

    # =========================================================
    # column order (FIXED)
    # =========================================================
    trend_out = trend_out[[
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

    trend_out.to_csv(
        TREND_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"=== WEEKLY TREND CSV SAVED (HORIZONTAL) : {TREND_PATH.name} ===")


    # =========================================================
    # SIGN ACCURACY (FOR ANALYSIS)
    # =========================================================
    sign_accuracy = (
        merged
        .dropna(subset=["sign_correct"])
        .groupby(["target", "horizon"])["sign_correct"]
        .mean()
        .reset_index()
        .rename(columns={"sign_correct": "sign_accuracy"})
    )
    print(f"=== FORECAST LOG UPDATED : {LOG_PATH.name} ===")

    # =========================================================
    # TODAY MARKET DECISION (APP VIEW)  ※ FORECAST ONLY / CLEAN
    # =========================================================
    TODAY_PATH = DATA_DIR / "today_market_decision_summary.csv"

    latest_date = merged["as_of_date"].max()

    today_df = merged[
        (merged["as_of_date"] == latest_date) &
        (merged["target"].isin(["QQQ", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M"]))
    ].copy()

    # ---- 表示用 period（未来） ----
    today_df["forecast_period"] = (
        today_df["start_date"].dt.strftime("%Y-%m-%d")
        + " → "
        + today_df["end_date"].dt.strftime("%Y-%m-%d")
    )

    # ---- 予測方向（ソフト判定） ----
    def dir_soft(x, th=0.001):
        if pd.isna(x):
            return ""
        if x > th:
            return "UP"
        if x < -th:
            return "DOWN"
        return "FLAT"

    today_df["predicted_direction"] = today_df["pred_sum"].apply(dir_soft)

    # ---- 並び順固定 ----
    asset_order  = ["QQQ", "SP500"]
    period_order = ["1W", "1M"]

    today_df["target"] = pd.Categorical(
        today_df["target"],
        categories=asset_order,
        ordered=True
    )

    today_df["horizon"] = pd.Categorical(
        today_df["horizon"],
        categories=period_order,
        ordered=True
    )

    today_df = today_df.sort_values(["target", "horizon"]).reset_index(drop=True)

    # ---- Viewer 最終列（未来専用） ----
    today_df_final = (
        today_df[[
            "as_of_date",
            "target",
            "horizon",
            "forecast_period",
            "pred_sum",
            "predicted_direction",
        ]]
        .rename(columns={
            "as_of_date": "forecast_date",
            "target": "asset",
            "horizon": "forecast_horizon",
            "pred_sum": "predicted_return",
        })
    )

    today_df_final.to_csv(
        TODAY_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"=== TODAY MARKET DECISION (FORECAST ONLY) SAVED : {TODAY_PATH.name} ===")

    # =========================================================
    # VALIDATE ACTUAL_SUM (RAW RE-CALC / ASSERT)
    # =========================================================
    print("\n=== VALIDATING ACTUAL_SUM AGAINST RAW DATA ===")

    raw_px = raw_df.set_index("date")

    def recompute_actual_sum(row):
        start = row["start_date"]
        end   = row["end_date"]
        asset = row["target"]

        if asset not in ["QQQ", "SP500"]:
            return np.nan

        px = raw_px.loc[start:end, asset]

        if px.isna().any() or len(px) < 2:
            return np.nan

        return px.pct_change().dropna().sum()

    check = merged.copy()
    check["actual_recalc"] = check.apply(recompute_actual_sum, axis=1)

    check["diff"] = check["actual_sum"] - check["actual_recalc"]

    # --- 数値検証サマリー ---
    summary = check["diff"].abs().describe()
    print(summary)

    # --- 強制保証（異常があれば即わかる） ---
    max_diff = check["diff"].abs().max()

    if pd.notna(max_diff) and max_diff > 1e-10:
        print("!!! WARNING: actual_sum mismatch detected !!!")
    else:
        print("OK: actual_sum perfectly matches raw recomputation")

    # =========================================================
    # RETURN (IN-MEMORY)
    # =========================================================
    return {
        "results": results,
        "forecast_log": merged,
        "trend_df": trend_out,
        "today_df": today_df_final,
        "sign_accuracy": sign_accuracy,
    }

