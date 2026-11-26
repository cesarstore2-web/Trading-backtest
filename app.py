import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="استراتيجية تقاطع المتوسطات + ATR", layout="centered")
TRADE_AMOUNT = 100.0

VOLATILE_COINS = {
    "SOL-USD": "Solana",
    "AVAX-USD": "Avalanche",
    "NEAR-USD": "NEAR Protocol",
    "SUI20947-USD": "Sui",
    "APT21794-USD": "Aptos",
    "INJ-USD": "Injective",
    "SEI-USD": "Sei",
    "TIA-USD": "Celestia",
    "FET-USD": "ASI",
    "RENDER-USD": "Render",
    "ARB11841-USD": "Arbitrum",
    "DOT-USD": "Polkadot"
}

timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)

st.markdown("**إعدادات المتوسطات (Moving Averages)**")
ma_options = ["EMA", "SMA", "WMA", "RMA"]

c1, c2 = st.columns(2)
with c1:
    fast_type = st.selectbox("Fast MA Type", ma_options, index=0)
with c2:
    fast_len = st.number_input("Fast MA Length", 1, 200, 2, 1)

c3, c4 = st.columns(2)
with c3:
    med_type = st.selectbox("Medium MA Type", ma_options, index=2)
with c4:
    med_len = st.number_input("Medium MA Length", 2, 300, 20, 1)

c5, c6 = st.columns(2)
with c5:
    slow_type = st.selectbox("Slow MA Type (Trend)", ma_options, index=3)
with c6:
    slow_len = st.number_input("Slow MA Length", 5, 500, 50, 5)

st.markdown("**إدارة المخاطر (ATR / RR)**")
r1, r2, r3 = st.columns(3)
with r1:
    atr_len = st.number_input("ATR Length", 2, 100, 14, 1)
with r2:
    atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.5, 0.1, format="%.1f")
with r3:
    rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 1.5, 0.1, format="%.1f")

st.markdown("**فلاتر الاتجاه العام (1H / 1D)**")
f1, f2 = st.columns(2)
with f1:
    use_trend_1h = st.checkbox("تفعيل اتجاه 1 ساعة (1H)", value=False)
with f2:
    use_trend_1d = st.checkbox("تفعيل اتجاه 1 يوم (1D)", value=False)

trend_ema_len = st.number_input("طول متوسط الاتجاه العام (EMA):", 10, 200, 50, 10) if (use_trend_1h or use_trend_1d) else 50

st.caption(f"{fast_type}({fast_len}) × {med_type}({med_len}) فوق {slow_type}({slow_len}) | SL: {atr_mult}x ATR | عمولة 0.1%")
st.divider()

def calc_ma(series, length, ma_type):
    if ma_type == "EMA":
        return series.ewm(span=length, adjust=False).mean()
    elif ma_type == "SMA":
        return series.rolling(window=length).mean()
    elif ma_type == "WMA":
        w = np.arange(1, length + 1)
        return series.rolling(window=length).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
    elif ma_type == "RMA":
        return series.ewm(alpha=1.0 / length, adjust=False).mean()
    return series

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_all(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df_m = yf.download(ticker, period="30d", interval=yf_int, progress=False)
    if df_m.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if isinstance(df_m.columns, pd.MultiIndex):
        df_m.columns = df_m.columns.get_level_values(0)
    if tf == "4h":
        df_m = df_m.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

    df_1h = yf.download(ticker, period="30d", interval="1h", progress=False)
    if not df_1h.empty and isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = df_1h.columns.get_level_values(0)

    df_1d = yf.download(ticker, period="1y", interval="1d", progress=False)
    if not df_1d.empty and isinstance(df_1d.columns, pd.MultiIndex):
        df_1d.columns = df_1d.columns.get_level_values(0)

    return df_m, df_1h, df_1d

def apply_trends(df_m, df_1h, df_1d, ema_len, c_1h, c_1d):
    df = df_m.copy()
    df['Bull_1H'] = True
    df['Bull_1D'] = True
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    if c_1h and not df_1h.empty:
        d1 = df_1h.copy()
        if d1.index.tz is not None:
            d1.index = d1.index.tz_localize(None)
        d1['Bull_1H'] = (d1['Close'] > d1['Close'].ewm(span=ema_len, adjust=False).mean()).shift(1).fillna(False)
        df['Bull_1H'] = pd.merge_asof(df.sort_index(), d1[['Bull_1H']].sort_index(), left_index=True, right_index=True, direction='backward')['Bull_1H'].fillna(False)

    if c_1d and not df_1d.empty:
        d2 = df_1d.copy()
        if d2.index.tz is not None:
            d2.index = d2.index.tz_localize(None)
        d2['Bull_1D'] = (d2['Close'] > d2['Close'].ewm(span=ema_len, adjust=False).mean()).shift(1).fillna(False)
        df['Bull_1D'] = pd.merge_asof(df.sort_index(), d2[['Bull_1D']].sort_index(), left_index=True, right_index=True, direction='backward')['Bull_1D'].fillna(False)

    return df

def run_backtest(df, tf, f_t, f_l, m_t, m_l, s_t, s_l, a_l, a_m, rr):
    c_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    m_len = max(f_l, m_l, s_l, a_l)
    if len(df) < m_len + 10:
        return 0, 0, 0, 0.0

    df['Fast'] = calc_ma(df['Close'], f_l, f_t)
    df['Med'] = calc_ma(df['Close'], m_l, m_t)
    df['Slow'] = calc_ma(df['Close'], s_l, s_t)
    df['ATR'] = calc_atr(df, a_l)

    start_i = max(m_len + 1, len(df) - c_7d[tf])
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001

    i = start_i
    while i < len(df) - 1:
        p_row = df.iloc[i - 1]
        c_row = df.iloc[i]
        if pd.isna(p_row['Slow']) or pd.isna(c_row['Slow']) or pd.isna(c_row['ATR']):
            i += 1
            continue
        if not bool(c_row['Bull_1H']) or not bool(c_row['Bull_1D']):
            i += 1
            continue

        cross = (p_row['Fast'] <= p_row['Med']) and (c_row['Fast'] > c_row['Med'])
        above = (c_row['Fast'] > c_row['Slow']) and (c_row['Med'] > c_row['Slow'])

        if cross and above:
            entry = float(c_row['Close'])
            sl_dist = float(c_row['ATR']) * a_m
            if sl_dist > 0:
                sl = entry - sl_dist
                tp = entry + (sl_dist * rr)
                closed = False
                for j in range(i + 1, len(df)):
                    fut = df.iloc[j]
                    if float(fut['Low']) <= sl:
                        losses += 1
                        profit -= (TRADE_AMOUNT * (sl_dist / entry) + TRADE_AMOUNT * fee * 2)
                        closed = True
                        i = j
                        break
                    elif float(fut['High']) >= tp:
                        wins += 1
                        profit += (TRADE_AMOUNT * ((tp - entry) / entry) - TRADE_AMOUNT * fee * 2)
                        closed = True
                        i = j
                        break
                if not closed:
                    open_t += 1
                    break
        i += 1
    return wins, losses, open_t, profit

tot_w, tot_l, tot_o, tot_p, details = 0, 0, 0, 0.0, []

with st.spinner("جاري فحص تقاطعات المتوسطات ومطابقة اتجاه 1H و 1D..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            dm, d1h, d1d = fetch_all(ticker, timeframe)
            if not dm.empty:
                df_f = apply_trends(dm, d1h, d1d, int(trend_ema_len), use_trend_1h, use_trend_1d)
                w, l, o, p = run_backtest(df_f, timeframe, fast_type, int(fast_len), med_type, int(med_len), slow_type, int(slow_len), int(atr_len), float(atr_mult), float(rr_ratio))
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح ($)": round(p, 2)})
        except Exception:
            pass

closed_t = tot_w + tot_l
win_r = (tot_w / closed_t * 100) if closed_t > 0 else 0.0

st.markdown(f"**الربح الصافي سبوت (7 أيام | {timeframe})**")
st.title(f"$ {tot_p:.2f}")
st.markdown("**نسبة النجاح**")
st.title(f"{win_r:.1f}%")
st.info(f"↑ مغلقة: {closed_t} | مفتوحة: {tot_o}")
st.success(f"✅ {tot_w} ناجحة")
st.error(f"❌ {tot_l} خاسرة")

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
