import calendar
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="تقاطع المتوسطات — سبوت العملات الحلال", page_icon="📈", layout="centered")
CAPITAL = 100.0

# ───────────────────────── العملات الحلال بأزواج USDT (في الخلفية، بدون TIA) ─────────────────────────
COINS = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT", "ADAUSDT": "ADA/USDT", "AVAXUSDT": "AVAX/USDT", "DOTUSDT": "DOT/USDT", "LINKUSDT": "LINK/USDT", "ATOMUSDT": "ATOM/USDT", "NEARUSDT": "NEAR/USDT", "ALGOUSDT": "ALGO/USDT", "XLMUSDT": "XLM/USDT", "VETUSDT": "VET/USDT", "HBARUSDT": "HBAR/USDT", "FILUSDT": "FIL/USDT", "ICPUSDT": "ICP/USDT", "APTUSDT": "APT/USDT", "ARBUSDT": "ARB/USDT", "OPUSDT": "OP/USDT", "RENDERUSDT": "RENDER/USDT", "GRTUSDT": "GRT/USDT", "SUIUSDT": "SUI/USDT"}
YF_FALLBACK = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD", "ADAUSDT": "ADA-USD", "AVAXUSDT": "AVAX-USD", "DOTUSDT": "DOT-USD", "LINKUSDT": "LINK-USD", "ATOMUSDT": "ATOM-USD", "NEARUSDT": "NEAR-USD", "ALGOUSDT": "ALGO-USD", "XLMUSDT": "XLM-USD", "VETUSDT": "VET-USD", "HBARUSDT": "HBAR-USD", "FILUSDT": "FIL-USD", "ICPUSDT": "ICP-USD", "APTUSDT": "APT21794-USD", "ARBUSDT": "ARB11841-USD", "OPUSDT": "OP-USD", "RENDERUSDT": "RENDER-USD", "GRTUSDT": "GRT6719-USD", "SUIUSDT": "SUI20947-USD"}
ALL_SYMBOLS = tuple(COINS.keys())
AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
TF_OPTIONS = ("5m", "15m", "30m", "1h")
MA_TYPES = ("EMA", "SMA", "WMA")
DEFAULTS = dict(tf="15m", fast_name="المتوسط السريع", fast_type="EMA", fast_len=9, slow_name="المتوسط البطيء", slow_type="EMA", slow_len=21, trend_name="متوسط الاتجاه", trend_type="SMA", trend_len=200, use_trend=True, min_vol=0.15, fee=0.10, sl_atr=2.0, rr=2.0, exit_cross=True, hold=96)

SAVED = st.session_state.setdefault("_saved", {})
for _k, _v in DEFAULTS.items():
    if ("w_" + _k) not in st.session_state: st.session_state["w_" + _k] = SAVED.get(_k, _v)
cfg = {k: st.session_state["w_" + k] for k in DEFAULTS}

st.markdown("<style>html, body, .stApp, [data-testid='stAppViewContainer'] {direction: rtl; text-align: right;} .block-container {padding-top: 1.2rem; max-width: 760px;} .big-box {border-radius: 18px; padding: 18px 10px; text-align: center; margin-bottom: 10px;} .big-title {font-size: 15px; opacity: .85; margin-bottom: 4px;} .big-num {font-size: 46px; font-weight: 800; line-height: 1.1; direction: ltr;} .big-sub {font-size: 13px; opacity: .85; margin-top: 6px;} .wk-grid {display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; margin-bottom: 12px;} .wk-card {flex: 1 1 30%; min-width: 30%; border-radius: 14px; padding: 12px 6px; text-align: center;} .wk-t {font-size: 12px; opacity: .85;} .wk-n {font-size: 20px; font-weight: 700; direction: ltr; margin-top: 3px;}</style>", unsafe_allow_html=True)

GREEN, RED, GREY = "#16a34a", "#dc2626", "#6b7280"
def tone(v, active=True): return GREY if not active else (GREEN if v > 0 else RED if v < 0 else GREY)
def money(v): return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"
def fmt_price(x): return f"{x:.6g}"
def fmt_ym(ym_str):
    y_s, m_s = str(ym_str).split("-")
    return f"{AR_MONTHS.__getitem__(int(m_s) - 1)} {y_s}"

def _fetch_binance_usdt(symbol, interval):
    for host in ("https://binance.vision", "https://binance.com"):
        try:
            r = requests.get(f"{host}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": 1000}, timeout=5)
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
                df = pd.DataFrame(r.json(), columns=["ot", "Open", "High", "Low", "Close", "Vol", "ct", "qv", "nt", "tb", "tq", "ig"])
                df.index = pd.to_datetime(df["ot"], unit="ms", utc=True).dt.tz_localize(None)
                for col in ("Open", "High", "Low", "Close"): df[col] = df[col].astype(float)
                return df.loc[:, ["Open", "High", "Low", "Close"]].sort_index()
        except Exception: continue
    return None

def _clean_yf(df):
    if df is None or len(df) == 0: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(-1)
    if any(c not in df.columns for c in ("Open", "High", "Low", "Close")): return None
    df = df.loc[:, ["Open", "High", "Low", "Close"]].dropna()
    idx = pd.DatetimeIndex(df.index)
    df.index = (idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")).tz_localize(None)
    return df.loc[~df.index.duplicated(keep="last")].sort_index()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_usdt(interval):
    data, missing, failed = {}, [], []
    for sym in ALL_SYMBOLS:
        df = _fetch_binance_usdt(sym, interval)
        if df is not None and len(df) >= 150: data[sym] = df
        else: missing.append(sym)
    if missing:
        try: raw = yf.download([YF_FALLBACK[s] for s in missing], period="59d", interval=interval, group_by="ticker", auto_adjust=False, progress=False, threads=True)
        except Exception: raw = None
        for sym in missing:
            yfs = YF_FALLBACK.get(sym)
            try: df = _clean_yf(raw[yfs].copy()) if (raw is not None and isinstance(raw.columns, pd.MultiIndex) and yfs in raw.columns.get_level_values(0)) else None
            except Exception: df = None
            if df is not None and len(df) >= 150: data[sym] = df
            else: failed.append(COINS.get(sym, sym))
    return data, failed

def calc_ma(series, length, ma_type):
    s, n = pd.Series(series), int(length)
    if ma_type == "EMA": return s.ewm(span=n, adjust=False).mean().to_numpy(dtype=float)
    if ma_type == "WMA": return s.rolling(n).apply(lambda x: np.dot(x, np.arange(1, n + 1, dtype=float)) / np.arange(1, n + 1, dtype=float).sum(), raw=True).to_numpy(dtype=float)
    return s.rolling(n).mean().to_numpy(dtype=float)

def atr_arr(h, l, c, n=14):
    pc = np.roll(c, 1); pc.__setitem__(0, c.__getitem__(0))
    a = pd.Series(np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy(dtype=float, copy=True)
    a.__setitem__(slice(0, n - 1), np.nan)
    return a

def backtest_ma_cross(sym, df, p):
    h, l, c, ts, n = df["High"].to_numpy(float), df["Low"].to_numpy(float), df["Close"].to_numpy(float), df.index, len(df)
    fast, slow, trend, atr = calc_ma(c, p["fast_len"], p["fast_type"]), calc_ma(c, p["slow_len"], p["slow_type"]), calc_ma(c, p["trend_len"], p["trend_type"]), atr_arr(h, l, c, 14)
    start_bar = max(int(p["slow_len"]), int(p["trend_len"]) if p["use_trend"] else 15) + 1
    trades, open_trade, fee_rate, last_closed = [], None, p["fee"] / 100.0, n - 2
    if last_closed <= start_bar: return trades, 0.0
    for i in range(start_bar, last_closed + 1):
        hi_i, lo_i, cl_i = float(h.item(i)), float(l.item(i)), float(c.item(i))
        fa_i, fa_p = float(fast.item(i)), float(fast.item(i - 1))
        sl_i, sl_p = float(slow.item(i)), float(slow.item(i - 1))
        at_i, tr_i = float(atr.item(i)), float(trend.item(i))
        if open_trade is not None:
            sl, tp, entry, exit_price, reason = open_trade["sl"], open_trade["tp"], open_trade["entry"], None, None
            if lo_i <= sl: exit_price, reason = sl, "وقف خسارة"
            elif hi_i >= tp: exit_price, reason = tp, "هدف"
            elif p["exit_cross"] and fa_i < sl_i and fa_p >= sl_p: exit_price, reason = cl_i, f"تقاطع عكسي ({p['fast_name']})"
            elif (i - open_trade["entry_bar"]) >= int(p["hold"]): exit_price, reason = cl_i, "انتهاء المدة"
            if exit_price is not None:
                qty = CAPITAL / entry
                net = (exit_price - entry) * qty - (entry * qty + exit_price * qty) * fee_rate
                trades.append({"الزوج": COINS.get(sym, sym), "الإشارة": f"{p['fast_name']} × {p['slow_name']}", "الدخول": open_trade["entry_time"], "الخروج": ts.__getitem__(i), "الشهر": ts.__getitem__(i).strftime("%Y-%m"), "اليوم": int(ts.__getitem__(i).day), "سعر الدخول": entry, "سعر الخروج": exit_price, "النتيجة": reason, "الربح $": round(net, 2)})
                open_trade = None
            continue
        if np.isnan(at_i) or np.isnan(fa_i) or np.isnan(sl_i) or not (fa_i > sl_i and fa_p <= sl_p): continue
        if (at_i / cl_i * 100.0) < p["min_vol"] or (p["use_trend"] and (np.isnan(tr_i) or cl_i <= tr_i)): continue
        sl = cl_i - p["sl_atr"] * at_i; risk = cl_i - sl
        if risk <= 0: continue
        open_trade = {"entry_bar": i, "entry_time": ts.__getitem__(i), "entry": cl_i, "sl": sl, "tp": cl_i + risk * p["rr"]}
    floating_pnl = ((float(c.item(last_closed)) - open_trade["entry"]) * (CAPITAL / open_trade["entry"]) - (open_trade["entry"] * (CAPITAL / open_trade["entry"]) + float(c.item(last_closed)) * (CAPITAL / open_trade["entry"])) * fee_rate) if open_trade is not None else 0.0
    return trades, floating_pnl

st.markdown("<h2 style='text-align:center; margin-bottom:14px;'>📈 تقاطع المتوسطات — سبوت العملات الحلال</h2>", unsafe_allow_html=True)
with st.spinner("جاري تحديث البيانات وحساب التقاطعات..."): data, failed = fetch_all_usdt(cfg["tf"])

all_trades, total_floating, last_candle_str = [], 0.0, ""
for sym, df in data.items():
    t_list, flt = backtest_ma_cross(sym, df, cfg)
    all_trades.extend(t_list)
    total_floating += flt
    if len(df) >= 2: last_candle_str = df.index.__getitem__(-2).strftime("%d-%m-%Y %H:%M UTC")

trades_df = pd.DataFrame(all_trades)
now_utc = datetime.now(timezone.utc)
sel_ym = now_utc.strftime("%Y-%m")
today_day = int(now_utc.day)

m_df = trades_df.loc[trades_df["الشهر"] == sel_ym].copy() if not trades_df.empty else pd.DataFrame()
month_pnl = float(m_df["الربح $"].sum()) if not m_df.empty else 0.0
wins = int((m_df["الربح $"] > 0).sum()) if not m_df.empty else 0
total_t = len(m_df)
