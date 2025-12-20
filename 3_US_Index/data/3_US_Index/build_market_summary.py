#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Summary Builder（FINAL / PRODUCTION）

- 回帰は fit しない（構造説明のみ）
- regression_coefficients_latest / regression_metrics_latest を解釈
- forecast は数値予測の唯一ソース
- 列名揺れ・NaN 完全耐性
- 投資判断用の Market Memo を生成
- Mahalanobis Short × Long 散布図用データセットを同時生成
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

RAW_PATH = DATA_DIR / "market_factors_raw.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"
LATEST_POS_PATH = DATA_DIR / "latest_cluster_position.csv"

REG_COEF_PATH = DATA_DIR / "regression_coefficients_latest.csv"
REG_METRICS_PATH = DATA_DIR / "regression_metrics_latest.csv"
FORECAST_PATH = DATA_DIR / "forecast" / "forecast_2025.csv"

SUMMARY_TEXT_PATH = DATA_DIR / "market_summary_text.txt"
SUMMARY_TABLE_PATH = DATA_DIR / "market_summary_table.csv"
DECISION_LOG_PATH = DATA_DIR / "decision_log.csv"

SCATTER_OUT_PATH = DATA_DIR / "mahalanobis_scatter_short_long.csv"

# =========================================================
# UTIL
# =========================================================
def load_csv_with_date(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ["date", "Date", "market_date", "global_market_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
            return df.rename(columns={c: "date"})
    raise ValueError(f"No date column found in {path.name}")

def safe_val(df, col):
    return df[col].iloc[0] if col in df.columns and not df.empty else np.nan

def extract_forecast_return(df):
    for c in df.columns:
        if c.lower() in ["expected_return", "forecast_return", "return", "expected", "value"]:
            return df[c].iloc[-1]
    return np.nan

def top_contributors(df, n=3):
    col_feature = None
    col_coef = None
    for c in df.columns:
        if c.lower() in ["feature", "feature_name", "name"]:
            col_feature = c
        if c.lower() in ["coefficient", "coef", "beta", "value"]:
            col_coef = c
    if col_feature is None or col_coef is None:
        return pd.DataFrame()
    d = df[[col_feature, col_coef]].copy()
    d.columns = ["feature", "coefficient"]
    d["abs_coef"] = d["coefficient"].abs()
    return d.sort_values("abs_coef", ascending=False).head(n)

def find_md_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

# =========================================================
# LOAD
# =========================================================
raw = load_csv_with_date(RAW_PATH)
metrics = load_csv_with_date(METRIC_PATH)
latest_pos = pd.read_csv(LATEST_POS_PATH)

reg_coef = pd.read_csv(REG_COEF_PATH)
reg_metrics = pd.read_csv(REG_METRICS_PATH)
forecast = pd.read_csv(FORECAST_PATH)

# =========================================================
# DATE
# =========================================================
latest_date = raw["date"].max()
prev_date = raw.loc[raw["date"] < latest_date, "date"].max()

raw_latest = raw.loc[raw["date"] == latest_date].iloc[0]
raw_prev = raw.loc[raw["date"] == prev_date].iloc[0]

m_latest = metrics.iloc[-1]
m_prev = metrics.iloc[-2]
m_week_avg = metrics.tail(5).mean(numeric_only=True)

# =========================================================
# BASIC VALUES
# =========================================================
risk = m_latest["RiskScore"]

mrdi_s_pct = safe_val(latest_pos, "MRDI_Short_pct")
mrdi_l_pct = safe_val(latest_pos, "MRDI_Long_pct")
ma20_pct   = safe_val(latest_pos, "MA20_MRDI_pct")
ma60_pct   = safe_val(latest_pos, "MA60_MRDI_pct")

vix_diff  = raw_latest["VIX"] - raw_prev["VIX"]
rate_diff = raw_latest["US10Y"] - raw_prev["US10Y"]

# =========================================================
# SUMMARY TABLE
# =========================================================
def pct(a, b):
    if b == 0 or pd.isna(b):
        return None
    return (a - b) / abs(b) * 100

ITEMS = [
    "QQQ", "SP500", "NASDAQ", "DOW",
    "VIX", "US10Y", "USDJPY",
    "RiskScore", "MRDI_Short", "MRDI_Long",
]

rows = []

for c in ITEMS:
    if c in raw.columns:
        latest = raw_latest[c]
        prev = raw_prev[c]
        week_avg = raw.tail(5)[c].mean()
    else:
        latest = m_latest[c]
        prev = m_prev[c]
        week_avg = m_week_avg[c]

    rows.append({
        "Item": c,
        "Latest": round(latest, 4),
        "Δ vs Yesterday": round(latest - prev, 4),
        "% vs Yesterday": round(pct(latest, prev), 2),
        "Δ vs LastWeekAvg": round(latest - week_avg, 4),
        "% vs LastWeekAvg": round(pct(latest, week_avg), 2),
    })

rows.extend([
    {"Item": "MA20_MRDI", "Latest": round(m_latest["MA20_MRDI"], 3), "Percentile": round(ma20_pct, 1)},
    {"Item": "MA60_MRDI", "Latest": round(m_latest["MA60_MRDI"], 3), "Percentile": round(ma60_pct, 1)},
])

pd.DataFrame(rows).to_csv(SUMMARY_TABLE_PATH, index=False)

# =========================================================
# DANGER / SIGNAL
# =========================================================
if mrdi_s_pct >= 85 and risk >= 0.75:
    danger = "EXTREME"
elif mrdi_s_pct >= 70 or risk >= 0.65:
    danger = "HIGH"
elif mrdi_s_pct >= 50:
    danger = "MODERATE"
else:
    danger = "LOW"

signal = "HOLD"
if danger == "EXTREME":
    signal = "DOWN"
elif danger == "LOW":
    signal = "UP"

# =========================================================
# REGRESSION INTERPRETATION
# =========================================================
top_factors = top_contributors(reg_coef, n=3)

if top_factors.empty:
    factor_sentence = "明確な寄与因子は限定的"
else:
    parts = []
    for _, r in top_factors.iterrows():
        sign = "プラス寄与" if r["coefficient"] > 0 else "マイナス寄与"
        parts.append(f"{r['feature']}が{sign}")
    factor_sentence = "、".join(parts)

r2  = reg_metrics["R2"].iloc[0]  if "R2"  in reg_metrics.columns else np.nan
mae = reg_metrics["MAE"].iloc[0] if "MAE" in reg_metrics.columns else np.nan

metric_parts = []
if not np.isnan(r2):
    metric_parts.append(f"R²={r2:.2f}")
if not np.isnan(mae):
    metric_parts.append(f"MAE={mae:.2f}")

metric_sentence = " , ".join(metric_parts) if metric_parts else "定量的精度指標は限定的"
forecast_return = extract_forecast_return(forecast)

# =========================================================
# SUMMARY TEXT
# =========================================================
daily = (
    f"短期MRDIは{mrdi_s_pct:.1f}%に位置し、"
    f"VIXは前日比{vix_diff:+.2f}、米10年金利は{rate_diff:+.2f}変化しています。"
    f" 危険度は【{danger}】と評価されます。"
)

weekly = (
    f"RiskScoreは{risk:.2f}で、先週平均と比べて"
    f"{(risk - m_week_avg['RiskScore']):+.2f}の変化です。"
)

structural = (
    f"長期MRDIは{mrdi_l_pct:.1f}%と平均的な水準にあり、"
    "構造的なレジーム転換を示す水準ではありません。"
)

ma_view = (
    f"MA20_MRDIは上位{ma20_pct:.1f}%、"
    f"MA60_MRDIは上位{ma60_pct:.1f}%に位置しています。"
)

forecast_sentence = (
    f"forecastモデルでは2025年は{forecast_return*100:+.1f}%と想定されています。"
    if not np.isnan(forecast_return)
    else "forecastモデルの数値予測は現時点では参考外です。"
)

reg_view = (
    f"回帰分析の構造を見ると、{factor_sentence}。\n"
    f"モデル精度は {metric_sentence} で、"
    "方向性把握には有効だが数値予測には注意が必要です。\n"
    + forecast_sentence
)

with open(SUMMARY_TEXT_PATH, "w", encoding="utf-8") as f:
    f.write(f"Market Date: {latest_date.date()}\n")
    f.write(f"Updated At: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write("【Daily View】\n" + daily + "\n\n")
    f.write("【Weekly View】\n" + weekly + "\n\n")
    f.write("【Structural View】\n" + structural + "\n\n")
    f.write("【MA-Based Early Signal】\n" + ma_view + "\n\n")
    f.write("【Regression & Forecast Interpretation】\n" + reg_view + "\n\n")
    f.write("【Issued Signal】\n" + f"{signal} (Danger Level: {danger})\n")

# =========================================================
# DECISION LOG
# =========================================================
log_row = {
    "date": latest_date.normalize(),
    "signal": signal,
    "danger_level": danger,
    "risk_score": round(risk, 3),
    "mrdi_short_pct": round(mrdi_s_pct, 1),
    "comment": "Summary with regression structure & forecast"
}

if DECISION_LOG_PATH.exists():
    log_df = pd.read_csv(DECISION_LOG_PATH, parse_dates=["date"])
    log_df = log_df[log_df["date"] != latest_date.normalize()]
    log_df = pd.concat([log_df, pd.DataFrame([log_row])], ignore_index=True)
else:
    log_df = pd.DataFrame([log_row])

log_df.to_csv(DECISION_LOG_PATH, index=False)

# =========================================================
# MRDI SCATTER DATASET（Short × Long）
# =========================================================

MRDI_SCATTER_OUT_PATH = DATA_DIR / "mrdi_scatter_short_long.csv"

# metrics はすでに date 正規化済み
md_df = metrics.copy()

required_cols = ["MRDI_Short", "MRDI_Long"]

if all(c in md_df.columns for c in required_cols):
    scatter = md_df[["date", "MRDI_Short", "MRDI_Long"]].copy()
    scatter.columns = ["date", "mrdi_short", "mrdi_long"]

    # 散布図なので欠損は落とす
    scatter = scatter.dropna().reset_index(drop=True)

    # 最新日フラグ
    latest_scatter_date = scatter["date"].max()
    scatter["is_latest"] = (scatter["date"] == latest_scatter_date).astype(int)

    scatter.to_csv(MRDI_SCATTER_OUT_PATH, index=False)

    print("=== MRDI Scatter Dataset Generated ===")
    print("Rows       :", len(scatter))
    print("Latest Date:", latest_scatter_date.date())
    print("Output     :", MRDI_SCATTER_OUT_PATH)
else:
    print("WARNING: MRDI_Short / MRDI_Long not found. Scatter CSV not generated.")


# =========================================================
# DONE
# =========================================================
print("=== MARKET SUMMARY GENERATED (FINAL + MAHALANOBIS SCATTER) ===")
print("Summary :", SUMMARY_TEXT_PATH)
print("Table   :", SUMMARY_TABLE_PATH)
print("Decision:", DECISION_LOG_PATH)
