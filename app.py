import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم", layout="centered")

# رأس مال كل صفقة ثابت في الخفاء (100 دولار)
TRADE_AMOUNT = 100.0

# قائمة الـ 8 عملات الرقمية الحلال المختارة بصيغة Yahoo Finance
HALAL_COINS = {
    "TAO22974-USD": "Bittensor (TAO)",
    "RENDER-USD": "Render (RENDER)",
    "LINK-USD": "Chainlink (LINK)",
    "HBAR-USD": "Hedera (HBAR)",
    "SUI20947-USD": "Sui (SUI)",
    "TIA-USD": "Celestia (TIA)",
    "ARB11841-USD": "Arbitrum (ARB)",
    "DOT-USD": "Polkadot (DOT)"
}

# القيم الافتراضية المعتمدة
timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3
use_demand = False
use_support = True

# مربع إظهار أو إخفاء الإعدادات (مخفية افتراضياً)
show_settings = st.checkbox("إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    
    st.markdown("**إعدادات ضغط الشراء والدعوم**")
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", min_value=51, max_value=95, value=80, step=1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم والطلب:", min_value=15, max_value=200, value=100, step=5)

    st.markdown("**إدارة المخاطر (ATR / RR)**")
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1, format="%.1f")

    st.markdown("**مصدر مناطق الدخول**")
    z1, z2 = st.columns(2)
    with z1:
        use_demand = st.checkbox("مناطق الطلب (Demand Zones)", value=False)
    with z2:
        use_support = st.checkbox("مستويات الدعم (Support Levels)", value=True)
    st.divider()

st.caption(f"العملات المختارة: {len(HALAL_COINS)} عملات نقية | الشراء > {min_buy_ratio}% عند الدعوم | الفريم: {timeframe} | المدة: 7 أيام")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_data(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="30d", interval=yf_int, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if tf == "4h":
        df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    return df

def check_zone_touch(window_df, curr_candle, enable_demand, enable_support):
    curr_low = float(curr_candle['Low'])
    curr_close = float(curr_candle['Close'])
    
    if enable_demand:
        for k in range(len(window_df) - 2):
            c = window_df.iloc[k]
            next_c = window_df.iloc[k + 1]
            c_body = abs(float(c['Close']) - float(c['Open']))
            next_body = float(next_c['Close']) - float(next_c['Open'])
            
            if next_body > 0 and next_body > (c_body * 1.8):
                zone_top = max(float(c['Open']), float(c['Close']))
                zone_bottom = float(c['Low'])
                if curr_low <= zone_top and curr_close >= zone_bottom:
                    return True, "منطقة طلب"

    if enable_support:
        lows = window_df['Low'].values
        support_level = np.min(lows)
        tolerance = support_level * 0.005
        if curr_low <= (support_level + tolerance) and curr_close >= support_level:
            return True, "مستوى دعم"

    return False, ""

def run_backtest(df, tf, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support):
    c_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0, []

    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()

    start_i = max(min_bars, len(df) - c_7d[tf])
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001
    zone_hits = []

    i = start_i
    while i < len(df) - 1:
        c_row = df.iloc[i]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            i += 1
            continue

        high_p = float(c_row['High'])
        low_p = float(c_row['Low'])
        close_p = float(c_row['Close'])
        open_p = float(c_row['Open'])
        vol = float(c_row['Volume'])
        candle_range = high_p - low_p

        if candle_range > 0 and vol > 0:
            buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0
        else:
            buy_pressure_ratio = 50.0

        strong_buying = (buy_pressure_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8)

        if strong_buying:
            window_df = df.iloc[i - lookback : i]
            in_zone, zone_type = check_zone_touch(window_df, c_row, en_demand, en_support)

            if in_zone:
                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl = entry - sl_dist
                    tp = entry + (sl_dist * rr)
                    zone_hits.append(zone_type)
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
    return wins, losses, open_t, profit, zone_hits

tot_w, tot_l, tot_o, tot_p, details, all_zones = 0, 0, 0, 0.0, [], []

with st.spinner("جاري حساب الربح الصافي لآخر 7 أيام..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                w, l, o, p, z_list = run_backtest(
                    df_m, timeframe, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support
                )
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                all_zones.extend(z_list)
                if (w + l + o) > 0:
                    details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح الصافي ($)": round(p, 2)})
        except Exception:
            pass

closed_t = tot_w + tot_l
win_r = (tot_w / closed_t * 100) if closed_t > 0 else 0.0

st.markdown(f"**الربح الصافي سبوت لمدة 7 أيام ({timeframe})**")
st.title(f"$ {tot_p:.2f}")
st.markdown("**نسبة النجاح**")
st.title(f"{win_r:.1f}%")
st.info(f"↑ مغلقة: {closed_t} | مفتوحة: {tot_o}")
st.success(f"✅ {tot_w} ناجحة")
st.error(f"❌ {tot_l} خاسرة")

if all_zones:
    st.subheader("توزيع الصفقات حسب المنطقة")
    z_df = pd.Series(all_zones).value_counts().reset_index()
    z_df.columns = ["نوع المنطقة", "عدد الصفقات"]
    st.dataframe(z_df, use_container_width=True, hide_index=True)

if details:
    with st.expander("عرض تفاصيل الصفقات والربح الصافي لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
