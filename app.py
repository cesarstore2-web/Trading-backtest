
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
st.set_page_config(page_title="ماسح ضغط الشراء والدعوم", layout="centered")
# رأس مال كل صفقة ثابت في الخفاء (100 دولار)
TRADE_AMOUNT = 100.0
# توقيت المغرب الحالي (UTC / WET)
MOROCCO_TZ = timezone.utc
# قائمة الـ 16 عملة رقمية النقية (الـ 8 الأساسية + 8 إضافية بنفس الشروط)
HALAL_COINS = {
    # القائمة الأساسية
    "TIA-USD": "Celestia (TIA)",
    "SUI20947-USD": "Sui (SUI)",
    "RENDER-USD": "Render (RENDER)",
    "ARB11841-USD": "Arbitrum (ARB)",
    "DOT-USD": "Polkadot (DOT)",
    "TAO22974-USD": "Bittensor (TAO)",
    "HBAR-USD": "Hedera (HBAR)",
    "LINK-USD": "Chainlink (LINK)",
    # العملات المضافة
    "SOL-USD": "Solana (SOL)",
    "AVAX-USD": "Avalanche (AVAX)",
    "NEAR-USD": "NEAR Protocol (NEAR)",
    "APT21794-USD": "Aptos (APT)",
    "SEI-USD": "Sei (SEI)",
    "ATOM-USD": "Cosmos (ATOM)",
    "ALGO-USD": "Algorand (ALGO)",
    "IMX10603-USD": "Immutable (IMX)"
}
# دالة حساب بداية ونهاية الدورة الأسبوعية (الأحد 00:00 إلى الأحد القادم 23:55 بتوقيت المغرب UTC)
def get_sunday_to_sunday_window():
    now = datetime.now(MOROCCO_TZ)
    days_since_sunday = (now.weekday() + 1) % 7
    start_dt = (now - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = (start_dt + timedelta(days=7)).replace(hour=23, minute=55, second=0, microsecond=0)
    return start_dt, end_dt, now
start_window, end_window, now_ma = get_sunday_to_sunday_window()
# القيم الافتراضية المعتمدة
timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3
use_demand = False
use_support = True
# مربع إظهار أو إخفاء الإعدادات
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
st.caption(
    f"العملات: {len(HALAL_COINS)} عملة نقية | الدورة: من الأحد {start_window.strftime('%Y-%m-%d %H:%M')} إلى الأحد {end_window.strftime('%Y-%m-%d %H:%M')} (UTC)"
)
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
        
    if df.index.tz is None:
        df.index = df.index.tz_localize(MOROCCO_TZ)
    else:
        df.index = df.index.tz_convert(MOROCCO_TZ)
        
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
def run_backtest(df, start_dt, end_dt, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support):
    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001
    i = min_bars
    while i < len(df) - 1:
        candle_time = df.index[i]
        
        if candle_time < start_dt or candle_time > end_dt:
            i += 1
            continue
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
            in_zone, _ = check_zone_touch(window_df, c_row, en_demand, en_support)
            if in_zone:
                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl = entry - sl_dist
                    tp = entry + (sl_dist * rr)
                    closed = False
                    for j in range(i + 1, len(df)):
                        if df.index[j] > end_dt:
                            break
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
with st.spinner("جاري فحص العملات الـ 16 وحساب صفقات الدورة الحالية..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                w, l, o, p = run_backtest(
                    df_m, start_window, end_window, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support
                )
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح الصافي ($)": round(p, 2)})
        except Exception:
            pass
closed_t = tot_w + tot_l
win_r = (tot_w / closed_t * 100) if closed_t > 0 else 0.0
st.markdown(f"**الربح الصافي للدورة الحالية ({timeframe})**")
st.title(f"$ {tot_p:.2f}")
st.markdown("**نسبة النجاح**")
st.title(f"{win_r:.1f}%")
st.info(f"↑ مغلقة: {closed_t} | مفتوحة: {tot_o}")
st.success(f"✅ {tot_w} ناجحة")
st.error(f"❌ {tot_l} خاسرة")
if details:
    with st.expander("عرض تفاصيل الصفقات والربح الصافي لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
