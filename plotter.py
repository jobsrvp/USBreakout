import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import json
import os
import requests

# ─── CONFIG ─────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


# -------------------------
# Load data
# -------------------------
file_path = 'breadth_history.json'
if not os.path.exists(file_path):
    print(f"{file_path} not found.")
    exit(1)

with open(file_path, 'r') as f:
    data = json.load(f)

df = pd.DataFrame(data)

required_cols = ['date', 'near_high_pct', 'near_low_pct', 'breadth_pct']
missing = [col for col in required_cols if col not in df.columns]
if missing:
    print(f"Missing columns: {missing}")
    exit(1)

# -------------------------
# Prepare dataframe
# -------------------------
df['date'] = pd.to_datetime(df['date'])
df.sort_values('date', inplace=True)
df.set_index('date', inplace=True)
df = df[~df.index.duplicated(keep='last')]

# -------------------------
# Compute stats (FULL HISTORY)
# -------------------------
nh_mean = df['near_high_pct'].mean()
nh_p20 = df['near_high_pct'].quantile(0.2)
nh_p80 = df['near_high_pct'].quantile(0.8)

nl_mean = df['near_low_pct'].mean()
nl_p20 = df['near_low_pct'].quantile(0.2)
nl_p80 = df['near_low_pct'].quantile(0.8)

# -------------------------
# Regime Score
# -------------------------
df['regime_score'] = (
    0.5 * df['breadth_pct'] +
    0.25 * df['near_high_pct'] +
    0.25 * (100 - df['near_low_pct'])
)

# -------------------------
# Momentum (10-day)
# -------------------------
df['regime_momentum'] = df['regime_score'] - df['regime_score'].shift(10)

# -------------------------
# Market classification
# -------------------------
def classify_market(row):
    score = row['regime_score']
    mom = row['regime_momentum']

    if pd.isna(mom):
        return "Neutral"

    if score > 70 and mom > 0:
        return "Strong Bull"
    elif score > 70 and mom < 0:
        return "Weakening Bull"
    elif score < 30 and mom < 0:
        return "Strong Bear"
    elif score < 30 and mom > 0:
        return "Bottoming"
    elif 30 <= score <= 70 and mom > 0:
        return "Improving"
    elif 30 <= score <= 70 and mom < 0:
        return "Deteriorating"
    else:
        return "Neutral"

df['market_state'] = df.apply(classify_market, axis=1)

# -------------------------
# Signals
# -------------------------
df['signal'] = "HOLD"

df.loc[
    (df['regime_score'] > 60) &
    (df['regime_momentum'] > 0),
    'signal'
] = "BUY"

df.loc[
    (df['regime_score'] < 40) &
    (df['regime_momentum'] < 0),
    'signal'
] = "SELL"

# -------------------------
# Slice last 5 years
# -------------------------
cutoff_date = df.index.max() - pd.Timedelta(days=365 * 8)
df_plot = df[df.index >= cutoff_date]

# -------------------------
# Dynamic width
# -------------------------
num_days = len(df_plot)
width = max(18, num_days * 0.04)
width = min(width, 30)

# -------------------------
# Plot setup (LIGHT THEME)
# -------------------------
fig, (ax1, ax2, ax3, ax4) = plt.subplots(
    4, 1,
    figsize=(width, 14),
    dpi=200,
    facecolor='white',
    gridspec_kw={'height_ratios': [1, 1.2, 0.8, 0.6]}
)

for ax in [ax1, ax2, ax3, ax4]:
    ax.set_facecolor('white')

# -------------------------
# Panel 1: Extremes
# -------------------------
ax1.plot(df_plot.index, df_plot['near_high_pct'], color='green', linewidth=0.5, label='% Near High')
ax1.plot(df_plot.index, df_plot['near_low_pct'], color='red', linewidth=0.5, label='% Near Low')

ax1.axhline(nh_mean, color='green', alpha=0.6)
ax1.axhline(nh_p80, color='green', linestyle='--', alpha=0.5)
ax1.axhline(nh_p20, color='green', linestyle=':', alpha=0.4)

ax1.axhline(nl_mean, color='red', alpha=0.6)
ax1.axhline(nl_p80, color='red', linestyle='--', alpha=0.5)
ax1.axhline(nl_p20, color='red', linestyle=':', alpha=0.4)

ax1.set_title('Market Extremes (5Y)')
ax1.legend()
ax1.grid(True, alpha=0.2)

# -------------------------
# Panel 2: Breadth
# -------------------------
ax2.plot(df_plot.index, df_plot['breadth_pct'], color='blue', linewidth=1.2)

ax2.fill_between(df_plot.index, 0, 100,
                 where=(df_plot['breadth_pct'] > 60),
                 color='green', alpha=0.08)

ax2.fill_between(df_plot.index, 0, 100,
                 where=(df_plot['breadth_pct'] < 40),
                 color='red', alpha=0.08)

ax2.axhline(80, linestyle='--', color='red', alpha=0.3)
ax2.axhline(20, linestyle='--', color='green', alpha=0.3)

ax2.set_ylim(0, 100)
ax2.set_title('Market Breadth')
ax2.grid(True, alpha=0.2)

# -------------------------
# Panel 3: Regime Score
# -------------------------
ax3.plot(df_plot.index, df_plot['regime_score'], color='black', linewidth=1.5)

ax3.fill_between(df_plot.index, 70, 100, color='green', alpha=0.1)
ax3.fill_between(df_plot.index, 0, 30, color='red', alpha=0.1)

ax3.axhline(70, linestyle='--', color='green', alpha=0.4)
ax3.axhline(30, linestyle='--', color='red', alpha=0.4)

# Buy / Sell signals
buy = df_plot[df_plot['signal'] == "BUY"]
sell = df_plot[df_plot['signal'] == "SELL"]

ax3.scatter(buy.index, buy['regime_score'], marker='^', color='green', s=40, label='Buy')
ax3.scatter(sell.index, sell['regime_score'], marker='v', color='red', s=40, label='Sell')

ax3.set_ylim(0, 100)
ax3.set_title('Market Regime Score')
ax3.legend()
ax3.grid(True, alpha=0.2)

# -------------------------
# Panel 4: Momentum
# -------------------------
ax4.plot(df_plot.index, df_plot['regime_momentum'], color='black', linewidth=1)

ax4.axhline(0, color='grey', linestyle='--')

ax4.fill_between(df_plot.index, 0, df_plot['regime_momentum'],
                 where=(df_plot['regime_momentum'] > 0),
                 color='green', alpha=0.1)

ax4.fill_between(df_plot.index, 0, df_plot['regime_momentum'],
                 where=(df_plot['regime_momentum'] < 0),
                 color='red', alpha=0.1)

ax4.set_title('Regime Momentum')
ax4.grid(True, alpha=0.2)

# -------------------------
# X-axis formatting
# -------------------------
for ax in [ax1, ax2, ax3, ax4]:
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.xaxis.set_minor_locator(mdates.MonthLocator(interval=3))

    ax.grid(which='minor', axis='x', alpha=0.05)
    ax.grid(which='major', axis='x', alpha=0.15)

# -------------------------
# Save
# -------------------------
plt.subplots_adjust(hspace=0.3)
plt.savefig('market_dashboard.png', dpi=200, bbox_inches='tight', facecolor='white')
plt.close()

# -------------------------
# Console summary (for Telegram use)
# -------------------------
latest = df.iloc[-1]

print("\n📊 Market Summary")
print(f"Regime Score: {latest['regime_score']:.1f}")
print(f"Momentum: {latest['regime_momentum']:.1f}")
print(f"State: {latest['market_state']}")
print(f"Signal: {latest['signal']}")

print("Light theme chart saved")

caption = "\n📊 NASDAQ - Market Summary" + f"\nRegime Score: {latest['regime_score']:.1f}" +f"\nMomentum: {latest['regime_momentum']:.1f}" +f"\nState: {latest['market_state']}" + f"\nSignal: {latest['signal']}"

with open("market_dashboard.png", "rb") as img:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
        files={"photo": img}
    )