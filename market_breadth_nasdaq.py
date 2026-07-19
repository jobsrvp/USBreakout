import yfinance as yf
import pandas as pd
import numpy as np
import json
import time
import os
from datetime import datetime

# ========================= CONFIG =========================
BREADTH_FILE = "breadth_history.json"
NASDAQ_CACHE_FILE = "nasdaq_tickers_cache.csv"
CHUNK_SIZE = 80                    # Adjust based on your internet / rate limits
NEAR_RANGE_PCT = 10
START_DATE = "1990-01-01"          # Long history buffer
OUTPUT_START = "2000-01-01"        # When to start saving data
# =========================================================

def load_nasdaq_tradable_stocks():
    """Load from shared cache with strict filtering (same as RS + Screener)"""
    if not os.path.exists(NASDAQ_CACHE_FILE):
        print("❌ NASDAQ cache not found. Please run generate_nasdaq_rs.py first.")
        return []
    
    print("📂 Loading NASDAQ tickers from cache...")
    df = pd.read_csv(NASDAQ_CACHE_FILE)
    
    def is_common_tradable(row):
        symbol = str(row['Symbol']).strip()
        name = str(row.get('Security Name', '')).lower()
        
        if not symbol or len(symbol) > 5:
            return False
        if any(c in symbol for c in ['.', '-', '^', '/', '\\', '+', '*']):
            return False
        if symbol.endswith(('W', 'R', 'U', 'P', 'V', 'Q', 'T')):  # Warrants, Rights, Units etc.
            return False
        
        exclude = ['warrant', 'right', 'unit', 'preferred', 'etf', 'fund', 'trust',
                   'note', 'debenture', 'bond', 'depositary', 'acquisition']
        if any(kw in name for kw in exclude):
            return False
        
        if row.get('Financial Status') != 'N' or row.get('Market Category') not in ['Q', 'G', 'S']:
            return False
        return True
    
    tradable_df = df[df.apply(is_common_tradable, axis=1)]
    symbols = tradable_df['Symbol'].astype(str).str.strip().tolist()
    print(f"✅ Loaded {len(symbols)} tradable common NASDAQ stocks")
    return symbols


def extract_symbol_df(data, symbol):
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if symbol in data.columns.get_level_values(0):
                return data[symbol].dropna()
        else:
            return data.dropna()
    except:
        return None
    return None


def run():
    symbols = load_nasdaq_tradable_stocks()
    if not symbols:
        print("❌ No symbols loaded.")
        return

    print(f"Total symbols to process: {len(symbols)}")
    all_stock_data = {}

    # ─── DOWNLOAD IN CHUNKS ───────────────────────
    for i in range(0, len(symbols), CHUNK_SIZE):
        chunk = symbols[i:i + CHUNK_SIZE]
        print(f"Downloading chunk {i//CHUNK_SIZE + 1} / {len(symbols)//CHUNK_SIZE + 1} → {len(chunk)} stocks")

        try:
            data = yf.download(
                chunk,
                start=START_DATE,
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False
            )
            
            for sym in chunk:
                df = extract_symbol_df(data, sym)
                if df is None or len(df) < 300:   # Need decent history
                    continue
                
                df = df[['High', 'Low', 'Close']].copy()
                df['SMA200'] = df['Close'].rolling(200).mean()
                df['H52'] = df['High'].rolling(252).max()
                df['L52'] = df['Low'].rolling(252).min()
                
                all_stock_data[sym] = df
                
        except Exception as e:
            print(f"  Chunk error: {e}")
        
        time.sleep(1.5)   # Polite delay

    print(f"✅ Valid stocks with sufficient history: {len(all_stock_data)}")

    # ─── BUILD DAILY BREADTH ──────────────────────
    all_dates = sorted(set(d for df in all_stock_data.values() for d in df.index))

    history = []
    print("Building daily breadth history...")

    for dt in all_dates:
        if dt < pd.to_datetime(OUTPUT_START):
            continue

        total = above = nh = nl = 0

        for sym, df in all_stock_data.items():
            if dt not in df.index:
                continue

            row = df.loc[dt]
            if pd.isna(row.get('SMA200')):
                continue

            total += 1
            close = row['Close']

            if close > row['SMA200']:
                above += 1

            if close >= row['H52'] * (1 - NEAR_RANGE_PCT / 100):
                nh += 1

            if close <= row['L52'] * (1 + NEAR_RANGE_PCT / 100):
                nl += 1

        if total == 0:
            continue

        entry = {
            "date": dt.strftime("%Y-%m-%d"),
            "breadth_pct": round(above / total * 100, 2),
            "near_high_pct": round(nh / total * 100, 2),
            "near_low_pct": round(nl / total * 100, 2),
            "total": total
        }

        history.append(entry)

        if len(history) % 250 == 0:
            print(f"Processed up to {dt.date()}")

    # ─── SAVE ─────────────────────────────────────
    with open(BREADTH_FILE, "w") as f:
        json.dump(history, f, indent=4)

    print(f"\n✅ NASDAQ Market Breadth History Completed!")
    print(f"   Total days saved : {len(history)}")
    print(f"   Output file      : {BREADTH_FILE}")


if __name__ == "__main__":
    run()