import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import webbrowser
import yfinance as yf
import time

start_total = time.time()

# ========================= CONFIG =========================
FILE = "breadth_history.json"
NASDAQ_CACHE_FILE = "nasdaq_tickers_cache.csv"

# Download major index (NASDAQ Composite or Nasdaq-100)
INDEX_TICKER = "^IXIC"   # NASDAQ Composite
# INDEX_TICKER = "^NDX"  # Nasdaq-100 (uncomment if you prefer)
# =========================================================

# =========================
# LOAD BREADTH DATA
# =========================
with open(FILE, "r") as f:
    data = json.load(f)

df = pd.DataFrame(data)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

# Downsample for performance (optional)
df = df.iloc[::3].reset_index(drop=True)   # Change to ::5 or remove if you want full data

print(f"✅ Breadth rows loaded: {len(df)}")

# =========================
# DOWNLOAD NASDAQ INDEX
# =========================
print(f"Downloading {INDEX_TICKER}...")
index_data = yf.download(INDEX_TICKER, period="max", progress=False)

if index_data.empty:
    print("Trying fallback ^NDX")
    index_data = yf.download("^NDX", period="max", progress=False)

# Flatten columns if MultiIndex
if isinstance(index_data.columns, pd.MultiIndex):
    index_data.columns = index_data.columns.get_level_values(0)

index_data.reset_index(inplace=True)
index_data.rename(columns={"Date": "date"}, inplace=True)

print(f"✅ Index price rows: {len(index_data)}")

# =========================
# REGIME FUNCTION (Same as your original)
# =========================
def market_regime_filter(hist, i):
    if i < 20:
        return "INIT"

    curr = hist.iloc[i]
    w1 = hist.iloc[i - 5]
    w4 = hist.iloc[i - 20]

    b, h, l = curr["breadth_pct"], curr["near_high_pct"], curr["near_low_pct"]
    b1, h1, l1 = w1["breadth_pct"], w1["near_high_pct"], w1["near_low_pct"]
    b4 = w4["breadth_pct"]

    db, dh, dl = b - b1, h - h1, l - l1

    if b < 20 and l > 40: return "CAPITULATION"
    if b < 25 and l > 35 and dl > 0: return "MELTDOWN"
    if b < 40 and db < 0 and l > 25 and dl > 0: return "EARLY_RISK"
    if b > 70 and b < b4 and h < h1 and l > l1: return "BEAR_DISTR"
    if b > 70 and b < b4: return "BULL_DISTR"
    if 45 < b < 75 and db > 5 and dh > 3 and dl < 0: return "HEALTHY_BULL"
    if 25 < b < 50 and db > 0: return "RECOVERY"
    if b >= 40 and db > 0 and dl <= 0: return "WEAK_BULL"
    if b < 60 and db < 0 and dl >= 0: return "WEAK_BEAR"
    return "TRANSITION"

df["regime"] = [market_regime_filter(df, i) for i in range(len(df))]

# =========================
# CURRENT VALUES
# =========================
curr = df.iloc[-1]

# =========================
# CREATE FIGURE (3 PANELS)
# =========================
fig = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    row_heights=[0.5, 0.25, 0.25],
    vertical_spacing=0.02
)

# =========================
# PANEL 1: NASDAQ INDEX PRICE
# =========================
fig.add_trace(go.Candlestick(
    x=index_data["date"],
    open=index_data["Open"],
    high=index_data["High"],
    low=index_data["Low"],
    close=index_data["Close"],
    increasing_line_color="#26a69a",
    decreasing_line_color="#ef5350",
    showlegend=False,
    name="NASDAQ"
), row=1, col=1)

# =========================
# PANEL 2: BREADTH %
# =========================
fig.add_trace(go.Scattergl(
    x=df["date"],
    y=df["breadth_pct"],
    name="Breadth %",
    customdata=df["regime"],
    line=dict(color="#42a5f5", width=2),
    hovertemplate="<b>Breadth</b>: %{y:.1f}%<br>Regime: %{customdata}<br>%{x|%b %d, %Y}<extra></extra>"
), row=2, col=1)

# Zones
fig.add_hrect(y0=0, y1=30, fillcolor="red", opacity=0.08, row=2, col=1)
fig.add_hrect(y0=30, y1=70, fillcolor="yellow", opacity=0.05, row=2, col=1)
fig.add_hrect(y0=70, y1=100, fillcolor="green", opacity=0.08, row=2, col=1)

# =========================
# PANEL 3: NEAR HIGH / LOW
# =========================
fig.add_trace(go.Scattergl(
    x=df["date"],
    y=df["near_high_pct"],
    name="Near High %",
    customdata=df["regime"],
    line=dict(color="#66bb6a", width=2),
    hovertemplate="<b>Near High</b>: %{y:.1f}%<br>Regime: %{customdata}<br>%{x|%b %d, %Y}<extra></extra>"
), row=3, col=1)

fig.add_trace(go.Scattergl(
    x=df["date"],
    y=df["near_low_pct"],
    name="Near Low %",
    customdata=df["regime"],
    line=dict(color="#ef5350", width=2),
    hovertemplate="<b>Near Low</b>: %{y:.1f}%<br>Regime: %{customdata}<br>%{x|%b %d, %Y}<extra></extra>"
), row=3, col=1)

# Zones
fig.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.08, row=3, col=1)
fig.add_hrect(y0=20, y1=50, fillcolor="yellow", opacity=0.05, row=3, col=1)
fig.add_hrect(y0=50, y1=100, fillcolor="red", opacity=0.08, row=3, col=1)

# =========================
# REGIME SHADING
# =========================
colors = {
    "CAPITULATION": "rgba(255,0,0,0.2)",
    "MELTDOWN": "rgba(200,0,0,0.2)",
    "EARLY_RISK": "rgba(255,140,0,0.2)",
    "BEAR_DISTR": "rgba(255,80,80,0.2)",
    "BULL_DISTR": "rgba(255,215,0,0.2)",
    "HEALTHY_BULL": "rgba(0,200,0,0.2)",
    "RECOVERY": "rgba(0,255,100,0.2)",
    "WEAK_BULL": "rgba(100,255,100,0.15)",
    "WEAK_BEAR": "rgba(255,120,120,0.15)",
    "TRANSITION": "rgba(200,200,200,0.1)",
    "INIT": "rgba(150,150,150,0.1)"
}

shapes = []
i = 0
while i < len(df):
    r = df.iloc[i]["regime"]
    j = i
    while j < len(df) and df.iloc[j]["regime"] == r:
        j += 1

    shapes.append(dict(
        type="rect",
        xref="x",
        yref="paper",
        x0=df.iloc[i]["date"],
        x1=df.iloc[j-1]["date"],
        y0=0,
        y1=0.33,
        fillcolor=colors[r],
        line_width=0,
        layer="below"
    ))
    i = j

fig.update_layout(shapes=shapes)

# =========================
# LAYOUT
# =========================
fig.update_layout(
    template="plotly_dark",
    height=1000,
    hovermode="x unified",
    font=dict(family="Segoe UI", size=12),
    margin=dict(l=50, r=120, t=80, b=40),
    title=f"""
    NASDAQ Market Regime Dashboard<br>
    <span style='color:#00ffcc'>
    Regime: {curr['regime']} |
    Breadth: {curr['breadth_pct']:.1f}% |
    Near High: {curr['near_high_pct']:.1f}% |
    Near Low: {curr['near_low_pct']:.1f}%
    </span>
    """
)

fig.update_xaxes(showspikes=True, spikemode="across", rangeslider_visible=False)

# =========================
# LEGEND / GUIDE
# =========================
fig.add_annotation(
    text="""
<b>Regime Guide</b><br>
🔴 Capitulation → Panic bottom<br>
🟠 Early Risk → Weakening<br>
🟡 Distribution → Exit phase<br>
🟢 Healthy Bull → Strong trend<br>
🟢 Recovery → Early uptrend<br>
⚪ Transition → No edge
""",
    x=1.02,
    y=0.5,
    xref="paper",
    yref="paper",
    showarrow=False,
    align="left",
    font=dict(size=11)
)

# =========================
# SAVE & OPEN
# =========================
file_path = os.path.abspath("nasdaq_market_dashboard.html")
fig.write_html(file_path, include_plotlyjs="cdn")

print(f"✅ Dashboard saved: {file_path}")
print(f"⏱ Total time: {time.time() - start_total:.1f}s")

try:
    os.startfile(file_path)
except:
    webbrowser.open("file://" + file_path)