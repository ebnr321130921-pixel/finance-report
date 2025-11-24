import yfinance as yf
import pandas as pd

# 取得したいティッカー
tickers = {
    "QQQ": "QQQ",
    "VTI": "VTI",
    "SP500": "^GSPC",
    "USDJPY": "JPY=X"   # ← ドル円
}

start = "2010-01-01"
end   = "2025-12-31"

dfs = {}

for name, t in tickers.items():
    print(f"Downloading: {name} ({t})")
    df = yf.download(t, start=start, end=end, progress=False)

    # auto_adjust=True の影響対策
    if "Adj Close" in df.columns:
        df = df[["Adj Close"]].rename(columns={"Adj Close": name})
    else:
        df = df[["Close"]].rename(columns={"Close": name})

    dfs[name] = df

# 全部を1つに結合
data = pd.concat(dfs.values(), axis=1)
data.dropna(inplace=True)

# 月次
monthly = data.resample('ME').ffill().pct_change().dropna()
monthly.to_csv("monthly_returns.csv")

# 年次
annual = data.resample('YE').ffill().pct_change().dropna()
annual.to_csv("annual_returns.csv")

print("完了：株価＋ドル円の月次・年次CSVを出力しました。")
