#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression Evaluation & Forecast Pipeline (3Y FIXED)

- 毎日実行
- 回帰 window は 3y に固定
- QQQ / SP500 を並列で回帰
- 予測は「Forward SUM（1W / 1M / 6M）」のみ使用
- コメント・confidence 等の主観表現は一切排除
"""


import pandas as pd
import numpy as np
import shutil
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
MODEL_VERSION = "walk_forward_v2"


def select_feature_columns(df, target_columns):
    """Return a stable, estimable feature set.

    The old model fed hundreds of high-order interaction terms to unregularized
    OLS with only roughly 600-700 observations.  Keep the directly observable
    features and remove one dummy from each categorical group to avoid the
    dummy-variable trap.
    """
    excluded = {"date", *target_columns, "m_12", "wd_4"}
    return [
        c for c in df.columns
        if c not in excluded and "_x_" not in c
    ]

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
        "QQQ_6M_FWD_SUM": "QQQ_6M_FWD_SUM",
        "SOX_1W_FWD_SUM": "SOX_1W_FWD_SUM",
        "SOX_1M_FWD_SUM": "SOX_1M_FWD_SUM",
        "SOX_6M_FWD_SUM": "SOX_6M_FWD_SUM",
        "SP500_1W_FWD_SUM": "SP500_1W_FWD_SUM",
        "SP500_1M_FWD_SUM": "SP500_1M_FWD_SUM",
        "SP500_6M_FWD_SUM": "SP500_6M_FWD_SUM",
    }
    TARGETS.update({
        f"{asset}_D{day}_FWD": f"{asset}_D{day}_FWD"
        for asset in ["QQQ", "SOX", "SP500"] for day in range(1, 11)
    })

    FEATURE_COLS = select_feature_columns(df, TARGETS.values())

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
        "QQQ_6M_FWD_SUM": "QQQ_6M_FWD_SUM",
        "SOX_1W_FWD_SUM": "SOX_1W_FWD_SUM",
        "SOX_1M_FWD_SUM": "SOX_1M_FWD_SUM",
        "SOX_6M_FWD_SUM": "SOX_6M_FWD_SUM",
        "SP500_1W_FWD_SUM": "SP500_1W_FWD_SUM",
        "SP500_1M_FWD_SUM": "SP500_1M_FWD_SUM",
        "SP500_6M_FWD_SUM": "SP500_6M_FWD_SUM",
    }
    TARGETS.update({
        f"{asset}_D{day}_FWD": f"{asset}_D{day}_FWD"
        for asset in ["QQQ", "SOX", "SP500"] for day in range(1, 11)
    })

    FEATURE_COLS = select_feature_columns(df, TARGETS.values())

    df[FEATURE_COLS] = df[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")
    for t in TARGETS.values():
        df[t] = pd.to_numeric(df[t], errors="coerce")

    # =========================================================
    # DATE CONTROL
    # =========================================================
    data_date = raw_df["date"].max().normalize()
    forecast_date = data_date

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
    # REGRESSION & FORECAST (6 TARGETS)
    # =========================================================
    results = {}

    for label, target_col in TARGETS.items():

        train_df = work_df.dropna(subset=FEATURE_COLS + [target_col]).copy()
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

        latest_features = predict_df.sort_values("date")[FEATURE_COLS].iloc[[-1]]
        if latest_features.isna().any(axis=None):
            missing_latest = latest_features.columns[latest_features.isna().iloc[0]].tolist()
            raise RuntimeError(
                f"Latest feature row is incomplete for {label}: "
                + ", ".join(missing_latest)
            )

        latest_X = sm.add_constant(
            latest_features,
            has_constant="add"
        )

        # OLS can extrapolate far outside the observed return distribution.
        # Bound every horizon to its training-period central range; the old
        # implementation bounded daily predictions only and still emitted
        # implausible double-digit weekly forecasts.
        prediction_lower = float(y.quantile(0.05))
        prediction_upper = float(y.quantile(0.95))
        raw_point_pred = float(model.predict(latest_X).iloc[0])
        point_pred = float(np.clip(
            raw_point_pred, prediction_lower, prediction_upper
        ))

        results[label] = {
            "model": model,
            "n_obs": int(model.nobs),
            "R2": float(model.rsquared),
            "Adj_R2": float(model.rsquared_adj),
            "AIC": float(model.aic),
            "BIC": float(model.bic),
            "point_prediction": point_pred,
            "prediction_lower": prediction_lower,
            "prediction_upper": prediction_upper,
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

    if not coef_rows:
        raise RuntimeError("No regression model could be fitted")

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

    raw_dates = pd.DatetimeIndex(raw_df["date"]).sort_values()
    raw_pos = {d.normalize(): i for i, d in enumerate(raw_dates)}

    def future_market_days(as_of_date, needed):
        start = as_of_date + pd.Timedelta(days=1)
        end = as_of_date + pd.Timedelta(days=needed * 3 + 30)
        try:
            import pandas_market_calendars as mcal
            nyse = mcal.get_calendar("NYSE")
            sched = nyse.schedule(start_date=start, end_date=end)
            days = pd.DatetimeIndex(sched.index).normalize()
        except Exception:
            days = pd.date_range(start=start, end=end, freq=US_BDAY).normalize()
        return days[:needed]

    def period_for(as_of_date, start_offset, length):
        as_of_date = pd.Timestamp(as_of_date).normalize()
        pos = raw_pos.get(as_of_date)
        end_offset = start_offset + length - 1

        if pos is not None and pos + end_offset < len(raw_dates):
            return (
                raw_dates[pos + start_offset].normalize(),
                raw_dates[pos + end_offset].normalize(),
            )

        days = future_market_days(as_of_date, end_offset)
        if len(days) < end_offset:
            raise RuntimeError("Unable to build future market-day forecast period")
        return days[start_offset - 1], days[end_offset - 1]

    def row_for(as_of_date, target, horizon, start_date, end_date, key, pred_sum):
        r = results[key]
        m = r["model"]

        t_values = m.tvalues.drop("const", errors="ignore")
        p_values = m.pvalues.drop("const", errors="ignore")

        return {
            "model_version": MODEL_VERSION,
            "as_of_date": as_of_date,
            "target": target,
            "horizon": horizon,
            "start_date": start_date,
            "end_date": end_date,

            # prediction
            "pred_sum": pred_sum,

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

    predict_work = predict_df.sort_values("date").reset_index(drop=True).copy()
    predict_work[FEATURE_COLS] = predict_work[FEATURE_COLS].apply(pd.to_numeric, errors="coerce")

    target_meta = [
        ("QQQ", "1W", "QQQ_1W_FWD_SUM", 5, 5),
        ("QQQ", "1M", "QQQ_1M_FWD_SUM", 20, 20),
        ("QQQ", "6M", "QQQ_6M_FWD_SUM", 1, 126),
        ("SOX", "1W", "SOX_1W_FWD_SUM", 5, 5),
        ("SOX", "1M", "SOX_1M_FWD_SUM", 20, 20),
        ("SOX", "6M", "SOX_6M_FWD_SUM", 1, 126),
        ("SP500", "1W", "SP500_1W_FWD_SUM", 5, 5),
        ("SP500", "1M", "SP500_1M_FWD_SUM", 20, 20),
        ("SP500", "6M", "SP500_6M_FWD_SUM", 1, 126),
    ]

    # Production forecasts are immutable point-in-time records.  Only the
    # latest row is forecast here; applying today's fitted model to every past
    # row would leak future information into the historical evaluation.
    valid_predict = predict_work.dropna(subset=FEATURE_COLS)
    if valid_predict.empty:
        raise RuntimeError("No complete feature row is available for prediction")

    pred_row = valid_predict.iloc[-1]
    as_of_date = pd.Timestamp(pred_row["date"]).normalize()
    if as_of_date != data_date:
        raise RuntimeError(
            f"Latest complete feature date {as_of_date.date()} does not match "
            f"raw data date {data_date.date()}"
        )

    latest_X = sm.add_constant(
        pd.DataFrame([pred_row[FEATURE_COLS]], columns=FEATURE_COLS),
        has_constant="add"
    )

    for target, horizon, key, start_offset, length in target_meta:
        if key not in results:
            continue
        start_date, end_date = period_for(as_of_date, start_offset, length)
        raw_pred = float(results[key]["model"].predict(latest_X).iloc[0])
        pred_sum = float(np.clip(
            raw_pred,
            results[key]["prediction_lower"],
            results[key]["prediction_upper"],
        ))
        log_rows.append(
            row_for(as_of_date, target, horizon, start_date, end_date, key, pred_sum)
        )

    new_log = pd.DataFrame(log_rows)

    # The pre-v2 file was reconstructed on every run with a model trained on
    # future data.  Preserve it for audit, but never mix it into valid results.
    existing = pd.DataFrame()
    if LOG_PATH.exists():
        old = pd.read_csv(LOG_PATH)
        if "model_version" in old.columns:
            old = old[old["model_version"] == MODEL_VERSION].copy()
            for c in ["as_of_date", "start_date", "end_date"]:
                old[c] = pd.to_datetime(old[c])
            existing = old
        else:
            legacy_path = LOG_PATH.with_name(
                LOG_PATH.stem + ".legacy_pre_walk_forward.csv"
            )
            if not legacy_path.exists():
                shutil.copy2(LOG_PATH, legacy_path)

    merged = pd.concat([existing, new_log], ignore_index=True)
    merged = (
        merged
        .drop_duplicates(
            subset=["model_version", "as_of_date", "target", "horizon"],
            keep="first",
        )
        .sort_values(["as_of_date", "target", "horizon"])
        .reset_index(drop=True)
    )

    # =========================================================
    # ACTUAL REALIZATION (AUTO FILL)
    # =========================================================
    raw_px = raw_df.set_index("date")

    def calc_actual_sum(row):
        # すでに埋まっている場合は触らない
        if pd.notna(row["actual_sum"]):
            return row["actual_sum"]

        start = pd.Timestamp(row["start_date"]).normalize()
        end   = pd.Timestamp(row["end_date"]).normalize()
        target = row["target"]

        # 対象列
        if target in ["QQQ", "SOX", "SP500"]:
            col = target
        else:
            return np.nan

        dates = raw_px.index
        if start not in dates or end not in dates:
            return np.nan

        start_pos = dates.get_loc(start)
        end_pos = dates.get_loc(end)
        if start_pos == 0 or end_pos < start_pos:
            return np.nan

        px = raw_px.iloc[start_pos - 1:end_pos + 1][col]
        if px.isna().any() or len(px) < 2:
            return np.nan

        # 回帰で使用した *_FWD_SUM と同じく、日次リターンの単純和で評価する。
        ret = px.pct_change().dropna()
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
        (merged["target"].isin(["QQQ", "SOX", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M", "6M"])) &
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
        (merged["target"].isin(["QQQ", "SOX", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M", "6M"]))
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
    # helper : build asset block  (FIXED : 1M weekly normalize + 1/1 reset)
    # =========================================================
    def build_asset_block(df_asset, prefix):

        # -----------------------------------------------------
        # pivot (prediction / actual)
        # -----------------------------------------------------
        p_pred = df_asset.pivot_table(
            index="week",
            columns="horizon",
            values="pred_sum",
            aggfunc="mean"
        ).rename(columns={
            "1W": f"{prefix}_pred_1w",
            "1M": f"{prefix}_pred_1m_raw",
            "6M": f"{prefix}_pred_6m",
        })

        p_act = df_asset.pivot_table(
            index="week",
            columns="horizon",
            values="actual_sum",
            aggfunc="mean"
        ).rename(columns={
            "1W": f"{prefix}_actual_1w",
            "1M": f"{prefix}_actual_1m_raw",
            "6M": f"{prefix}_actual_6m",
        })

        block = p_pred.join(p_act, how="outer").sort_index()

        # -----------------------------------------------------
        # (1) Monthly → Weekly 正規化
        # 定義:
        #   1M_FWD_SUM = 20営業日分
        #   Weekly換算 = /20 × 5
        # -----------------------------------------------------
        for kind in ["pred", "actual"]:
            raw_col = f"{prefix}_{kind}_1m_raw"
            out_col = f"{prefix}_{kind}_1m"

            if raw_col in block.columns:
                block[out_col] = block[raw_col] / 20.0 * 5.0

        # raw 月次は Viewer では使用しない
        block = block.drop(
            columns=[c for c in block.columns if c.endswith("_1m_raw")],
            errors="ignore"
        )

        # -----------------------------------------------------
        # (2-a) リセットなし累積（完全連続）
        # -----------------------------------------------------
        for c in block.columns:
            if c.endswith("_1w") or c.endswith("_1m"):
                block[f"{c}_cum_nrst"] = block[c].cumsum()

        # -----------------------------------------------------
        # (2-b) 1/1 リセット付き累積（年次累積：既存仕様）
        # -----------------------------------------------------
        block["year"] = block.index.year

        for c in block.columns:
            if c.endswith("_1w") or c.endswith("_1m"):
                block[f"{c}_cum"] = (
                    block
                    .groupby("year")[c]
                    .cumsum()
                )

        block = block.drop(columns=["year"])

        return block

    # =========================================================
    # build blocks
    # =========================================================
    qqq_block = build_asset_block(
        trend_src[trend_src["target"] == "QQQ"],
        prefix="qqq"
    )

    sox_block = build_asset_block(
        trend_src[trend_src["target"] == "SOX"],
        prefix="sox"
    )

    sp_block = build_asset_block(
        trend_src[trend_src["target"] == "SP500"],
        prefix="sp"
    )

    # --- guard ---
    blocks = [b for b in [qqq_block, sox_block, sp_block] if b is not None]
    if not blocks:
        trend_out = pd.DataFrame(columns=["week"])
    else:
        combined = blocks[0]
        for block in blocks[1:]:
            combined = combined.join(block, how="outer")
        trend_out = combined.reset_index().sort_values("week")

    # =========================================================
    # column order (FIXED)
    # =========================================================
    EXPECTED_COLS = [
        "week",

        # --- QQQ ---
        "qqq_pred_1w",
        "qqq_pred_1w_cum",
        "qqq_pred_1w_cum_nrst",

        "qqq_actual_1w",
        "qqq_actual_1w_cum",
        "qqq_actual_1w_cum_nrst",

        "qqq_pred_1m",
        "qqq_pred_1m_cum",
        "qqq_pred_1m_cum_nrst",

        "qqq_actual_1m",
        "qqq_actual_1m_cum",
        "qqq_actual_1m_cum_nrst",

        "qqq_pred_6m",
        "qqq_actual_6m",

        # --- SOX ---
        "sox_pred_1w", "sox_pred_1w_cum", "sox_pred_1w_cum_nrst",
        "sox_actual_1w", "sox_actual_1w_cum", "sox_actual_1w_cum_nrst",
        "sox_pred_1m", "sox_pred_1m_cum", "sox_pred_1m_cum_nrst",
        "sox_actual_1m", "sox_actual_1m_cum", "sox_actual_1m_cum_nrst",
        "sox_pred_6m", "sox_actual_6m",

        # --- SP ---
        "sp_pred_1w",
        "sp_pred_1w_cum",
        "sp_pred_1w_cum_nrst",

        "sp_actual_1w",
        "sp_actual_1w_cum",
        "sp_actual_1w_cum_nrst",

        "sp_pred_1m",
        "sp_pred_1m_cum",
        "sp_pred_1m_cum_nrst",

        "sp_actual_1m",
        "sp_actual_1m_cum",
        "sp_actual_1m_cum_nrst",

        "sp_pred_6m",
        "sp_actual_6m",
    ]


    # Keep a stable schema even before enough point-in-time observations have
    # matured.  Downstream diagnostics can render an honest "not enough
    # history yet" state instead of crashing or reading legacy backtests.
    for col in EXPECTED_COLS:
        if col not in trend_out.columns:
            trend_out[col] = np.nan
    trend_out = trend_out[EXPECTED_COLS]


    trend_out.to_csv(
        TREND_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"=== WEEKLY TREND CSV SAVED (HORIZONTAL) : {TREND_PATH.name} ===")

    # =========================================================
    # DAILY TIMING VIEW: last 5 sessions + next 10 sessions
    # =========================================================
    DAILY_TREND_PATH = DATA_DIR / "forecast_trend_daily.csv"
    valid_predict = predict_work.dropna(subset=FEATURE_COLS).sort_values("date")
    daily_rows = []

    if not valid_predict.empty:
        latest_pred_row = valid_predict.iloc[-1]
        daily_X = sm.add_constant(
            pd.DataFrame([latest_pred_row[FEATURE_COLS]], columns=FEATURE_COLS),
            has_constant="add"
        )

        # Five realized sessions, including the latest market date.
        actual_window = raw_df.sort_values("date").tail(6).copy()
        for asset in ["QQQ", "SOX", "SP500"]:
            actual_returns = actual_window[asset].pct_change()
            for idx in actual_window.index[-5:]:
                daily_rows.append({
                    "date": actual_window.loc[idx, "date"],
                    "asset": asset,
                    "actual_return": actual_returns.loc[idx],
                    "predicted_return": np.nan,
                    "phase": "actual",
                    "as_of_date": data_date,
                })

        future_days = future_market_days(data_date, 10)
        for asset in ["QQQ", "SOX", "SP500"]:
            for day, future_date in enumerate(future_days, start=1):
                key = f"{asset}_D{day}_FWD"
                if key in results:
                    raw_prediction = float(results[key]["model"].predict(daily_X).iloc[0])
                    prediction = float(np.clip(
                        raw_prediction,
                        results[key]["prediction_lower"],
                        results[key]["prediction_upper"],
                    ))
                else:
                    prediction = np.nan
                daily_rows.append({
                    "date": future_date,
                    "asset": asset,
                    "actual_return": np.nan,
                    "predicted_return": prediction,
                    "phase": "forecast",
                    "as_of_date": data_date,
                })

    pd.DataFrame(daily_rows).to_csv(
        DAILY_TREND_PATH, index=False, encoding="utf-8-sig"
    )
    print(f"=== DAILY TREND CSV SAVED : {DAILY_TREND_PATH.name} ===")


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

    latest_date = forecast_date

    today_df = merged[
        (merged["as_of_date"] == latest_date) &
        (merged["target"].isin(["QQQ", "SOX", "SP500"])) &
        (merged["horizon"].isin(["1W", "1M", "6M"]))
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
    asset_order  = ["QQQ", "SOX", "SP500"]
    period_order = ["1W", "1M", "6M"]

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
        start = pd.Timestamp(row["start_date"]).normalize()
        end   = pd.Timestamp(row["end_date"]).normalize()
        asset = row["target"]

        if asset not in ["QQQ", "SOX", "SP500"]:
            return np.nan

        dates = raw_px.index
        if start not in dates or end not in dates:
            return np.nan

        start_pos = dates.get_loc(start)
        end_pos = dates.get_loc(end)
        if start_pos == 0 or end_pos < start_pos:
            return np.nan

        px = raw_px.iloc[start_pos - 1:end_pos + 1][asset]

        if px.isna().any() or len(px) < 2:
            return np.nan

        return px.pct_change().dropna().sum()

    # =========================================================
    # VALIDATE ACTUAL_SUM (RAW RE-CALC / NO-RESET BASIS)
    # =========================================================

    check = merged.copy()

    # --- 再計算（nrst：連続リターン） ---
    check["actual_recalc_nrst"] = check.apply(recompute_actual_sum, axis=1)

    # --- 比較対象も nrst 側に統一 ---
    # actual_sum は period 単位なので、そのまま nrst と比較してよい
    check["diff_nrst"] = check["actual_sum"] - check["actual_recalc_nrst"]

    summary = check["diff_nrst"].abs().describe()
    print(summary)

    max_diff = check["diff_nrst"].abs().max()

    # --- 実質ゼロ判定のみ WARNING ---
    # --- 実務許容誤差（営業日ズレ・丸め込み込み）
    TOL = 1e-2  # 1%未満は完全許容

    if pd.notna(max_diff) and max_diff > TOL:
        print("!!! WARNING: actual_sum mismatch (nrst) detected !!!")
    else:
        print("OK: actual_sum matches raw recomputation within tolerance")


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
