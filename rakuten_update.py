#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json

# ==========================================================
# PATH
# ==========================================================
BASE = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.join(BASE, "daily_returns.csv")
MONTHLY = os.path.join(BASE, "monthly_returns.csv")

# ==========================================================
# 内蔵ファンドマスター（CSV不要）
# ==========================================================
MASTER = [
    {
        "fund_id": "JP90C000Q2U6",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000Q2U6",
        "short": "楽天VTI",
        "status": "active",
    },
    {
        "fund_id": "JP90C000QF22",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000QF22",
        "short": "楽天VT",
        "status": "active",
    },
    {
        "fund_id": "JP90C000FHD2",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000FHD2",
        "short": "USA360",
        "status": "active",
    },
    {
        "fund_id": "JP90C000MLM1",
        "url": "https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000MLM1",
        "short": "楽天Nasdaq100",
        "status": "active",
    },
]

SHORTS = [m["short"] for m in MASTER]


# ==========================================================
# MASTER LOAD
# ==========================================================
def load_master():
    df = pd.DataFrame(MASTER)
    df = df[df["status"] == "active"]
    print(f"Loaded {len(df)} funds (internal master)")
    return df


# ==========================================================
# SCRAPE FUND
# ==========================================================
def fetch_fund(url):
    r = requests.get(url)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    pm = re.search(r"基準価額\s*([\d,]+)\s*円", text)
    if not pm:
        raise ValueError("Price not found: " + url)
    price = int(pm.group(1).replace(",", ""))

    dm = re.search(r"[（(]\s*(\d{1,2})/(\d{1,2})\s*[）)]", text)
    if not dm:
        raise ValueError("Date not found: " + url)
    y = datetime.now().year
    market_date = datetime(y, int(dm.group(1)), int(dm.group(2))).strftime("%Y-%m-%d")

    return price, market_date


# ==========================================================
# FETCH ALL FUNDS
# ==========================================================
def fetch_all(df):
    out = {}
    for _, row in df.iterrows():
        price, date = fetch_fund(row["url"])
        out[row["short"]] = {
            "price": price,
            "date": date,
        }
    return out


# ==========================================================
# SAVE DAILY
# ==========================================================
def save_daily(all_data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new = {"fetch_date": now}

    # 新規 row を構築
    for short, info in all_data.items():
        new[short] = info["price"]
        new[f"{short}_date"] = info["date"]

    # CSV がない → 新規作成
    if not os.path.exists(DAILY):
        df = pd.DataFrame([new])
        df.to_csv(DAILY, index=False)
        print("Created daily CSV.")
    else:
        df = pd.read_csv(DAILY)

        # 不要列削除（念のため）
        for c in df.columns:
            if (not c.endswith("_date")) and (c not in SHORTS) and c not in ["fetch_date"]:
                df = df.drop(columns=[c])

        # 同日基準日の行を削除
        for short, info in all_data.items():
            dc = f"{short}_date"
            if dc in df.columns:
                df = df[df[dc] != info["date"]]

        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        df.sort_values("fetch_date", inplace=True)
        df.to_csv(DAILY, index=False)
        print("Updated daily CSV.")

    # Backup
    backup = DAILY.replace(".csv", f"_backup_{datetime.now().strftime('%Y-%m-%d')}.csv")
    df.to_csv(backup, index=False)
    print("Daily backup:", backup)


# ==========================================================
# BUILD MONTHLY
# ==========================================================
def build_monthly():
    if not os.path.exists(DAILY):
        print("No daily csv.")
        return

    df = pd.read_csv(DAILY)
    df["month"] = df["fetch_date"].str.slice(0, 7)

    # 月末データのみ抽出
    m_end = df.sort_values("fetch_date").groupby("month").tail(1)
    m_end.to_csv(MONTHLY, index=False)

    print("Monthly CSV updated.")

    b = MONTHLY.replace(".csv", f"_backup_{datetime.now().strftime('%Y-%m-%d')}.csv")
    m_end.to_csv(b, index=False)
    print("Monthly backup:", b)


# ==========================================================
# DASHBOARD HTML
# ==========================================================
def build_dashboard():
    if not os.path.exists(DAILY):
        print("dashboard skipped.")
        return

    df = pd.read_csv(DAILY)
    df["date"] = df["fetch_date"].str.slice(0, 10)
    df["month"] = df["fetch_date"].str.slice(0, 7)

    # ===========================
    # DAILY（方式 A：月初基準）
    # ===========================
    daily_price = {}
    daily_return = {}
    daily_cum = {}

    for short in SHORTS:
        if short not in df.columns:
            continue

        prices = df[short].tolist()

        # 月初価格辞書
        month_first = df.groupby("month")[short].first().to_dict()

        dp = []
        dr = []
        dc = []

        for _, row in df.iterrows():
            price = row[short]
            base = month_first[row["month"]]
            ret = (price - base) / base * 100

            dp.append(price)
            dr.append(round(ret, 4))
            dc.append(round(ret, 4))  # cumulative も同じ（方式A）

        daily_price[short] = dp
        daily_return[short] = dr
        daily_cum[short] = dc

    # ===========================
    # MONTHLY（方式 B：全期間基準）
    # ===========================
    if os.path.exists(MONTHLY):
        mf = pd.read_csv(MONTHLY)
        mf["date"] = mf["fetch_date"].str.slice(0, 10)
    else:
        mf = df.copy()

    monthly_price = {}
    monthly_return = {}
    monthly_cum = {}

    for short in SHORTS:
        if short not in mf.columns:
            continue
        prices = mf[short].tolist()
        base = prices[0]

        rets = [(p - base) / base * 100 for p in prices]

        monthly_price[short] = prices
        monthly_return[short] = [round(r, 4) for r in rets]
        monthly_cum[short] = [round(r, 4) for r in rets]

    # ===========================
    # JSON 化（JS が読める形式に変換）
    # ===========================
    labelsDaily = json.dumps(df["date"].tolist(), ensure_ascii=False)
    labelsMonthly = json.dumps(mf["date"].tolist(), ensure_ascii=False)

    js_daily_price = json.dumps(daily_price, ensure_ascii=False)
    js_daily_return = json.dumps(daily_return, ensure_ascii=False)
    js_daily_cum = json.dumps(daily_cum, ensure_ascii=False)

    js_month_price = json.dumps(monthly_price, ensure_ascii=False)
    js_month_return = json.dumps(monthly_return, ensure_ascii=False)
    js_month_cum = json.dumps(monthly_cum, ensure_ascii=False)

    # ===========================
    # HTML 出力
    # ===========================
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Rakuten Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body {{
  margin:0;
  background:#e8e8e8;
  font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue';
}}
.wrapper {{
  max-width:1100px;
  margin:40px auto;
  padding:20px;
}}
.card {{
  background:rgba(255,255,255,0.75);
  backdrop-filter:blur(20px);
  padding:24px;
  border-radius:20px;
  margin-bottom:40px;
  box-shadow:0 8px 30px rgba(0,0,0,0.1);
}}
.card h2 {{
  margin:0 0 12px;
  font-size:22px;
  font-weight:600;
}}
canvas {{
  width:100%;
  height:360px;
}}
</style>
</head>
<body>

<div class="wrapper">

<div class="card"><h2>Daily Price</h2><canvas id="daily_price"></canvas></div>
<div class="card"><h2>Daily Return (%)</h2><canvas id="daily_return"></canvas></div>
<div class="card"><h2>Daily Cumulative (%)</h2><canvas id="daily_cum"></canvas></div>

<div class="card"><h2>Monthly Price</h2><canvas id="month_price"></canvas></div>
<div class="card"><h2>Monthly Return (%)</h2><canvas id="month_return"></canvas></div>
<div class="card"><h2>Monthly Cumulative (%)</h2><canvas id="month_cum"></canvas></div>

</div>

<script>
const labelsDaily = {labelsDaily};
const labelsMonthly = {labelsMonthly};

const daily_price = {js_daily_price};
const daily_return = {js_daily_return};
const daily_cum = {js_daily_cum};

const monthly_price = {js_month_price};
const monthly_return = {js_month_return};
const monthly_cum = {js_month_cum};

const colors = ["#007AFF","#FF3B30","#34C759","#AF52DE"];

function makeDataset(obj){{
    let out=[];
    let i=0;
    for(let k in obj){{
        out.push({{
            label:k,
            data:obj[k],
            borderColor:colors[i%4],
            backgroundColor:colors[i%4],
            tension:0.2,
            fill:false
        }});
        i++;
    }}
    return out;
}}

function makeBarDataset(obj){{
    let out=[];
    let i=0;
    for(let k in obj){{
        out.push({{
            label:k,
            data:obj[k],
            backgroundColor:colors[i%4]
        }});
        i++;
    }}
    return out;
}}

function lineChart(id, labels, obj, yLabel){{
    new Chart(document.getElementById(id),{{
        type:"line",
        data:{{ labels:labels, datasets:makeDataset(obj) }},
        options:{{
            scales:{{
                x:{{ title:{{ display:true, text:"Date" }} }},
                y:{{
                    title:{{ display:true, text:yLabel }},
                    ticks:{{ callback:(v)=> yLabel.includes("%") ? v+"%" : v }}
                }}
            }}
        }}
    }});
}}

function barChart(id, labels, obj, yLabel){{
    new Chart(document.getElementById(id),{{
        type:"bar",
        data:{{ labels:labels, datasets:makeBarDataset(obj) }},
        options:{{
            scales:{{
                x:{{ title:{{ display:true, text:"Month" }} }},
                y:{{
                    title:{{ display:true, text:yLabel }},
                    ticks:{{ callback:(v)=> yLabel.includes("%") ? v+"%" : v }}
                }}
            }}
        }}
    }});
}}

lineChart("daily_price", labelsDaily, daily_price, "Price");
lineChart("daily_return", labelsDaily, daily_return, "Return (%)");
lineChart("daily_cum", labelsDaily, daily_cum, "Cumulative (%)");

barChart("month_price", labelsMonthly, monthly_price, "Price");
barChart("month_return", labelsMonthly, monthly_return, "Return (%)");
barChart("month_cum", labelsMonthly, monthly_cum, "Cumulative (%)");

</script>
</body>
</html>
"""

    out = os.path.join(BASE, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("dashboard.html updated:", out)


# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    print("\n=== FUND MASTER ===")
    master = load_master()

    print("\n=== FETCH ===")
    all_data = fetch_all(master)

    print("\n=== SAVE DAILY ===")
    save_daily(all_data)

    print("\n=== SAVE MONTHLY ===")
    build_monthly()

    print("\n=== DASHBOARD ===")
    build_dashboard()

    print("\n=== COMPLETED ===\n")
