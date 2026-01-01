#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Index Viewer (FINAL / Mobile Decision UI)

Display only (NO recalculation)

- Market Performance (Daily)
- Market Performance (Weekly) [collapsible]
- Decision Index Summary
- MRDI Correlation (Short × Long, SPC-based scatter)
- RiskScore × MRDI Short (SPC-based scatter)
- Assessment (collapsible, bottom)

=========================================================
[Scatter Graph Rules — DO NOT REGRESS]
=========================================================
1) Style: Excel-like clean scatter, axis labels + ticks (min/max at least)
2) Points:
   - Base cloud: many points, small, light gray, drawn at back
   - Trace points: small, slightly stronger than base, connected with thin dotted line
   - Latest point: on top, slightly larger, colored by SPC thresholds
3) Front order (important):
   Latest point (top) -> SPC lines -> trace line/trace points -> base points (back)
4) Lines:
   - All dotted (no mixed dash styles)
   - Thin (stroke-width=1)
   - Mean: green dotted
   - +1σ: ORANGE dotted
   - +3σ: red dotted
   - Median: NOT drawn
5) Threshold color for Latest:
   - If either axis > +3σ : red
   - Else if either axis > +1σ : orange
   - Else : blue
6) Data columns:
   - mrdi_scatter_short_long.csv : date, mrdi_short, mrdi_long, risk_score, is_latest, display_roled
   - market_state_distribution_summary.csv :
       metric, mean, std, +1sigma, -1sigma, +3sigma, -3sigma, median
   - display_roled convention:
       2 = latest (top)
       1 = trace (connectable)
       0 = base cloud (back)
       0.5 etc allowed; treat as base unless you want special later
=========================================================
"""

import pandas as pd
from pathlib import Path

# =========================================================
# PATH
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SUMMARY_TABLE_PATH = DATA_DIR / "market_summary_table.csv"
METRIC_PATH = DATA_DIR / "market_state_metrics.csv"
MRDI_PATH = DATA_DIR / "mrdi_scatter_short_long.csv"
DIST_PATH = DATA_DIR / "market_state_distribution_summary.csv"
NOTES_PATH = DATA_DIR / "market_indicator_notes.csv"
# =========================================================
# Forecast Log / Actual Market
# =========================================================
ACTUAL_PATH = DATA_DIR / "market_factors_raw.csv"

OUT_HTML = BASE_DIR / "us_index.html"

# =========================================================
# Market Performance
# =========================================================
summary = pd.read_csv(SUMMARY_TABLE_PATH)
summary.columns = [c.strip() for c in summary.columns]

INDEX_ITEMS = ["QQQ", "SP500", "NASDAQ", "DOW", "VIX", "US10Y", "USDJPY"]


summary.columns = [c.strip() for c in summary.columns]


def find_col(keys, percent=None):
    for c in summary.columns:
        cl = c.lower()
        if all(k in cl for k in keys):
            if percent is None:
                return c
            if percent and "%" in c:
                return c
            if not percent and "%" not in c:
                return c
    raise KeyError(keys)

COL_ITEM   = find_col(["item"])
COL_LATEST = find_col(["latest"])
COL_DAY    = find_col(["yesterday"], percent=False)
COL_DAY_P  = find_col(["yesterday"], percent=True)
COL_WEEK   = find_col(["lastweek"], percent=False)
COL_WEEK_P = find_col(["lastweek"], percent=True)

INDEX_ITEMS = ["QQQ", "SP500", "NASDAQ", "DOW", "VIX", "US10Y", "USDJPY"]
perf = summary[summary[COL_ITEM].isin(INDEX_ITEMS)].copy()

perf["Index"] = perf[COL_ITEM]
perf["Last"]  = perf[COL_LATEST]
perf["Day"]   = perf[COL_DAY]
perf["%Day"]  = perf[COL_DAY_P]
perf["Week"]  = perf[COL_WEEK]
perf["%Week"] = perf[COL_WEEK_P]

fmt_val = lambda x: f"{x:,.2f}"
fmt_sig = lambda x: f"{x:+,.2f}"
fmt_pct = lambda x: f"{x:+.2f}%"

perf["LastDisp"]  = perf["Last"].map(fmt_val)
perf["DayDisp"]   = perf["Day"].map(fmt_sig)
perf["WeekDisp"]  = perf["Week"].map(fmt_sig)
perf["%DayDisp"]  = perf["%Day"].map(fmt_pct)
perf["%WeekDisp"] = perf["%Week"].map(fmt_pct)

# =========================================================
# Market Dates (from summary_table)
# =========================================================
# Expected columns (name flexible):
# - Market Date / Trading Date
# - Previous Date
# - Week Start
# - Week End

try:
    market_date = summary.loc[0, find_col(["market", "date"])]
except KeyError:
    market_date = ""

try:
    prev_date = summary.loc[0, find_col(["prev", "date"])]
except KeyError:
    prev_date = ""

try:
    week_start = summary.loc[0, find_col(["week", "avg", "from"])]
except KeyError:
    week_start = ""

try:
    week_end = summary.loc[0, find_col(["week", "avg", "to"])]
except KeyError:
    week_end = ""



def perf_color(index, v):
    if index == "VIX":
        return "blue" if v < 0 else "red"
    if index == "USDJPY":
        return "blue" if v > 0 else "red"
    return "blue" if v > 0 else "red"

# =========================================================
# Decision Index Summary & TOP RISK
# =========================================================
metrics = pd.read_csv(METRIC_PATH)
metrics["date"] = pd.to_datetime(metrics["date"])
latest_m = metrics.sort_values("date").iloc[-1]

def status(v, low, high):
    if v < low:
        return "LOW", "blue"
    elif v < high:
        return "NORMAL", "green"
    else:
        return "HIGH", "red"

risk_label, risk_color = status(latest_m["RiskScore"], 0.3, 0.6)

# ★ ここで追加（RISKカード用の表示クラス）
risk_class = (
    "status-risk" if str(risk_label).upper() == "HIGH"
    else "status-safe" if str(risk_label).upper() == "LOW"
    else ""
)

decision_rows = [("RiskScore", latest_m["RiskScore"], risk_label, risk_color, "Overall risk")]
for k, note in [
    ("MRDI_Short", "Short-term"),
    ("MRDI_Long",  "Structural"),
    ("MA20_MRDI",  "MA20"),
    ("MA60_MRDI",  "MA60"),
]:
    if k in latest_m:
        s, c = status(latest_m[k], 2.5, 3.5)
        decision_rows.append((k, latest_m[k], s, c, note))

# =========================================================
# Market Direction Log (Prediction)
# =========================================================
def dir_class(d: str) -> str:
    d = str(d).upper()
    if d == "UP": return "dir-up"
    if d == "DOWN": return "dir-down"
    if d == "WEAK": return "dir-weak"
    if d == "NEUTRAL": return "dir-neutral"
    return "gray"

def conf_class(c: str) -> str:
    c = str(c).upper()
    if c == "HIGH": return "conf-high"
    if c == "MID":  return "conf-mid"
    if c == "LOW":  return "conf-low"
    return "gray"

def score_class(s: float) -> str:
    try:
        v = float(s)
    except Exception:
        return "gray"
    # “感度高すぎ問題”を避けて、ざっくり3段
    if abs(v) >= 8.0: return "score-strong"
    if abs(v) >= 3.0: return "score-mid"
    return "score-weak"


# =========================================================
# MRDI / Risk Scatter Data
# =========================================================
mrdi = pd.read_csv(MRDI_PATH)
mrdi.columns = [c.strip() for c in mrdi.columns]
mrdi["date"] = pd.to_datetime(mrdi["date"])

# column name is display_roled (not display_role)
if "display_roled" not in mrdi.columns:
    if "display_role" in mrdi.columns:
        mrdi["display_roled"] = mrdi["display_role"]
    else:
        mrdi["display_roled"] = mrdi.get("is_latest", 0).apply(lambda v: 2 if float(v) == 1.0 else 0)

mrdi = mrdi.dropna(subset=["mrdi_short", "mrdi_long", "risk_score"]).sort_values("date")

# Distribution summary (metric, mean, std, +1sigma, -1sigma, +3sigma, -3sigma, median)
dist_df = pd.read_csv(DIST_PATH)
dist_df.columns = [c.strip() for c in dist_df.columns]
dist_df["metric"] = dist_df["metric"].astype(str).str.strip()
dist = dist_df.set_index("metric")

def D(metric: str, col: str) -> float:
    return float(dist.loc[metric, col])

# Stats
short_mean = D("mrdi_short", "mean")
short_1s   = D("mrdi_short", "+1sigma")
short_3s   = D("mrdi_short", "+3sigma")

long_mean  = D("mrdi_long", "mean")
long_1s    = D("mrdi_long", "+1sigma")
long_3s    = D("mrdi_long", "+3sigma")

risk_mean  = D("risk_score", "mean")
risk_1s    = D("risk_score", "+1sigma")
risk_3s    = D("risk_score", "+3sigma")

# Latest row: prefer display_roled==2, else is_latest==1, else last date
latest_candidates = mrdi[mrdi["display_roled"] == 2]
if len(latest_candidates) > 0:
    latest = latest_candidates.iloc[-1]
else:
    if "is_latest" in mrdi.columns and (mrdi["is_latest"] == 1).any():
        latest = mrdi[mrdi["is_latest"] == 1].iloc[-1]
    else:
        latest = mrdi.iloc[-1]

def latest_color_by_spc(xv: float, x1: float, x3: float, yv: float, y1: float, y3: float) -> str:
    # If either axis exceeds threshold -> color
    if xv > x3 or yv > y3:
        return "#ff3b30"  # red
    if xv > x1 or yv > y1:
        return "#ff9500"  # orange
    return "#007aff"      # blue

# =========================================================
# SVG scatter generator (shared)
# =========================================================
def build_spc_scatter_svg(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
    x_mean: float, x_1s: float, x_3s: float,
    y_mean: float, y_1s: float, y_3s: float,
    latest_row: pd.Series,
    legend_text: str,
):
    # Canvas
    W, H = 360, 230
    left, right = 50, 330
    top, bottom = 36, 195

    x = df[x_col]
    y = df[y_col]
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())

    # avoid divide-by-zero
    if x_max == x_min:
        x_max = x_min + 1e-9
    if y_max == y_min:
        y_max = y_min + 1e-9

    def cx(v): return left + (float(v) - x_min) / (x_max - x_min) * (right - left)
    def cy(v): return bottom - (float(v) - y_min) / (y_max - y_min) * (bottom - top)

    # ticks: min/max only (clean)
    tick_svg = f"""
    <text x="{left}" y="{bottom+14}" font-size="10" fill="#6e6e73">{x_min:.2f}</text>
    <text x="{right}" y="{bottom+14}" font-size="10" fill="#6e6e73" text-anchor="end">{x_max:.2f}</text>

    <text x="{left-6}" y="{bottom}" font-size="10" fill="#6e6e73" text-anchor="end">{y_min:.2f}</text>
    <text x="{left-6}" y="{top+4}" font-size="10" fill="#6e6e73" text-anchor="end">{y_max:.2f}</text>
    """

    # base points (back): display_roled == 0 or others not in (1,2)
    base_df = df[(df["display_roled"] != 1) & (df["display_roled"] != 2)]
    base_points = "".join(
        f"<circle cx='{cx(r[x_col]):.1f}' cy='{cy(r[y_col]):.1f}' r='1.6' fill='#d1d1d6'/>"
        for _, r in base_df.iterrows()
    )

    # trace points + trace line: display_roled == 1 (connect in date order)
    trace_df = df[df["display_roled"] == 1].sort_values("date")
    trace_points = "".join(
        f"<circle cx='{cx(r[x_col]):.1f}' cy='{cy(r[y_col]):.1f}' r='1.6' fill='rgba(0,122,255,0.35)'/>"
        for _, r in trace_df.iterrows()
    )

    trace_line = ""
    if len(trace_df) >= 2:
        pts = [(cx(r[x_col]), cy(r[y_col])) for _, r in trace_df.iterrows()]
        for i in range(1, len(pts)):
            x1, y1 = pts[i-1]
            x2, y2 = pts[i]
            trace_line += (
                f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                f"stroke='rgba(0,122,255,0.35)' stroke-dasharray='3,3' stroke-width='1'/>"
            )

    # SPC lines (front): mean/+1/+3
    spc_lines = f"""
    <!-- Mean (green dotted) -->
    <line x1="{cx(x_mean):.1f}" y1="{top}" x2="{cx(x_mean):.1f}" y2="{bottom}"
          stroke="#34c759" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_mean):.1f}" x2="{right}" y2="{cy(y_mean):.1f}"
          stroke="#34c759" stroke-dasharray="3,3" stroke-width="1"/>

    <!-- +1σ (ORANGE dotted) -->
    <line x1="{cx(x_1s):.1f}" y1="{top}" x2="{cx(x_1s):.1f}" y2="{bottom}"
          stroke="#ff9500" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_1s):.1f}" x2="{right}" y2="{cy(y_1s):.1f}"
          stroke="#ff9500" stroke-dasharray="3,3" stroke-width="1"/>

    <!-- +3σ (red dotted) -->
    <line x1="{cx(x_3s):.1f}" y1="{top}" x2="{cx(x_3s):.1f}" y2="{bottom}"
          stroke="#ff3b30" stroke-dasharray="3,3" stroke-width="1"/>
    <line x1="{left}" y1="{cy(y_3s):.1f}" x2="{right}" y2="{cy(y_3s):.1f}"
          stroke="#ff3b30" stroke-dasharray="3,3" stroke-width="1"/>
    """

    # Latest point (top)
    lx, ly = cx(latest_row[x_col]), cy(latest_row[y_col])
    latest_fill = latest_color_by_spc(float(latest_row[x_col]), x_1s, x_3s, float(latest_row[y_col]), y_1s, y_3s)
    latest_point = f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.6' fill='{latest_fill}'/>"

    # Axes
    axes = f"""
    <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#c7c7cc"/>
    <line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#c7c7cc"/>

    <text x="{(left+right)/2:.1f}" y="{H-6}" font-size="11"
      fill="#6e6e73" text-anchor="middle">{x_label}</text>
    <text x="15" y="{(top+bottom)/2:.1f}" font-size="11" fill="#6e6e73"
          transform="rotate(-90 15 {(top+bottom)/2:.1f})">{y_label}</text>
    """

    # Legend
    legend = f"""
    <rect x="60" y="50" width="240" height="28" rx="6" fill="#ffffff" stroke="#e5e5ea"/>
    <text x="70" y="69" font-size="11" fill="#6e6e73">{legend_text}</text>
    """

    svg = f"""
    <svg viewBox="0 0 {W} {H}">
      <!-- Axes -->
      {axes}

      <!-- Ticks (min/max) -->
      {tick_svg}

      <!-- Base points (BACK) -->
      {base_points}

      <!-- Trace line (middle) -->
      {trace_line}

      <!-- Trace points (middle) -->
      {trace_points}

      <!-- SPC lines (FRONT) -->
      {spc_lines}

      <!-- Latest point (TOP) -->
      {latest_point}

      <!-- Legend -->
      {legend}
    </svg>
    """
    return svg

# =========================================================
# SVG histogram generator (SPC aligned)
# =========================================================
def build_histogram_svg(series, title, mean=None, s1=None, s3=None, latest=None):
    import numpy as np

    data = series.dropna().values
    if len(data) == 0:
        return ""

    W, H = 360, 78
    left, right = 40, 330
    top, bottom = 14, 64

    bins = 30  # ← 指定どおり30

    hist, edges = np.histogram(data, bins=bins)
    max_h = hist.max() if hist.max() > 0 else 1

    def cx(v):
        return left + (v - edges[0]) / (edges[-1] - edges[0]) * (right - left)

    def cy(v):
        return bottom - (v / max_h) * (bottom - top)

    bars = ""
    for h, x0, x1 in zip(hist, edges[:-1], edges[1:]):
        x = cx(x0)
        w = cx(x1) - cx(x0)
        y = cy(h)
        bars += (
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{bottom-y:.1f}' "
            f"fill='#d1d1d6'/>"
        )

    def vline(val, color, dashed=True):
        if val is None:
            return ""
        x = cx(val)
        dash = " stroke-dasharray='3,3'" if dashed else ""
        return (
            f"<line x1='{x:.1f}' y1='{top}' x2='{x:.1f}' y2='{bottom}' "
            f"stroke='{color}'{dash} stroke-width='1'/>"
            f"<text x='{x:.1f}' y='{top-6}' font-size='7' fill='{color}' opacity='0.85' "
            f"text-anchor='middle' "
            f"transform='rotate(-90 {x:.1f} {top-6})'>"
            f"{val:.2f}</text>"
        )

    lines = ""
    # Mean / +1σ / +3σ は点線のまま
    lines += vline(mean, "#34c759", dashed=True)
    lines += vline(s1,   "#ff9500", dashed=True)
    lines += vline(s3,   "#ff3b30", dashed=True)

    # Latest だけ実線（紛らわしさ回避）
    if latest is not None:
        if s3 is not None and latest > s3:
            c = "#ff3b30"
        elif s1 is not None and latest > s1:
            c = "#ff9500"
        else:
            c = "#007aff"
        lines += vline(latest, c, dashed=False)


    x_min = edges[0]
    x_max = edges[-1]

    svg = f"""
    <svg viewBox="0 0 {W} {H}">
    {bars}
    {lines}

    <!-- Legend (Right) -->
    <text x="{right+6}" y="{top+10}" font-size="7" fill="#34c759" opacity="0.85">Mean</text>
    <text x="{right+6}" y="{top+22}" font-size="7" fill="#ff9500" opacity="0.85">+1σ</text>
    <text x="{right+6}" y="{top+34}" font-size="7" fill="#ff3b30" opacity="0.85">+3σ</text>
    <text x="{right+6}" y="{top+46}" font-size="7" fill="#007aff" opacity="0.85">Latest</text>

    <text x="10" y="{bottom:.1f}"
    font-size="9" fill="#6e6e73"
    text-anchor="start"
    transform="rotate(-90 10 {bottom:.1f})">
    {title}

    </svg>
    """
    return svg

# =========================================================
# Build 2 scatter SVGs
#   - MRDI Short×Long
#   - RiskScore×MRDI Short
#   (RiskScore×MRDI Long is REMOVED)
# =========================================================
svg_mrdi = build_spc_scatter_svg(
    df=mrdi,
    x_col="mrdi_short",
    y_col="mrdi_long",
    x_label="MRDI Short",
    y_label="MRDI Long",
    x_mean=short_mean, x_1s=short_1s, x_3s=short_3s,
    y_mean=long_mean,  y_1s=long_1s,  y_3s=long_3s,
    latest_row=latest,
    legend_text=f"Today : Short {float(latest.mrdi_short):.2f} / Long {float(latest.mrdi_long):.2f}",
)

svg_risk_short = build_spc_scatter_svg(
    df=mrdi,
    x_col="risk_score",
    y_col="mrdi_short",
    x_label="RiskScore",
    y_label="MRDI Short",
    x_mean=risk_mean, x_1s=risk_1s, x_3s=risk_3s,
    y_mean=short_mean, y_1s=short_1s, y_3s=short_3s,
    latest_row=latest,
    legend_text=f"Today : Risk {float(latest.risk_score):.2f} / MRDI Short {float(latest.mrdi_short):.2f}",
)

# =========================================================
# Histograms (Distribution / SPC aligned)
# =========================================================
hist_mrdi_short = build_histogram_svg(
    mrdi["mrdi_short"], "MRDI Short",
    mean=short_mean,
    s1=short_1s,
    s3=short_3s,
    latest=float(latest.mrdi_short),
)

hist_mrdi_long = build_histogram_svg(
    mrdi["mrdi_long"], "MRDI Long",
    mean=long_mean,
    s1=long_1s,
    s3=long_3s,
    latest=float(latest.mrdi_long)
)

hist_ma20 = build_histogram_svg(
    mrdi["ma20_mrdi"], "MA20 MRDI",
    mean=D("ma20_mrdi", "mean"),
    s1=D("ma20_mrdi", "+1sigma"),
    s3=D("ma20_mrdi", "+3sigma"),
    latest=float(latest.ma20_mrdi)
)

hist_ma60 = build_histogram_svg(
    mrdi["ma60_mrdi"], "MA60 MRDI",
    mean=D("ma60_mrdi", "mean"),
    s1=D("ma60_mrdi", "+1sigma"),
    s3=D("ma60_mrdi", "+3sigma"),
    latest=float(latest.ma60_mrdi)
)

# =========================================================
# Forecast Summary (Display Only)
#   Columns: Asset / Horizon / Period / Forecast / Direction
# =========================================================
FORECAST_TODAY_PATH = DATA_DIR / "today_market_decision_summary.csv"

forecast_html = ""
if FORECAST_TODAY_PATH.exists():
    fdf = pd.read_csv(FORECAST_TODAY_PATH)

    def period_2lines(v):
        s, e = map(str.strip, str(v).split("→", 1))
        return f"{s}<br><span class='soft'>{e}</span>"

    rows = []
    for asset in ["QQQ", "SP500"]:
        sub = fdf[fdf["asset"] == asset]

        for h in ["1W", "1M"]:
            r = sub[sub["forecast_horizon"].astype(str).str.upper() == h].iloc[0]
            ret = float(r["predicted_return"]) * 100

            rows.append(f"""
            <tr>
              <td>{asset}</td>
              <td class="soft">{h}</td>
              <td class="soft">{period_2lines(r["forecast_period"])}</td>
              <td class="num">{ret:.2f}%</td>
              <td class="dir-{str(r["predicted_direction"]).lower()}">{r["predicted_direction"]}</td>
            </tr>
            """)

    forecast_html = f"""
    <div class="card">
    <h2>Forecast Summary</h2>
    <table>
      <colgroup>
        <col style="width:18%">
        <col style="width:10%">
        <col style="width:32%">
        <col style="width:20%">
        <col style="width:20%">
      </colgroup>
      <tr>
        <th>Asset</th>
        <th>Horizon</th>
        <th>Period</th>
        <th>Forecast</th>
        <th>Direction</th>
      </tr>
      {''.join(rows)}
    </table>
    </div>
    """

# =========================================================
# Market Decision (Shock Summary)  ※ NEW
#   Columns:
#     Asset / Horizon / StartDate / EndDate / Shock Score / Rank
# =========================================================
DECISION_CUR_PATH = DATA_DIR / "market_decision_current.csv"

decision_html = ""
if DECISION_CUR_PATH.exists():
    ddf = pd.read_csv(DECISION_CUR_PATH)

    def shock_color(score):
        try:
            v = float(score)
        except Exception:
            return ""
        if v >= 3.0:
            return "status-risk"   # 赤
        if v >= 2.0:
            return "status-warn"   # ピンク
        return ""

    rows = []
    for _, r in ddf.iterrows():
        rows.append(f"""
        <tr>
          <td>{r['asset']}</td>
          <td class="soft">{r['horizon']}</td>
          <td class="soft">
            {str(r['start_date'])}<br>
            <span class="soft">{str(r['end_date'])}</span>
          </td>
          <td class="num {shock_color(r['shock_score'])}">
            {float(r['shock_score']):.2f}
          </td>
          <td class="{shock_color(r['shock_score'])}">
            {r['shock_rank']}
          </td>
        </tr>
        """)

    decision_html = f"""
    <div class="card">
    <h2>Market Decision (Shock)</h2>
    <table>
      <colgroup>
        <col style="width:18%">
        <col style="width:10%">
        <col style="width:32%">
        <col style="width:20%">
        <col style="width:20%">
      </colgroup>
      <tr>
        <th>Asset</th>
        <th>Horizon</th>
        <th>Period</th>
        <th>Score</th>
        <th>Status</th>
      </tr>
      {''.join(rows)}
    </table>
    </div>
    """

# =========================================================
# Market Decision Trend (1M / Weekly)  ※ NEW
# =========================================================
DECISION_CHART_PATH = DATA_DIR / "market_decision_chart_weekly.csv"

# ここでは「読むだけ」：Forecast Trend 側の week と同期してから HTML を作る
decision_cdf = None
decision_chart_html = ""

if DECISION_CHART_PATH.exists():
    decision_cdf = pd.read_csv(DECISION_CHART_PATH)
    decision_cdf["week"] = pd.to_datetime(decision_cdf["week"])

# =========================================================
# Forecast Evaluation (Actualized / Display Only)
#   Columns: Asset / Horizon / Period / Forecast / Actual
# =========================================================
EVAL_PATH = DATA_DIR / "forecast_actual_comparison_today.csv"

forecast_eval_html = ""
if EVAL_PATH.exists():
    edf = pd.read_csv(EVAL_PATH)

    def period_2lines(v):
        s, e = map(str.strip, str(v).split("→", 1))
        return f"{s}<br><span class='soft'>{e}</span>"

    rows = []
    order = {"1W": 0, "1M": 1}

    for asset in ["QQQ", "SP500"]:
        sub = (
            edf.loc[edf["asset"] == asset]
               .assign(_o=lambda x: x["forecast_horizon"].map(order))
               .sort_values("_o")
        )

        for _, r in sub.iterrows():
            pred = float(r["predicted_return"]) * 100
            act  = float(r["actual_return"]) * 100

            rows.append(f"""
            <tr>
            <td>{asset}</td>
            <td class="soft">{r["forecast_horizon"]}</td>
            <td class="soft">{period_2lines(r["forecast_period"])}</td>
            <td class="num {'perf-safe' if pred >= 0 else 'perf-risk'}">{pred:.2f}%</td>
            <td class="num {'perf-safe' if act  >= 0 else 'perf-risk'}">{act:.2f}%</td>
            </tr>
            """)

    forecast_eval_html = f"""
    <div class="card">
    <h2>Forecast Evaluation (Actualized)</h2>
    <table>
      <colgroup>
        <col style="width:18%">
        <col style="width:10%">
        <col style="width:32%">
        <col style="width:20%">
        <col style="width:20%">
      </colgroup>
      <tr>
        <th>Asset</th>
        <th>Horizon</th>
        <th>Period</th>
        <th>Forecast</th>
        <th>Actual</th>
      </tr>
      {''.join(rows)}
    </table>
    </div>
    """

# =========================================================
# Forecast Trend Chart (1M / Weekly)  ※ 正式版
# =========================================================
TREND_PATH = DATA_DIR / "forecast_trend_weekly.csv"

forecast_trend_html = ""
if TREND_PATH.exists():
    tdf = pd.read_csv(TREND_PATH)
    tdf["week"] = pd.to_datetime(tdf["week"])

    # --- 中心日：今日 ---
    center = pd.Timestamp.today().normalize()
    start  = center - pd.DateOffset(months=3)
    end    = center + pd.DateOffset(months=3)

    tdf = tdf[(tdf["week"] >= start) & (tdf["week"] <= end)].sort_values("week")

    def js_array(s):
        return "[" + ",".join(
            "null" if pd.isna(v) else f"{float(v)*100:.2f}"
            for v in s
        ) + "]"

    # =========================================================
    # Market Decision Trend (1M / Weekly)
    #   ※ Forecast Trend と横軸完全同期（labels / range 共通）
    # =========================================================
    base_weeks = tdf["week"]
    labels = "[" + ",".join(f"'{d.strftime('%Y-%m-%d')}'" for d in base_weeks) + "]"

    def js_arr(s):
        return "[" + ",".join(
            "null" if pd.isna(v) else f"{float(v):.2f}"
            for v in s
        ) + "]"

    if decision_cdf is not None:
        cdf_sync = (
            decision_cdf
            .set_index("week")
            .reindex(base_weeks)
            .reset_index()
        )

        decision_chart_tpl = """
        <div class="card">
        <details>
        <summary>Market Decision Trend (Weekly / Monthly)</summary>

        <h3 class="soft">Weekly</h3>
        <canvas id="decWeekly" height="180"></canvas>
        <h3 class="soft">Monthly</h3>
        <canvas id="decMonthly" height="180"></canvas>

        <script>
        const dlabels = __LABELS__;

        function buildDecision(id, datasets, ymax) {
          new Chart(
            document.getElementById(id),
            {
              type: 'line',
              data: {
                labels: dlabels,
                datasets: datasets
              },
              options: {
                responsive: true,
                scales: {
                  y: {
                    min: 0,
                    max: ymax,
                    title: { display: true, text: 'Shock Score' }
                  },
                  x: {
                    title: { display: true, text: 'Week' }
                  }
                },
                plugins: {
                  legend: { position: 'bottom' }
                }
              }
            }
          );
        }

        // Weekly（QQQ=水色 / SP500=ピンク / 2・3ラインあり）
        buildDecision(
          'decWeekly',
          [
            {label:'QQQ', data:__QQQ_W_DATA__, borderColor:'#5ac8fa', borderDash:[3,3], borderWidth:1},
            {label:'SP500', data:__SP_W_DATA__, borderColor:'#ff9bb0', borderWidth:1},
            {label:'2', data:new Array(dlabels.length).fill(2), borderColor:'#ff9500', borderDash:[4,4], pointRadius:0},
            {label:'3', data:new Array(dlabels.length).fill(3), borderColor:'#ff3b30', borderDash:[4,4], pointRadius:0}
          ],
          5
        );

        // Monthly（3ライン無し）
        buildDecision(
          'decMonthly',
          [
            {label:'QQQ', data:__QQQ_M_DATA__, borderColor:'#5ac8fa', borderDash:[3,3], borderWidth:1},
            {label:'SP500', data:__SP_M_DATA__, borderColor:'#ff9bb0', borderWidth:1},
            {label:'2', data:new Array(dlabels.length).fill(2), borderColor:'#ff9500', borderDash:[4,4], pointRadius:0}
          ],
          5
        );
        </script>

        </details>
        </div>
        """

        decision_chart_html = (
            decision_chart_tpl
            .replace("__LABELS__", labels)
            .replace("__QQQ_W_DATA__", js_arr(cdf_sync["QQQ_1W_shock_score"]))
            .replace("__SP_W_DATA__",  js_arr(cdf_sync["SP_1W_shock_score"]))
            .replace("__QQQ_M_DATA__", js_arr(cdf_sync["QQQ_1M_shock_score"]))
            .replace("__SP_M_DATA__",  js_arr(cdf_sync["SP_1M_shock_score"]))
        )

    forecast_trend_html = f"""
        <h3 class="soft">QQQ</h3>
        <canvas id="trendQQQ" height="180"></canvas>
        <h3 class="soft">SP500</h3>
        <canvas id="trendSP" height="180"></canvas>

    <script>
        const labels = {labels};

        // QQQ を基準にオートスケール（SP500 も同一軸で描画）
        const QQQ_PRED_1M = {js_array(tdf["qqq_pred_1m_cum"])};

        function calcSharedY(baseArray) {{
          const values = baseArray
            .filter(v => v !== null && !isNaN(v));

          if (values.length === 0) {{
            return {{}}; // Chart.js に任せる（完全オート）
          }}

          let min = Math.min(...values);
          let max = Math.max(...values);

          const pad = (max - min) * 0.1 || 1;

          return {{
            min: min - pad,
            max: max + pad
          }};
        }}

        const sharedY = {{
          ...calcSharedY(QQQ_PRED_1M),   // ← QQQ 基準で自動スケール
          title: {{ display: true, text: 'Forward 1M Cumulative Return (%)' }},
          ticks: {{
            stepSize: 5,                // ★ 5% 刻み
            callback: v => v + '%'
          }}
        }};


        function buildTrend(id, pred, act) {{
          new Chart(
            document.getElementById(id),
            {{
              type: 'line',
              data: {{
                labels: labels,
                datasets: [
                  {{ label: 'Forecast (1M)', data: pred, borderDash: [3,3], borderWidth: 1 }},
                  {{ label: 'Actual (1M)',   data: act,  borderWidth: 1 }}
                ]
              }},
              options: {{
                responsive: true,
                scales: {{
                  y: sharedY,
                  x: {{ title: {{ display: true, text: 'Week' }} }}
                }},
                plugins: {{
                  legend: {{ position: 'bottom' }}
                }}
              }}
            }}
          );
        }}

        // ★★★★★ ここが重要 ★★★★★
        buildTrend(
          'trendQQQ',
          {js_array(tdf["qqq_pred_1m_cum"])},
          {js_array(tdf["qqq_actual_1m_cum"])}
        );

        buildTrend(
          'trendSP',
          {js_array(tdf["sp_pred_1m_cum"])},
          {js_array(tdf["sp_actual_1m_cum"])}
        );
    </script>

    """

# =========================================================
# HTML
# =========================================================
html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Market Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
:root {{
  font-size:15px;

  /* base text */
  --fg-main:#2c2c2e;
  --fg-sub:#6e6e73;
  --fg-soft:#8e8e93;

  /* semantic colors */
  --safe:#5ac8fa;   /* 水色：好ましい */
  --risk:#ff9bb0;   /* ピンク：危険 */

  /* bg */
  --bg:#f5f5f7;
  --card:#ffffff;
  --line:#e5e5ea;
}}

body {{
  margin:0;
  padding:12px;
  background:var(--bg);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Helvetica,Arial;
  color:var(--fg-main);
}}

.card {{
  background:var(--card);
  border-radius:14px;
  padding:14px;
  margin-bottom:16px;
}}

h2 {{
  margin:0 0 10px 0;
  font-size:1.05rem;
  font-weight:400;
  color:var(--fg-sub);    /* ← グレー */
  position:relative;
  padding-left:10px;
}}


h2::before {{
  content:"";
  position:absolute;
  left:0;
  top:3px;
  bottom:3px;
  width:3px;
  border-radius:2px;
  background:var(--safe);
  opacity:0.35;
}}

table {{
  width:100%;
  border-collapse:collapse;
  table-layout:fixed;
}}

th, td {{
  padding:6px 8px;
  font-size:0.9rem;
  font-weight:400;
  color:var(--fg-sub);    /* ← 全部グレーに統一 */
  text-align:right;
  vertical-align:middle;
}}

th {{
  color:var(--fg-sub);
}}

th:first-child,
td:first-child {{
  text-align:left;
}}

tr:nth-child(even) {{
  background:#fafafa;
}}

/* utility */
.gray {{ color:var(--fg-sub); }}
.soft {{ color:var(--fg-soft); }}
.num  {{ letter-spacing:0.02em; }}

/* semantic values */
.val-pos {{ color:var(--safe); }}
.val-neg {{ color:var(--risk); }}

/* performance % only */
.perf-safe {{ color:var(--safe); }}
.perf-risk {{ color:var(--risk); }}

/* status */
.status-safe   {{ color:var(--safe); }}
.status-risk   {{ color:var(--risk); }}
.status-normal {{ color:#34c759; }}   /* ← Normal は緑 */

.dir-up   {{ color:var(--safe); }}
.dir-down {{ color:var(--risk); }}
.dir-weak {{ color:var(--fg-soft); }}
.dir-neutral {{ color:var(--fg-soft); }}

details summary {{
  cursor:pointer;
  font-weight:400;
}}

svg {{
  width:100%;
  height:auto;
}}

/* ===============================
   TOP RISK (HIGH / LOW emphasis)
================================ */
.risk-card {{
  text-align: center;
  border-radius: 14px;
  padding: 14px;
}}

/* タイトルは常にニュートラル */
.risk-title {{
  font-size: 0.9rem;
  color: var(--fg-soft);
}}

/* 値そのもの */
.risk-value {{
  margin-top: 4px;
  font-size: 1.6rem;
  font-weight: 500;
  letter-spacing: 0.06em;
}}

/* ===============================
   RISK background (subtle)
   LOW / HIGH のみ空気感を変える
================================ */

/* HIGH：ほんのりピンク */
.risk-card .status-risk {{
  background: rgba(255, 155, 176, 0.08);
  border-radius: 10px;
  padding: 6px 0;
}}

/* LOW：ほんのり水色 */
.risk-card .status-safe {{
  background: rgba(90, 200, 250, 0.10);
  border-radius: 10px;
  padding: 6px 0;
}}

</style>
</head>

<body>

<!-- ===============================
     RISK (label only)
     ※ RiskScore のラベルは「高いほど危険」なので HIGH はピンク寄り
================================ -->
<div class="card risk-card">
  <div class="risk-title">RISK</div>
  <div class="risk-value {risk_class if risk_label!='NORMAL' else 'status-normal'}">
    {risk_label}
  </div>
  <div class="soft" style="margin-top:4px;">
  </div>
</div>

<div class="card soft">
  Market Date : {market_date}<br>
  Previous Trade : {prev_date}<br>
  Week Range : {week_start} – {week_end}
</div>

<!-- ===============================
     Market Performance (Daily)
     ルール：
       - %だけ色付け
       - VIX, US10Y は「下がると嬉しい」
       - それ以外は「上がると嬉しい」
================================ -->
<div class="card">
<h2>Market Performance (Daily)</h2>
<table>
<colgroup>
  <col style="width:18%">
  <col style="width:12%">
  <col style="width:30%">
  <col style="width:20%">
  <col style="width:20%">
</colgroup>
<tr>
  <th>Index</th>
  <th colspan="2">Last</th>
  <th>Day</th>
  <th>%</th>
</tr>
{''.join(
f"<tr><td>{r.Index}</td>"
f"<td colspan='2' class='num'>{r.LastDisp}</td>"
f"<td class='num'>{r.DayDisp}</td>"
f"<td class='num {('perf-safe' if ((r.Index in ['VIX','US10Y'] and float(r['%Day']) < 0) or (r.Index not in ['VIX','US10Y'] and float(r['%Day']) > 0)) else 'perf-risk')}'>{r['%DayDisp']}</td></tr>"
for _, r in perf.iterrows())}
</table>
</div>

<!-- ===============================
     Market Performance (Weekly)
================================ -->
<div class="card">
<details>
<summary>Market Performance (Weekly)</summary>
<table>
<colgroup>
  <col style="width:18%">
  <col style="width:12%">
  <col style="width:30%">
  <col style="width:20%">
  <col style="width:20%">
</colgroup>
<tr>
  <th>Index</th>
  <th colspan="2">Last</th>
  <th>Week</th>
  <th>%</th>
</tr>
{''.join(
f"<tr><td>{r.Index}</td>"
f"<td colspan='2' class='num'>{r.LastDisp}</td>"
f"<td class='num'>{r.WeekDisp}</td>"
f"<td class='num {('perf-safe' if ((r.Index in ['VIX','US10Y'] and float(r['%Week']) < 0) or (r.Index not in ['VIX','US10Y'] and float(r['%Week']) > 0)) else 'perf-risk')}'>{r['%WeekDisp']}</td></tr>"
for _, r in perf.iterrows())}
</table>
</details>
</div>

<!-- ===============================
     Decision Index Summary
     ルール：
       - HIGH / UP    → ピンク（危険）
       - LOW / DOWN   → 水色（安全）
       - NORMAL       → そのまま
     ※ decision_rows の s は "LOW / NORMAL / HIGH" を想定
================================ -->
<div class="card">
<h2>Decision Index Summary</h2>
<table>
<colgroup>
  <col style="width:32%">
  <col style="width:18%">
  <col style="width:20%">
  <col style="width:30%">
</colgroup>
<tr>
  <th>Index</th>
  <th>Value</th>
  <th>Status</th>
  <th>Note</th>
</tr>
{''.join(
    (
        (lambda status_class:
            f"<tr>"
            f"<td>{n}</td>"
            f"<td class='num'>{float(v):.2f}</td>"
            f"<td class='{status_class}'>{s}</td>"
            f"<td class='soft'>{note}</td>"
            f"</tr>"
        )(
            "status-risk" if str(s).upper() in ["HIGH", "UP"]
            else "status-safe" if str(s).upper() in ["LOW", "DOWN"]
            else "status-normal"
        )
    )
    for n, v, s, c, note in decision_rows
)}
</table>
</div>

<!-- ===============================
     Forecast / Actual
     ルール：
       - + は水色
       - - はピンク
   ※ forecast_html / forecast_eval_html 側で class を付与していないなら、
      そこも同じルールで class を付けてください（次の差分でやります）
================================ -->
{forecast_html}
{forecast_eval_html}

<div class="card">
<details>
<summary>Forecast Trend (1M / Weekly)</summary>
<div class="inner">
{forecast_trend_html}
</div>
</details>
</div>

{decision_html}
{decision_chart_html}

<div class="card">
<h2>MRDI Correlation (Short × Long)</h2>
{svg_mrdi}
</div>

<div class="card">
<h2>RiskScore × MRDI Short</h2>
{svg_risk_short}
</div>

<div class="card">
<h2>Distributions</h2>
{hist_mrdi_short}
{hist_mrdi_long}
{hist_ma20}
{hist_ma60}
</div>

</body>
</html>
"""
# =========================================================
# WRITE HTML
# =========================================================
OUT_HTML.write_text(html, encoding="utf-8")
print(f"GENERATED: {OUT_HTML}")
