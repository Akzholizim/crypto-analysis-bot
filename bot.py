import ccxt
import pandas as pd
import numpy as np
import asyncio
import time
from telegram import Bot
import os
BOT_TOKEN = os.getenv"8444967788:AAHIGblabg88BXf1UTA1jGsbyVDboQ20wJc"
CHANNEL_ID = os.getenv"@Akzholcryptosignal"

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TF_LTF = "15m"
TF_HTF = "1h"

CHECK_INTERVAL = 300      # 5 минут
COOLDOWN = 3600           # анти-спам 1 час

exchange = ccxt.binance()
bot = Bot(token=BOT_TOKEN)
last_signal_time = {}

# ================= INDICATORS =================
def vwap(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum()

def bos(df, lookback=20):
    hh = df["high"].rolling(lookback).max()
    ll = df["low"].rolling(lookback).min()
    return df["close"] > hh.shift(1), df["close"] < ll.shift(1)

def atr(df, period=14):
    tr = np.maximum(df["high"] - df["low"],
         np.maximum(abs(df["high"] - df["close"].shift()),
                    abs(df["low"] - df["close"].shift())))
    return tr.rolling(period).mean()

# ================= ORDER BLOCK =================
def detect_order_block(df, direction):
    prev = df.iloc[-2]
    last = df.iloc[-1]

    if direction == "long":
        if prev["close"] < prev["open"] and last["close"] > last["open"]:
            return prev["low"], prev["high"]
    if direction == "short":
        if prev["close"] > prev["open"] and last["close"] < last["open"]:
            return prev["low"], prev["high"]

    return None

# ================= SIGNAL LOGIC =================
def check_signal(symbol):
    now = time.time()
    if symbol in last_signal_time and now - last_signal_time[symbol] < COOLDOWN:
        return None

    # --- HTF ---
    htf = exchange.fetch_ohlcv(symbol, timeframe=TF_HTF, limit=100)
    htf = pd.DataFrame(htf, columns=["t","open","high","low","close","vol"])
    bos_up, bos_down = bos(htf)

    if not bos_up.iloc[-2] and not bos_down.iloc[-2]:
        return None

    trend = "long" if bos_up.iloc[-2] else "short"

    # --- LTF ---
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TF_LTF, limit=100)
    df = pd.DataFrame(ohlcv, columns=["t","open","high","low","close","volume"])

    df["vwap"] = vwap(df)
    df["atr"] = atr(df)

    last = df.iloc[-1]

    if trend == "long" and last["close"] < last["vwap"]:
        return None
    if trend == "short" and last["close"] > last["vwap"]:
        return None

    ob = detect_order_block(df, trend)
    if not ob:
        return None

    ob_low, ob_high = ob

    if trend == "long" and not (ob_low <= last["low"] <= ob_high):
        return None
    if trend == "short" and not (ob_low <= last["high"] <= ob_high):
        return None

    entry = last["close"]
    atr_val = last["atr"]

    if trend == "long":
        sl = entry - atr_val * 1.2
        tp1 = entry + (entry - sl)
        tp2 = entry + (entry - sl) * 2
        emoji = "🟢 LONG"
    else:
        sl = entry + atr_val * 1.2
        tp1 = entry - (sl - entry)
        tp2 = entry - (sl - entry) * 2
        emoji = "🔴 SHORT"

    last_signal_time[symbol] = now

    return f"""{emoji} {symbol.replace("/","")} (M15)

📍 Entry: {entry:.2f}
🛑 SL: {sl:.2f}
🎯 TP1: {tp1:.2f}
🎯 TP2: {tp2:.2f}

📦 Order Block: Confirmed
📊 VWAP: {"Above" if trend=="long" else "Below"}
🧠 Trend: H1 BOS {"Up" if trend=="long" else "Down"}
"""

# ================= MAIN LOOP =================
async def main():
    while True:
        for symbol in SYMBOLS:
            try:
                signal = check_signal(symbol)
                if signal:
                    await bot.send_message(chat_id=CHANNEL_ID, text=signal)
            except Exception as e:
                print(e)
        await asyncio.sleep(CHECK_INTERVAL)

asyncio.run(main())
