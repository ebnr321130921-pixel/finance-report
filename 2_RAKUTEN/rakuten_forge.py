#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rakuten Forge
==========================
Data shaping & metric generation only.

INPUT:
- daily_records.csv   (market data, normalized)
- holdings.csv        (units & initial investment)

OUTPUT:
- today_summary.csv
- daily_chart_data.csv
- cum_daily_chart_data.csv
- weekly_chart_data.csv
- cum_weekly_chart_data.csv
- monthly_chart_data.csv
- cum_monthly_chart_data.csv

NO HTML / NO UI / NO CHART LOGIC
"""

import pandas as pd
import numpy as np
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ------------------------------------------------------------
# Product mapping
# ------------------------------------------------------------
PRODUCT_MAP = {
    "楽天QQQ": "Rakuten QQQ",
    "楽天SP500": "Rakuten S&P 500",
    "楽天VTI": "Rakuten VTI",
    "楽天レバナス": "Rakuten LN"
}

JP_PRODUCTS = list(PRODUCT_MAP.keys())

# ------------------------------------------------------------
# Load source data
# ------------------------------------------------------------
def load_source():
    raw = pd.read_csv(BASE / "daily_records.csv")

    rows = []
    for jp in JP_PRODUCTS:
        rows.append(pd.DataFrame({
            "product": PRODUCT_MAP[jp],
            "market_date": pd.to_datetime(raw[f"{jp}_market_date"]),
            "nav": pd.to_numeric(raw[jp], errors="coerce"),
            "pct": pd.to_numeric(raw[f"{jp}_prev_pct"], errors="coerce"),
            "cum_pct": pd.to_numeric(raw.get(f"{jp}_cum_pct"), errors="coerce")
        }))

    records = pd.concat(rows).reset_index(drop=True)

    # --- holdings.csv 読み込み ---
    holdings = pd.read_csv(BASE / "holdings.csv")

    holdings["product"] = holdings["product"].map(PRODUCT_MAP)

    # ★ 型を強制的に数値化（重要）
    holdings["units"] = pd.to_numeric(holdings["units"], errors="coerce").fillna(0)

    return records, holdings

# ------------------------------------------------------------
# Today summary (P/L)
# ------------------------------------------------------------
def build_summary_market_daily(records):
    latest=records["market_date"].max()
    today=records[records["market_date"]==latest].copy()
    today["date"]=latest.strftime("%Y-%m-%d")
    today["prod_diff_yen_per_10k"]=today["nav"]*today["pct"]/100
    out=today[["product","date","nav","pct","prod_diff_yen_per_10k"]].rename(columns={"pct":"daily_pct"})
    out.to_csv(BASE/"summary_market_daily.csv",index=False,encoding="utf-8-sig")
    return out

def build_summary_portfolio_pnl(records, holdings):
    latest = records["market_date"].max()
    today = records[records["market_date"] == latest]

    # 型正規化
    holdings = holdings.copy()
    # --- 起点日（Zero_date） ---
    holdings["Zero_date"] = pd.to_datetime(holdings["Zero_date"], errors="coerce")
    holdings["change_date"] = pd.to_datetime(holdings["change_date"], errors="coerce")
    holdings["change_value"] = pd.to_numeric(holdings["change_value"], errors="coerce")
    holdings["units"] = pd.to_numeric(holdings["units"], errors="coerce").fillna(0)


    # 通常商品行のみ
    holdings_prod = holdings[holdings["product"].notna()]

    df = today.merge(holdings_prod, on="product", how="inner")
    df = df[df["units"] > 0]

    # 現在評価額
    df["value"] = df["units"] * df["nav"] / 10000

    # 今日の損益（円）
    df["daily_pnl_yen"] = df["units"] * df["nav"] * df["pct"] / 100 / 10000

    # 前日比率（％）
    # = 今日の損益 ÷ 前日評価額
    # 前日評価額 = value - daily_pnl_yen
    df["daily_pnl_pct"] = np.where(
        (df["value"] - df["daily_pnl_yen"]) != 0,
        df["daily_pnl_yen"] / (df["value"] - df["daily_pnl_yen"]) * 100,
        np.nan
    )

    # change_date 時点の NAV
    base_nav = (
        records.sort_values("market_date")
        .set_index(["market_date","product"])["nav"]
    )

    def lookup_base_nav(row):
        try:
            return base_nav.loc[(row["change_date"], row["product"])]
        except KeyError:
            return np.nan

    df["base_nav"] = df.apply(lookup_base_nav, axis=1)

    # change_date 時点の評価額（CSV優先）
    df["base_value"] = np.where(
        df["change_value"].notna(),
        df["change_value"],
        df["units"] * df["base_nav"] / 10000
    )

    # スイッチング以降の損益
    df["since_change_pnl_yen"] = df["value"] - df["base_value"]
    df["since_change_pnl_pct"] = df["since_change_pnl_yen"] / df["base_value"] * 100

    out = df.assign(
        date = latest.strftime("%Y-%m-%d")
    )[[
        "product","status","date","units",
        "value",
        "daily_pnl_yen","daily_pnl_pct",
        "since_change_pnl_yen","since_change_pnl_pct"
    ]]

    out.to_csv(
        BASE / "summary_portfolio_pnl.csv",
        index=False,
        encoding="utf-8-sig"
    )
    return out

# ------------------------------------------------------------
# Daily trend (20)
# ------------------------------------------------------------
def build_daily_trend(records):
    p = records.pivot_table(
        index="market_date",
        columns="product",
        values="pct"
    ).sort_index()

    p = p.tail(10)

    # ★ date を先頭列に
    p = p.reset_index()
    p.insert(0, "date", p["market_date"].dt.strftime("%Y-%m-%d"))
    p = p.drop(columns=["market_date"])

    p.to_csv(BASE/"daily_chart_data.csv", index=False, encoding="utf-8-sig")
    return p

def build_cum_daily_trend(records, holdings):
    df=records.sort_values("market_date")
    nav=df.pivot_table(index="market_date",columns="product",values="nav").sort_index()
    zero_map=holdings.dropna(subset=["product"]).set_index("product")["Zero_date"].apply(pd.to_datetime).to_dict()
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        z=zero_map.get(prod)
        if pd.isna(z):
            cum[prod]=np.nan; continue
        s=nav[prod]; s_after=s[s.index>=z]
        if s_after.empty:
            cum[prod]=np.nan; continue
        base=s_after.iloc[0]
        cum[prod]=(s/base-1)*100
    cum[prod]=(s/base-1)*100
    cum=cum.tail(10).reset_index()
    cum.insert(0,"date",cum["market_date"].dt.strftime("%Y-%m-%d"))
    cum=cum.drop(columns=["market_date"])
    cum.to_csv(BASE/"cum_daily_chart_data.csv",index=False,encoding="utf-8-sig")
    return cum

# ------------------------------------------------------------
# Weekly trend
# ------------------------------------------------------------
def build_weekly_trend(records):
    df = records.copy()
    df["week"] = df["market_date"].dt.to_period("W-MON")

    weekly = df.groupby(["week","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product")

    latest_week = weekly.index.max()
    weeks = pd.period_range(end=latest_week, periods=12, freq="W-MON")
    weekly = weekly.reindex(weeks)

    weekly = weekly.reset_index()
    weekly.rename(columns={weekly.columns[0]: "week"}, inplace=True)
    weekly["week"] = weekly["week"].apply(lambda p: f"{p.start_time.strftime('%Y-%m-%d')} ~ {(p.start_time + pd.Timedelta(days=4)).strftime('%Y-%m-%d')}")

    weekly.to_csv(BASE/"weekly_chart_data.csv", index=False, encoding="utf-8-sig")
    return weekly

def build_cum_weekly_trend(records, holdings):
    df=records.copy()
    df["week"]=df["market_date"].dt.to_period("W-MON")
    nav=df.groupby(["week","product"])["nav"].last().unstack("product")
    zero_map=holdings.dropna(subset=["product"]).set_index("product")["Zero_date"].apply(pd.to_datetime).to_dict()
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        z=zero_map.get(prod)
        if pd.isna(z):
            cum[prod]=np.nan; continue
        s=nav[prod]
        weeks=s.index.to_timestamp()
        valid=weeks>=z
        if not valid.any():
            cum[prod]=np.nan; continue
        base=s[valid].iloc[0]
        cum[prod]=(s/base-1)*100
    latest_week = nav.index.max()
    weeks = pd.period_range(end=latest_week, periods=12, freq="W-MON")
    cum = cum.reindex(weeks).reset_index()
    cum.rename(columns={cum.columns[0]: "week"}, inplace=True)
    cum["week"] = cum["week"].apply(lambda p: f"{p.start_time.strftime('%Y-%m-%d')} ~ {(p.start_time + pd.Timedelta(days=4)).strftime('%Y-%m-%d')}")

    cum.to_csv(BASE/"cum_weekly_chart_data.csv", index=False, encoding="utf-8-sig")
    return cum


# ------------------------------------------------------------
# Monthly trend
# ------------------------------------------------------------
def build_monthly_trend(records):
    df = records.copy()
    df["month"] = df["market_date"].dt.to_period("M")

    monthly = df.groupby(["month","product"]).apply(
        lambda x: (x["nav"].iloc[-1] / x["nav"].iloc[0] - 1) * 100
    ).unstack("product")

    monthly = monthly.reset_index()
    latest_month = monthly["month"].max()
    months = pd.period_range(end=latest_month, periods=12, freq="M")

    monthly = monthly.set_index("month").reindex(months).reset_index()
    monthly.rename(columns={monthly.columns[0]: "month"}, inplace=True)
    monthly["month"] = monthly["month"].apply(lambda p: p.strftime("%Y/%m"))

    monthly.to_csv(BASE/"monthly_chart_data.csv", index=False, encoding="utf-8-sig")
    return monthly

def build_cum_monthly_trend(records, holdings):
    df=records.copy()
    df["month"]=df["market_date"].dt.to_period("M")
    nav=df.groupby(["month","product"])["nav"].last().unstack("product")
    zero_map=holdings.dropna(subset=["product"]).set_index("product")["Zero_date"].apply(pd.to_datetime).to_dict()
    cum=pd.DataFrame(index=nav.index)
    for prod in nav.columns:
        z=zero_map.get(prod)
        if pd.isna(z):
            cum[prod]=np.nan; continue
        s=nav[prod]
        months=s.index.to_timestamp()
        valid=months>=z
        if not valid.any():
            cum[prod]=np.nan; continue
        base=s[valid].iloc[0]
        cum[prod]=(s/base-1)*100
    latest_month = nav.index.max()
    months = pd.period_range(end=latest_month, periods=12, freq="M")
    cum = cum.reindex(months).reset_index()
    cum.rename(columns={cum.columns[0]: "month"}, inplace=True)
    cum["month"] = cum["month"].apply(lambda p: p.strftime("%Y/%m"))

    cum.to_csv(BASE/"cum_monthly_chart_data.csv", index=False, encoding="utf-8-sig")

    return cum

# ------------------------------------------------------------
# iDeCo return (start_value -> current, CAGR)
# ------------------------------------------------------------

def build_ideco_return(records, holdings):
    latest = records["market_date"].max()

    ideco = holdings[holdings["status"] == "Ideco"].copy()
    if ideco.empty:
        return None

    ideco["units"] = pd.to_numeric(ideco["units"], errors="coerce").fillna(0)
    ideco["start"] = pd.to_datetime(ideco["start"], errors="coerce")

    ideco["start_value"] = (
        ideco["start_value"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    start_date = ideco["start"].min()
    start_value = ideco["start_value"].sum()

    if pd.isna(start_date) or pd.isna(start_value):
        print("[WARN] iDeCo start_date or start_value is invalid")
        return None

    # ======================================================
    # 最新評価額
    # ======================================================
    nav_map = (
        records[records["market_date"] == latest]
        .set_index("product")["nav"]
        .to_dict()
    )

    ideco["nav"] = ideco["product"].map(nav_map)
    ideco["current_value"] = ideco["units"] * ideco["nav"] / 10000
    end_value = ideco["current_value"].sum()

    # ======================================================
    # CAGR（理論値）
    # ======================================================
    years = (latest - start_date).days / 365.25
    if years <= 0:
        return None

    total_return = (end_value / start_value - 1) * 100
    cagr = (end_value / start_value) ** (1 / years) - 1

    # ======================================================
    # XIRR（月次拠出キャッシュフロー）
    # ======================================================
    # 月数算出
    months = (
        (latest.year - start_date.year) * 12
        + (latest.month - start_date.month)
        + 1
    )

    if months <= 0:
        return None

    monthly_contribution = start_value / months

    cashflows = []

    # 月次拠出（マイナスCF）
    for i in range(months):
        d = (start_date + pd.DateOffset(months=i)).replace(day=1)
        if d <= latest:
            cashflows.append((d, -monthly_contribution))

    # 最終評価額（プラスCF）
    cashflows.append((latest, end_value))

    def xirr(flows, guess=0.05):
        def npv(rate):
            return sum(
                cf / (1 + rate) ** ((d - flows[0][0]).days / 365.25)
                for d, cf in flows
            )

        rate = guess
        for _ in range(100):
            f = npv(rate)
            df = sum(
                -cf * ((d - flows[0][0]).days / 365.25)
                / (1 + rate) ** (((d - flows[0][0]).days / 365.25) + 1)
                for d, cf in flows
            )
            if df == 0:
                break
            rate -= f / df
        return rate

    xirr_rate = xirr(cashflows)

    # ======================================================
    # 出力
    # ======================================================
    out = pd.DataFrame([{
        "type": "iDeCo",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": latest.strftime("%Y-%m-%d"),
        "years": round(years, 2),
        "months": months,
        "start_value": round(start_value, 0),
        "end_value": round(end_value, 0),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr * 100, 2),
        "xirr_monthly_cf_pct": round(xirr_rate * 100, 2)
    }])

    out.to_csv(
        BASE / "summary_ideco_return.csv",
        index=False,
        encoding="utf-8-sig"
    )

    return out

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    records, holdings = load_source()
    build_summary_market_daily(records)
    build_summary_portfolio_pnl(records, holdings)
    build_daily_trend(records)
    build_cum_daily_trend(records, holdings)
    build_weekly_trend(records)
    build_cum_weekly_trend(records, holdings)
    build_monthly_trend(records)
    build_cum_monthly_trend(records, holdings)

    # --- iDeCo 年率 ---
    build_ideco_return(records, holdings)

    print("=== RAKUTEN FORGE DONE ===")

if __name__ == "__main__":
    main()
