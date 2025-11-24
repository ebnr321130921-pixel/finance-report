# =============================================================
# Ultimate Premium UI Version（Ver26）
# Apple-grade UI + High-end aluminum background + Premium White Glass Cards
# PC version only（no mobile HTML）
# =============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import matplotlib as mpl

# -------------------------------------------------------------
# Apple Style Graph Font
# -------------------------------------------------------------
plt.style.use("seaborn-v0_8-whitegrid")
mpl.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'font.family': 'Helvetica Neue',
    'axes.labelsize': 10,
    'axes.titlesize': 11,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
})

def img_to_base64():
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# -------------------------------------------------------------
# Load CSV
# -------------------------------------------------------------
df = pd.read_csv("monthly_returns.csv", skiprows=[1,2])
df["Date"] = pd.to_datetime(df["Price"], errors="coerce")
df = df.drop(columns=["Price"])
df = df.dropna(subset=["Date"])
df = df.set_index("Date")

for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df["year"] = df.index.year
df["month"] = df.index.month

QQQ = "QQQ"
SPX = "SP500"

# -------------------------------------------------------------
# Axis Specs
# -------------------------------------------------------------
SCATTER_MIN = -0.15
SCATTER_MAX =  0.15

BAR_MIN = -15
BAR_MAX =  15

ANNUAL_MIN = -60
ANNUAL_MAX =  60


# -------------------------------------------------------------
# Premium PC CSS（Metal + White Glass）
# -------------------------------------------------------------
CSS_PC = """
<style>

body {
    font-family: Helvetica, Arial;
    padding: 24px;
    margin: 0;
    display: flex;
    flex-direction: column;
    align-items: center;

    background-color: #c4c4c4;

    background-image:
        radial-gradient(circle at 50% 18%, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.15) 40%, rgba(0,0,0,0.25) 100%),
        linear-gradient(90deg, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0.10) 8%, rgba(255,255,255,0.00) 12%, rgba(0,0,0,0.08) 50%, rgba(255,255,255,0.00) 88%, rgba(255,255,255,0.35) 100%),
        repeating-linear-gradient(90deg, rgba(255,255,255,0.12) 0px, rgba(255,255,255,0.03) 1px, rgba(0,0,0,0.04) 2px, rgba(255,255,255,0.04) 3px),
        repeating-linear-gradient(0deg, rgba(255,255,255,0.03) 0px, rgba(0,0,0,0.05) 2px);

    background-blend-mode: overlay, screen, normal, normal;
}

#container {
    width: 1180px;
    max-width: 94%;
}

.card {
    background: linear-gradient(
        160deg,
        rgba(255,255,255,0.92) 0%,
        rgba(255,255,255,0.86) 40%,
        rgba(255,255,255,0.82) 100%
    );
    border-radius: 18px;

    backdrop-filter: blur(12px) saturate(150%);
    -webkit-backdrop-filter: blur(12px) saturate(150%);

    border: 0.5px solid rgba(255,255,255,0.65);

    box-shadow:
        0 1px 2px rgba(255,255,255,0.55) inset,
        0 12px 28px rgba(0,0,0,0.25);

    padding: 22px;
    margin-bottom: 32px;

    transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.card:hover {
    transform: translateY(-3px);
    box-shadow:
        0 1px 3px rgba(255,255,255,0.6) inset,
        0 18px 34px rgba(0,0,0,0.32);
}

h1 {
    font-size: 34px;
    font-weight: 600;
    text-align: center;
    margin-bottom: 32px;

    background: linear-gradient(180deg, #ffffff 0%, #dcdcdc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;

    text-shadow: 0 2px 4px rgba(0,0,0,0.25);
}

h2 {
    font-size: 20px;
    font-weight: 500;

    background: linear-gradient(180deg, #ffffff 0%, #dfdfdf 95%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;

    text-shadow: 0 1px 2px rgba(0,0,0,0.22);

    margin-top: 6px;
    margin-bottom: 18px;
}

img {
    width: 100%;
    border-radius: 14px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.22);
}

</style>
"""

def base_html(css, body):
    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{css}
</head>
<body>
<div id="container">
{body}
</div>
</body>
</html>
"""

html_body = "<h1>Finance Report (Ver26)</h1>"

# -------------------------------------------------------------
# 1. Overall Scatter + Monthly
# -------------------------------------------------------------
plt.figure(figsize=(11,4))

# Scatter
plt.subplot(1,2,1)
x = df[SPX]
y = df[QQQ]

slope, intercept = np.polyfit(x, y, 1)
r = np.corrcoef(x, y)[0,1]
r2 = r**2

plt.scatter(x, y, color="#4da6ff", alpha=0.65)
xs = np.linspace(SCATTER_MIN, SCATTER_MAX, 100)
plt.plot(xs, slope*xs + intercept, color="red", linewidth=2)

plt.title(f"Overall Correlation  (Beta={slope:.2f}, R²={r2:.2f})")
plt.xlabel("SP500 Return")
plt.ylabel("QQQ Return")
plt.xlim(SCATTER_MIN, SCATTER_MAX)
plt.ylim(SCATTER_MIN, SCATTER_MAX)
plt.gca().set_aspect('equal', adjustable='box')
plt.grid(True)

# Monthly
plt.subplot(1,2,2)
ov = df.groupby("month")[[QQQ, SPX]].mean().reindex(range(1,13)).fillna(0)
diff = ov[QQQ] - ov[SPX]
m = ov.index
w = 0.35

plt.bar(m - w/2, ov[QQQ]*100, w, color="#4da6ff")
plt.bar(m + w/2, ov[SPX]*100, w, color="#ff9999")
plt.plot(m, diff*100, marker="o", color="red", linewidth=2)

plt.title("Overall Monthly (%)")
plt.xlabel("Month")
plt.ylabel("Return (%)")
plt.ylim(BAR_MIN, BAR_MAX)
plt.grid(True)

img = img_to_base64()
plt.close()

html_body += f"""
<div class="card">
<h2>Overall Summary</h2>
<img src="data:image/png;base64,{img}">
</div>
"""

# -------------------------------------------------------------
# 2. Annual Return Summary（±60% / 10%刻み）
# -------------------------------------------------------------
year_ret = df.groupby("year")[[QQQ, SPX]].apply(lambda x:(1+x).cumprod().iloc[-1]-1)
years = year_ret.index

plt.figure(figsize=(8,4))
plt.plot(years, year_ret[QQQ]*100, marker="o", color="#4da6ff", linewidth=2)
plt.plot(years, year_ret[SPX]*100, marker="o", color="#ff9999", linewidth=2)

plt.axhline(0, color="black")
plt.ylim(ANNUAL_MIN, ANNUAL_MAX)
plt.yticks(range(-60, 61, 10))
plt.grid(True)
plt.title("Annual Total Return (%)")
plt.xlabel("Year")
plt.ylabel("%")
plt.legend(["QQQ","SP500"])

img = img_to_base64()
plt.close()

html_body += f"""
<div class="card">
<h2>Annual Return Summary</h2>
<img src="data:image/png;base64,{img}">
</div>
"""

# -------------------------------------------------------------
# 3. Annual QQQ - SP500 Difference（±60%）
# -------------------------------------------------------------
year_ret["Diff"] = year_ret[QQQ] - year_ret[SPX]

plt.figure(figsize=(8,4))
plt.plot(years, year_ret["Diff"]*100, marker="o", color="red", linewidth=2)

plt.axhline(0, color="black")
plt.ylim(ANNUAL_MIN, ANNUAL_MAX)
plt.yticks(range(-60, 61, 10))
plt.grid(True)
plt.title("Annual QQQ - SP500 Difference (%)")
plt.xlabel("Year")
plt.ylabel("%")

img = img_to_base64()
plt.close()

html_body += f"""
<div class="card">
<h2>Annual QQQ - SP500 Difference</h2>
<img src="data:image/png;base64,{img}">
</div>
"""

# -------------------------------------------------------------
# 4. Year-by-Year Scatter + Monthly
# -------------------------------------------------------------
years_sorted = sorted(df["year"].unique(), reverse=True)

for y in years_sorted:
    sub = df[df["year"] == y]
    if len(sub) < 2:
        continue

    plt.figure(figsize=(11,4))

    # Scatter
    plt.subplot(1,2,1)
    xx = sub[SPX]
    yy = sub[QQQ]

    slope, intercept = np.polyfit(xx, yy, 1)
    r = np.corrcoef(xx, yy)[0,1]
    r2 = r**2

    plt.scatter(xx, yy, color="#4da6ff", alpha=0.65)
    xs = np.linspace(SCATTER_MIN, SCATTER_MAX, 100)
    plt.plot(xs, slope*xs + intercept, color="red", linewidth=2)

    plt.title(f"{y} Correlation  (Beta={slope:.2f}, R²={r2:.2f})")
    plt.xlabel("SP500 Return")
    plt.ylabel("QQQ Return")
    plt.xlim(SCATTER_MIN, SCATTER_MAX)
    plt.ylim(SCATTER_MIN, SCATTER_MAX)
    plt.gca().set_aspect('equal', adjustable='box')
    plt.grid(True)

    # Monthly
    plt.subplot(1,2,2)
    mdat = sub.groupby("month")[[QQQ, SPX]].mean().reindex(range(1,13)).fillna(0)
    d2 = mdat[QQQ] - mdat[SPX]
    m = mdat.index
    w = 0.35

    plt.bar(m - w/2, mdat[QQQ]*100, w, color="#4da6ff")
    plt.bar(m + w/2, mdat[SPX]*100, w, color="#ff9999")
    plt.plot(m, d2*100, marker="o", color="red", linewidth=2)

    cum_q = (1+mdat[QQQ]).cumprod().iloc[-1]-1
    cum_s = (1+mdat[SPX]).cumprod().iloc[-1]-1

    plt.title(f"{y} Monthly (Q={cum_q*100:.1f}%, S={cum_s*100:.1f}%)")
    plt.xlabel("Month")
    plt.ylabel("Return (%)")
    plt.ylim(BAR_MIN, BAR_MAX)
    plt.grid(True)
    plt.legend(["Diff","QQQ","SP500"])

    img = img_to_base64()
    plt.close()

    html_body += f"""
    <div class="card">
    <h2>Year {y}</h2>
    <img src="data:image/png;base64,{img}">
    </div>
    """


# -------------------------------------------------------------
# Output HTML（PCのみ）
# -------------------------------------------------------------
html_pc = base_html(CSS_PC, html_body)

with open("analysis_report.html", "w", encoding="utf-8") as f:
    f.write(html_pc)

print("Generated: analysis_report.html")
