import calendar
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="تقاطع المتوسطات — سبوت USDT", page_icon="📈", layout="centered")
CAPITAL = 100.0

COINS = {
    "BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT", "ADAUSDT": "ADA/USDT",
    "AVAXUSDT": "AVAX/USDT", "DOTUSDT": "DOT/USDT", "LINKUSDT": "LINK/USDT", "ATOMUSDT": "ATOM/USDT",
    "NEARUSDT": "NEAR/USDT", "ALGOUSDT": "ALGO/USDT", "XLMUSDT": "XLM/USDT", "VETUSDT": "VET/USDT",
    "HBARUSDT": "HBAR/USDT", "FILUSDT": "FIL/USDT", "ICPUSDT": "ICP/USDT", "APTUSDT": "APT/USDT",
    "ARBUSDT": "ARB/USDT", "OPUSDT": "OP/USDT", "RENDERUSDT": "RENDER/USDT", "GRTUSDT": "GRT/USDT",
    "TIAUSDT": "TIA/USDT", "SUIUSDT": "SUI/USDT",
}
YF_FALLBACK = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD", "ADAUSDT": "ADA-USD",
    "AVAXUSDT": "AVAX-USD", "DOTUSDT": "DOT-USD", "LINKUSDT": "LINK-USD", "ATOMUSDT": "ATOM-USD",
    "NEARUSDT": "NEAR-USD", "ALGOUSDT": "ALGO-USD", "XLMUSDT": "XLM-USD", "VETUSDT": "VET-USD",
    "HBARUSDT": "HBAR-USD", "FILUSDT": "FIL-USD", "ICPUSDT": "ICP-USD", "APTUSDT": "APT21794-USD",
    "ARBUSDT": "ARB11841-USD", "OPUSDT": "OP-USD", "RENDERUSDT": "RENDER-USD", "GRTUSDT": "GRT6719-USD",
    "TIAUSDT": "TIA22861-USD", "SUIUSDT": "SUI20947-USD",
}
ALL_SYMBOLS = tuple(COINS.keys())
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
TF_OPTIONS = ["5m", "15m", "30m", "1h"]
MA_TYPES = ["EMA", "SMA", "WMA"]

DEFAULTS = dict(
    tf="15m",
    fast_name="المتوسط السريع", fast_type="EMA", fast_len=9,
    slow_name="المتوسط البطيء", slow_type="EMA", slow_len=21,
    trend_name="متوسط الاتجاه", trend_type="SMA", trend_len=200, use_trend=True,
    min_vol=0.15, fee=0.10, sl_atr=2.0, rr=2.0, exit_cross=True, hold=96,
)

SAVED = st.session_state.setdefault("_saved", {})
for _k, _v in DEFAULTS.items():
    if ("w_" + _k) not in st.session_state:
        st.session_state["w_" + _k] = SAVED.get(_k, _v)
cfg = {k: st.session_state["w_" + k] for k in DEFAULTS}

CSS_STYLE = (
    "<style>"
    "html, body, .stApp, [data-testid='stAppViewContainer'] {direction: rtl; text-align: right;}"
    ".block-container {padding-top: 1.2rem; max-width: 760px;}"
    ".big-box {border-radius: 18px; padding: 18px 10px; text-align: center; margin-bottom: 10px;}"
    ".big-title {font-size: 15px; opacity: .85; margin-bottom: 4px;}"
    ".big-num {font-size: 46px; font-weight: 800; line-height: 1.1; direction: ltr;}"
    ".big-sub {font-size: 13px; opacity: .85; margin-top: 6px;}"
    ".wk-grid {display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; margin-bottom: 12px;}"
    ".wk-card {flex: 1 1 22%; min-width: 22%; border-radius: 14px; padding: 10px 6px; text-align: center;}"
    ".wk-t {font-size: 12px; opacity: .85;}"
    ".wk-n {font-size: 19px; font-weight: 700; direction: ltr; margin-top: 2px;}"
    "</style>"
)
st.markdown(CSS_STYLE, unsafe_allow_html=True)

GREEN, RED, GREY = "#16a34a", "#dc2626", "#6b7280"

def tone(v, active=True):
    return GREY if not active else (GREEN if v > 0 else RED if v < 0 else GREY)

def money(v):
    return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"

def fmt_price(x):
    return f"{x:.6g}"

def fmt_ym(ym_str):
    y, m = ym_str.split("-")
    return f"{AR_MONTHS[int(m) - 1]} {y}"

def _fetch_binance_usdt(symbol, interval):
    for host in ("https://binance.vision", "https://binance.com"):
        try:
            r = requests.get(f"{host}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": 1000}, timeout=5)
            if r.status_code == 200:
                rows = r.json()
                if rows and isinstance(rows, list):
                    df = pd.DataFrame(rows, columns=["ot", "Open", "High", "Low", "Close", "Vol", "ct", "qv", "nt", "tb", "tq", "ig"])
                    df.index = pd.to_datetime(df["ot"], unit="ms", utc=True).dt.tz_localize(None)
                    for col in ["Open", "High", "Low", "Close"]:
                        df[col] = df[col].astype(float)
                    return df[["Open", "High", "Low", "Close"]].sort_index()
        except Exception:
            continue
    return None

def _clean_yf(df):
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
    return df[~df.index.duplicated(keep="last")].sort_index()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_usdt(interval):
    data, missing = {}, []
    for sym in ALL_SYMBOLS:
        df = _fetch_binance_usdt(sym, interval)
        if df is not None and len(df) >= 150:
            data[sym] = df
        else:
            missing.append(sym)
    if missing:
        yf_list = [YF_FALLBACK[s] for s in missing if s in YF_FALLBACK]
        try:
            raw = yf.download(yf_list, period="59d", interval=interval, group_by="ticker", auto_adjust=False, progress=False, threads=True)
        except Exception:
            raw = None
        for sym in missing:
            yfs = YF_FALLBACK.get(sym)
            df = None
            try:
                if raw is not None and isinstance(raw.columns, pd.MultiIndex) and yfs in raw.columns.get_level_values(0):
                    df = _clean_yf(raw[yfs].copy())
            except Exception:
                df = None
            if df is not None and len(df) >= 150:
                data[sym] = df
    return data

def calc_ma(series, length, ma_type):
    s, n = pd.Series(series), int(length)
    if ma_type == "EMA":
        return s.ewm(span=n, adjust=False).mean().to_numpy(dtype=float)
    if ma_type == "WMA":
        w = np.arange(1, n + 1, dtype=float)
        return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True).to_numpy(dtype=float)
    return s.rolling(n).mean().to_numpy(dtype=float)

def atr_arr(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc = c
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    a = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy(dtype=float, copy=True)
    a[:n - 1] = np.nan
    return a

def backtest_ma_cross(sym, df, p):
    h, l, c = df["High"].to_numpy(float), df["Low"].to_numpy(float), df["Close"].to_numpy(float)
    ts, n = df.index, len(c)
    fast = calc_ma(c, p["fast_len"], p["fast_type"])
    slow = calc_ma(c, p["slow_len"], p["slow_type"])
    trend = calc_ma(c, p["trend_len"], p["trend_type"])
    atr = atr_arr(h, l, c, 14)
    start_bar = max(int(p["slow_len"]), int(p["trend_len"]) if p["use_trend"] else 15) + 1
    trades, open_trade, fee_rate = [], None, p["fee"] / 100.0
    last_closed = n - 2
    if last_closed <= start_bar:
        return trades, 0.0
    for i in range(start_bar, last_closed + 1):
        if open_trade is not None:
            sl, tp, entry = open_trade["sl"], open_trade["tp"], open_trade["entry"]
            exit_price, reason = None, None
            if l[i] <= sl:
                exit_price, reason = sl, "وقف خسارة"
            elif h[i] >= tp:
                exit_price, reason = tp, "هدف"
            elif p["exit_cross"] and fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:
                exit_price, reason = float(c[i]), f"تقاطع عكسي ({p['fast_name']})"
            elif (i - open_trade["entry_bar"]) >= int(p["hold"]):
                exit_price, reason = float(c[i]), "انتهاء المدة"
            if exit_price is not None:
                qty = CAPITAL / entry
                net = (exit_price - entry) * qty - (entry * qty + exit_price * qty) * fee_rate
                trades.append({
                    "الزوج": COINS.get(sym, sym),
                    "الإشارة": f"{p['fast_name']} × {p['slow_name']}",
                    "الدخول": open_trade["entry_time"],
                    "الخروج": ts[i],
                    "الشهر": ts[i].strftime("%Y-%m"),
                    "اليوم": int(ts[i].day),
                    "سعر الدخول": entry,
                    "سعر الخروج": exit_price,
                    "النتيجة": reason,
                    "الربح $": round(net, 2),
                })
                open_trade = None
            continue
        if np.isnan(atr[i]) or np.isnan(fast[i]) or np.isnan(slow[i]):
            continue
        if not (fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]):
            continue
        entry, a = float(c[i]), float(atr[i])
        if (a / entry * 100.0) < p["min_vol"]:
            continue
        if p["use_trend"] and (np.isnan(trend[i]) or entry <= trend[i]):
            continue
        sl = entry - p["sl_atr"] * a
        risk = entry - sl
        if risk <= 0:
            continue
        open_trade = {"entry_bar": i, "entry_time": ts[i], "entry": entry, "sl": sl, "tp": entry + risk * p["rr"]}
    floating_pnl = 0.0
    if open_trade is not None:
        curr_price, entry = float(c[last_closed]), open_trade["entry"]
        qty = CAPITAL / entry
        floating_pnl = (curr_price - entry) * qty - (entry * qty + curr_price * qty) * fee_rate
    return trades, floating_pnl

st.markdown("<h2 style='text-align:center; margin-bottom:14px;'>📈 تقاطع المتوسطات — سبوت USDT</h2>", unsafe_allow_html=True)

with st.spinner("جاري تحديث بيانات USDT وحساب التقاطعات..."):
    data = fetch_all_usdt(cfg["tf"])

all_trades = []
total_floating = 0.0
last_candle_str = ""
for sym, df in data.items():
    t_list, flt = backtest_ma_cross(sym, df, cfg)
    all_trades.extend(t_list)
    total_floating += flt
    if len(df) >= 2:
