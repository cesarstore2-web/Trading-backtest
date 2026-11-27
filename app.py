#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance Spot Signal Scanner (1h, Long only) -> Telegram

الاستخدام:
    python scanner.py signals   # فحص آخر شموع الساعة المغلقة وإرسال التوصيات
    python scanner.py report    # تقرير قصير: صافي الربح لكل أسبوع في الشهر الحالي

المتغيرات البيئية (GitHub Secrets):
    TELEGRAM_BOT_TOKEN   توكن البوت من BotFather
    TELEGRAM_CHAT_ID     مثال: @my_channel أو -1001234567890
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

# ───────────────────────── الإعدادات ─────────────────────────
TRADE_AMOUNT = 100.0          # USDT لكل صفقة
FEE_RATE = 0.001              # 0.1% عند الدخول و0.1% عند الخروج
INTERVAL = "1h"
HOUR_MS = 3_600_000

BUY_PRESSURE_MIN = 80.0       # %
VOLUME_SMA_LEN = 10
VOLUME_FACTOR = 0.8
SUPPORT_LOOKBACK = 100
SUPPORT_TOLERANCE = 0.005     # 0.5%
ATR_LEN = 13
ATR_SL_MULT = 2.3
ATR_TP_MULT = 2.3 * 2.3

SIGNAL_LOOKBACK_CANDLES = 2   # عدد الشموع المغلقة الأخيرة التي يفحصها وضع signals
STATE_FILE = "state.json"

HALAL_COINS = {   # نفس عملات تطبيق Streamlit (16 زوجاً)
    "BTCUSDT": "Bitcoin",
    "ETHUSDT": "Ethereum",
    "SOLUSDT": "Solana",
    "AVAXUSDT": "Avalanche",
    "NEARUSDT": "NEAR Protocol",
    "SUIUSDT": "Sui",
    "APTUSDT": "Aptos",
    "INJUSDT": "Injective",
    "SEIUSDT": "Sei",
    "TIAUSDT": "Celestia",
    "RENDERUSDT": "Render",
    "ARBUSDT": "Arbitrum",
    "DOTUSDT": "Polkadot",
    "LINKUSDT": "Chainlink",
    "ADAUSDT": "Cardano",
    "HBARUSDT": "Hedera",
}

# data-api.binance.vision: نقطة بيانات السوق العامة (تعمل غالباً من خوادم GitHub)
BASE_URLS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
]


# ───────────────────────── Binance ─────────────────────────
def _get(path, params):
    last_err = "unknown"
    for base in BASE_URLS:
        try:
            r = requests.get(base + path, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:
                # زوج غير موجود على Binance Spot: لا فائدة من تجربة بقية العناوين
                raise RuntimeError(f"HTTP 400 (الزوج غير موجود على Spot): {r.text[:100]}")
            last_err = f"{base} -> HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            last_err = f"{base} -> {e}"
    raise RuntimeError(last_err)


def _to_df(raw):
    df = pd.DataFrame(
        raw,
        columns=["open_time", "open", "high", "low", "close", "volume",
                 "close_time", "qav", "trades", "tbb", "tbq", "ignore"],
    )
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]


def _drop_unclosed(df):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return df[df["close_time"] < now_ms].reset_index(drop=True)


def fetch_recent(symbol, bars=500):
    raw = _get("/api/v3/klines", {"symbol": symbol, "interval": INTERVAL, "limit": bars})
    return _drop_unclosed(_to_df(raw))


def fetch_since(symbol, start_ms):
    rows, cursor = [], start_ms
    while True:
        raw = _get("/api/v3/klines", {"symbol": symbol, "interval": INTERVAL,
                                      "startTime": cursor, "limit": 1000})
        if not raw:
            break
        rows += raw
        cursor = raw[-1][6] + 1
        if len(raw) < 1000:
            break
    return _drop_unclosed(_to_df(rows))


# ───────────────────────── الاستراتيجية ─────────────────────────
def add_indicators(df):
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder's smoothing: EMA بمعامل alpha = 1/13
    df["atr"] = tr.ewm(alpha=1.0 / ATR_LEN, adjust=False).mean()

    rng = df["high"] - df["low"]
    df["buy_pressure"] = ((df["close"] - df["low"]) / rng.where(rng > 0)) * 100.0
    df["vol_sma"] = df["volume"].rolling(VOLUME_SMA_LEN).mean()
    # أقل قاع خلال آخر 100 شمعة سابقة للشمعة الحالية (بدون الحالية)
    df["support"] = df["low"].shift(1).rolling(SUPPORT_LOOKBACK).min()

    tol = df["support"] * SUPPORT_TOLERANCE
    df["signal"] = (
        (df["close"] > df["open"])
        & (df["buy_pressure"] >= BUY_PRESSURE_MIN)
        & (df["volume"] >= df["vol_sma"] * VOLUME_FACTOR)
        & (df["low"] <= df["support"] + tol)
        & (df["close"] >= df["support"])
    ).fillna(False)

    df["entry"] = df["close"]
    df["sl"] = df["entry"] - df["atr"] * ATR_SL_MULT
    df["tp"] = df["entry"] + df["atr"] * ATR_TP_MULT
    return df


# ───────────────────────── Telegram ─────────────────────────
def send_telegram(text):
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID غير مضبوطين")
        sys.exit(1)
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    if r.status_code != 200:
        print(f"Telegram error {r.status_code}: {r.text}")
        sys.exit(1)


def fmt(v):
    return f"{v:.8f}".rstrip("0").rstrip(".") if v < 1 else f"{v:.4f}".rstrip("0").rstrip(".")


# ───────────────────────── وضع التوصيات ─────────────────────────
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state[-1000:], f)


def run_signals():
    state = load_state()
    sent = set(state)
    for symbol, name in HALAL_COINS.items():
        try:
            df = add_indicators(fetch_recent(symbol))
        except Exception as e:
            print(f"[{symbol}] تعذر الجلب: {e}")
            continue
        for _, row in df.tail(SIGNAL_LOOKBACK_CANDLES).iterrows():
            if not row["signal"]:
                continue
            key = f"{symbol}|{int(row['open_time'])}"
            if key in sent:
                continue
            msg = (
                f"🟢 توصية شراء | {name}\n"
                f"الزوج: {symbol}\n"
                f"سعر الدخول: {fmt(row['entry'])}\n"
                f"وقف الخسارة (SL): {fmt(row['sl'])}\n"
                f"الهدف (TP): {fmt(row['tp'])}"
            )
            send_telegram(msg)
            sent.add(key)
            state.append(key)
            print(f"أُرسلت: {key}")
    save_state(state)


# ───────────────────────── وضع التقرير ─────────────────────────
def week_start(dt):
    """بداية الأسبوع: الأحد 00:00 UTC"""
    d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def simulate(df, i):
    """يحاكي صفقة دخلت عند إغلاق الشمعة i. يعيد (الحالة، سعر الخروج، فهرس شمعة الخروج)."""
    sl, tp = df.at[i, "sl"], df.at[i, "tp"]
    for j in range(i + 1, len(df)):
        # إذا لمست الشمعة SL و TP معاً تُحسب خسارة (فحص SL أولاً)
        if df.at[j, "low"] <= sl:
            return "loss", sl, j
        if df.at[j, "high"] >= tp:
            return "win", tp, j
    return "open", float(df["close"].iloc[-1]), len(df) - 1


def net_pnl(entry, exit_price):
    qty = TRADE_AMOUNT / entry
    gross = qty * exit_price - TRADE_AMOUNT
    fees = TRADE_AMOUNT * FEE_RATE + qty * exit_price * FEE_RATE
    return gross - fees


def run_report():
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fetch_from = int((month_start - timedelta(hours=400)).timestamp() * 1000)

    trades, failed = [], []
    for symbol in HALAL_COINS:
        try:
            df = add_indicators(fetch_since(symbol, fetch_from))
        except Exception as e:
            print(f"[{symbol}] تعذر الجلب: {e}")
            failed.append(symbol)
            continue
        # مثل Streamlit: صفقة واحدة في كل زوج في وقت واحد.
        # بعد إغلاق الصفقة يُستأنف الفحص من الشمعة التالية لشمعة الإغلاق،
        # وإذا بقيت صفقة مفتوحة يتوقف الفحص على هذا الزوج.
        last = len(df) - 1
        blocked_until = -1
        for i in df.index[df["signal"]]:
            if i >= last or i <= blocked_until:
                continue
            entry_dt = datetime.fromtimestamp((df.at[i, "open_time"] + HOUR_MS) / 1000, tz=timezone.utc)
            if entry_dt < month_start:
                continue
            status, exit_price, exit_idx = simulate(df, i)
            trades.append({
                "week": week_start(entry_dt),
                "status": status,
                "pnl": net_pnl(df.at[i, "entry"], exit_price),
            })
            if status == "open":
                break
            blocked_until = exit_idx

    # الأسابيع (أحد → سبت) التي تغطي الشهر الحالي
    weeks, w = [], week_start(month_start)
    while w <= now:
        weeks.append(w)
        w += timedelta(days=7)

    lines = [f"📊 تقرير {month_start.strftime('%Y-%m')} — صافي الربح بعد الرسوم "
             f"({FEE_RATE*100:.1f}% دخول وخروج) | {TRADE_AMOUNT:.0f} USDT/صفقة", ""]
    total_pnl = total_n = total_w = total_l = total_o = 0
    for n, w in enumerate(weeks, 1):
        wt = [t for t in trades if t["week"] == w]
        wins = sum(t["status"] == "win" for t in wt)
        losses = sum(t["status"] == "loss" for t in wt)
        opens = sum(t["status"] == "open" for t in wt)
        pnl = sum(t["pnl"] for t in wt)
        end = w + timedelta(days=6)
        lines.append(f"الأسبوع {n} ({w:%d/%m} → {end:%d/%m}): {len(wt)} صفقة | "
                     f"✅ {wins} ❌ {losses} 🔓 {opens} | {pnl:+.2f} USDT")
        total_pnl += pnl; total_n += len(wt)
        total_w += wins; total_l += losses; total_o += opens

    lines += ["", f"الإجمالي: {total_n} صفقة | ✅ {total_w} ❌ {total_l} 🔓 {total_o} | {total_pnl:+.2f} USDT"]
    if failed:
        lines.append(f"⚠️ تعذر جلب: {', '.join(failed)}")
    send_telegram("\n".join(lines))
    print("أُرسل التقرير")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "signals"
    if mode == "signals":
        run_signals()
    elif mode == "report":
        run_report()
    else:
        print("الاستخدام: python scanner.py [signals|report]")
        sys.exit(1)
