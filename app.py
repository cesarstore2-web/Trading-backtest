# app.py — تقاطع المتوسطات المتحركة (سبوت شراء فقط)
# بيانات yfinance / توقيت UTC / 100$ لكل صفقة (ثابت في الخلفية)
import calendar
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="تقاطع المتوسطات — سبوت حلال", page_icon="📈", layout="centered")

CAPITAL = 100.0  # رأس مال كل صفقة ثابت في الخلفية

# ───────────────────────── العملات (رموز Yahoo Finance) ─────────────────────────
COINS = {
    "BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL", "ADA-USD": "ADA",
    "AVAX-USD": "AVAX", "DOT-USD": "DOT", "LINK-USD": "LINK", "ATOM-USD": "ATOM",
    "NEAR-USD": "NEAR", "ALGO-USD": "ALGO", "XLM-USD": "XLM", "VET-USD": "VET",
    "HBAR-USD": "HBAR", "FIL-USD": "FIL", "ICP-USD": "ICP", "APT21794-USD": "APT",
    "ARB11841-USD": "ARB", "OP-USD": "OP", "RENDER-USD": "RENDER", "GRT6719-USD": "GRT",
    "TIA22861-USD": "TIA", "SUI20947-USD": "SUI",
}
ALL_SYMBOLS = tuple(COINS.keys())
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
TF_OPTIONS = ["5m", "15m", "30m", "1h"]
MA_TYPES = ["EMA", "SMA", "WMA"]

DEFAULTS = dict(
    tf="15m",
    coins=list(ALL_SYMBOLS),
    # ── إعدادات المتوسط السريع ──
    fast_name="المتوسط السريع",
    fast_type="EMA",
    fast_len=9,
    # ── إعدادات المتوسط البطيء ──
    slow_name="المتوسط البطيء",
    slow_type="EMA",
    slow_len=21,
    # ── إعدادات متوسط الاتجاه العام ──
    trend_name="متوسط الاتجاه",
    trend_type="SMA",
    trend_len=200,
    use_trend=True,
    # ── إدارة الصفقة والمخاطر ──
    min_vol=0.15,        # أدنى تذبذب ATR %
    fee=0.10,            # % لكل جهة
    sl_atr=2.0,          # وقف الخسارة (ATR ×)
    rr=2.0,              # نسبة الهدف إلى الوقف (Risk:Reward)
    exit_cross=True,     # الخروج عند التقاطع العكسي قبل الهدف/الوقف
    hold=96,             # أقصى مدة للصفقة (شموع)
)

# ───────────────────────── حفظ الإعدادات حتى عند إخفائها ─────────────────────────
SAVED = st.session_state.setdefault("_saved", {})
for _k, _v in DEFAULTS.items():
    if ("w_" + _k) not in st.session_state:
        st.session_state["w_" + _k] = SAVED.get(_k, _v)
cfg = {k: st.session_state["w_" + k] for k in DEFAULTS}

# ───────────────────────── تنسيق (RTL + جوال) ─────────────────────────
st.markdown("""
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {direction: rtl; text-align: right;}
.block-container {padding-top: 1.2rem; max-width: 760px;}
.big-box {border-radius: 18px; padding: 18px 10px; text-align: center; margin-bottom: 10px;}
.big-title {font-size: 15px; opacity: .85; margin-bottom: 4px;}
.big-num {font-size: 46px; font-weight: 800; line-height: 1.1; direction: ltr;}
.big-sub {font-size: 13px; opacity: .85; margin-top: 6px;}
.wk-grid {display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; margin-bottom: 12px;}
.wk-card {flex: 1 1 22%; min-width: 22%; border-radius: 14px; padding: 10px 6px; text-align: center;}
.wk-t {font-size: 12px; opacity: .85;}
.wk-n {font-size: 19px; font-weight: 700; direction: ltr; margin-top: 2px;}
</style>
""", unsafe_allow_html=True)

GREEN, RED, GREY = "#16a34a", "#dc2626", "#6b7280"


def tone(v, active=True):
    if not active:
        return GREY
    return GREEN if v > 0 else RED if v < 0 else GREY


def money(v):
    return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"


def fmt_price(x):
    return f"{x:.6g}"


# ───────────────────────── جلب البيانات (yfinance، UTC) ─────────────────────────
def _clean(df):
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    need = ["Open", "High", "Low", "Close"]
    if any(c not in df.columns for c in need):
        return None
    df = df[need].dropna()
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all(symbols, interval):
    data, failed = {}, []
    try:
        raw = yf.download(
            list(symbols),
            period="59d",
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception:
        raw = None
    for s in symbols:
        df = None
        try:
            if (
                raw is not None
                and isinstance(raw.columns, pd.MultiIndex)
                and s in raw.columns.get_level_values(0)
            ):
                df = _clean(raw[s].copy())
        except Exception:
            df = None
        if df is None or len(df) < 150:
            try:
                df = _clean(
                    yf.Ticker(s).history(
                        period="59d", interval=interval, auto_adjust=False
                    )
                )
            except Exception:
                df = None
        if df is None or len(df) < 150:
            failed.append(s)
        else:
            data[s] = df
    return data, failed


# ───────────────────────── المؤشرات ومحرك التقاطع ─────────────────────────
def calc_ma(series, length, ma_type):
    s = pd.Series(series)
    n = int(length)
    if ma_type == "EMA":
        return s.ewm(span=n, adjust=False).mean().to_numpy(dtype=float)
    if ma_type == "WMA":
        weights = np.arange(1, n + 1, dtype=float)
        return (
            s.rolling(n)
            .apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
            .to_numpy(dtype=float)
        )
    return s.rolling(n).mean().to_numpy(dtype=float)


def atr_arr(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    a = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy(dtype=float, copy=True)
    a[: n - 1] = np.nan
    return a


def backtest_ma_cross(sym, df, p):
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    ts = df.index
    n = len(c)

    fast = calc_ma(c, p["fast_len"], p["fast_type"])
    slow = calc_ma(c, p["slow_len"], p["slow_type"])
    trend = calc_ma(c, p["trend_len"], p["trend_type"])
    atr = atr_arr(h, l, c, 14)

    start_bar = max(int(p["slow_len"]), int(p["trend_len"]) if p["use_trend"] else 15) + 1
    trades = []
    open_trade = None
    fee_rate = p["fee"] / 100.0

    last_closed = n - 2
    if last_closed <= start_bar:
        return trades, None

    for i in range(start_bar, last_closed + 1):
        # ── إدارة الصفقة المفتوحة ──
        if open_trade is not None:
            sl = open_trade["sl"]
            tp = open_trade["tp"]
            entry = open_trade["entry"]
            exit_price = None
            reason = None

            if l[i] <= sl:
                exit_price = sl
                reason = "وقف خسارة"
            elif h[i] >= tp:
                exit_price = tp
                reason = "هدف"
            elif p["exit_cross"] and fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:
                exit_price = float(c[i])
                reason = f"تقاطع عكسي ({p['fast_name']})"
            elif (i - open_trade["entry_bar"]) >= int(p["hold"]):
                exit_price = float(c[i])
                reason = "انتهاء المدة"

            if exit_price is not None:
                qty = CAPITAL / entry
                gross = (exit_price - entry) * qty
                fees = (entry * qty + exit_price * qty) * fee_rate
                net = gross - fees
                trades.append(
                    {
                        "العملة": COINS.get(sym, sym),
                        "الإشارة": f"{p['fast_name']} × {p['slow_name']}",
                        "الدخول": open_trade["entry_time"],
                        "الخروج": ts[i],
                        "سعر الدخول": entry,
                        "سعر الخروج": exit_price,
                        "النتيجة": reason,
                        "الربح $": round(net, 2),
                    }
                )
                open_trade = None
            continue

        # ── فحص إشارة الدخول: تقاطع صاعد عند إغلاق شمعة الاختراق i ──
        if np.isnan(atr[i]) or np.isnan(fast[i]) or np.isnan(slow[i]):
            continue

        bull_cross = (fast[i] > slow[i]) and (fast[i - 1] <= slow[i - 1])
        if not bull_cross:
            continue

        entry = float(c[i])
        a = float(atr[i])

        if (a / entry * 100.0) < p["min_vol"]:
            continue
        if p["use_trend"] and (np.isnan(trend[i]) or entry <= trend[i]):
            continue

        sl = entry - p["sl_atr"] * a
        risk = entry - sl
        if risk <= 0:
            continue
        tp = entry + risk * p["rr"]

        open_trade = {
            "entry_bar": i,
            "entry_time": ts[i],
            "entry": entry,
            "sl": sl,
            "tp": tp,
        }

    # ── حساب الربح/الخسارة العائمة للصفقة المفتوحة ──
    floating_pnl = 0.0
    if open_trade is not None:
        curr_price = float(c[last_closed])
        entry = open_trade["entry"]
        qty = CAPITAL / entry
        floating_pnl = (curr_price - entry) * qty - (
            entry * qty + curr_price * qty
        ) * fee_rate

    return trades, floating_pnl


# ───────────────────────── تنفيذ الحسابات ─────────────────────────
st.markdown(
    "<h2 style='text-align:center; margin-bottom:14px;'>📈 تقاطع المتوسطات — سبوت العملات الحلال</h2>",
    unsafe_allow_html=True,
)

if not cfg["coins"]:
    st.warning("اختر عملة واحدة على الأقل من الإعدادات.")
    st.stop()

with st.spinner("جاري تحديث البيانات وحساب التقاطعات..."):
    data, failed = fetch_all(tuple(cfg["coins"]), cfg["tf"])

all_trades = []
total_floating = 0.0
last_candle_str = ""

for sym, df in data.items():
