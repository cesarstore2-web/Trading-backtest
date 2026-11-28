import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# إعدادات الصفحة والتصميم الداكن المطابق للصورة
st.set_page_config(page_title="تقاطع المتوسطات — سبوت العملات الحلال", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; direction: rtl; text-align: right; }
    .main-card {
        background-color: #2b1114;
        border: 1px solid #7f1d1d;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 15px;
    }
    .main-card.profit { background-color: #112b1a; border-color: #15803d; }
    .week-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 12px;
        text-align: center;
        margin-bottom: 10px;
    }
    .week-card.loss { border-color: #7f1d1d; background-color: #211215; }
    .week-card.profit { border-color: #15803d; background-color: #122117; }
    .big-num { font-size: 36px; font-weight: bold; color: #ff4b4b; margin: 5px 0; }
    .big-num.pos { color: #00cc66; }
    .sub-text { font-size: 13px; color: #9ca3af; }
</style>
""", unsafe_allow_html=True)

# العنوان الرئيسي
st.markdown("<h2 style='text-align: center;'>📈 تقاطع المتوسطات — سبوت العملات الحلال</h2>", unsafe_allow_html=True)

# قائمة العملات (تم تصحيح رمز TIA ليتوافق مع Yahoo Finance)
COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "TIA22861-USD"]

# قيم افتراضية في الذاكرة قبل فتح الإعدادات
if "ma1_type" not in st.session_state: st.session_state.ma1_type = "EMA"
if "ma1_len" not in st.session_state: st.session_state.ma1_len = 9
if "ma2_type" not in st.session_state: st.session_state.ma2_type = "EMA"
if "ma2_len" not in st.session_state: st.session_state.ma2_len = 21
if "timeframe" not in st.session_state: st.session_state.timeframe = "1h"
if "atr_sl" not in st.session_state: st.session_state.atr_sl = 1.5
if "rr_ratio" not in st.session_state: st.session_state.rr_ratio = 2.0

# دالة حساب المتوسطات
def calc_ma(series, ma_type, length):
    if ma_type == "SMA":
        return series.rolling(window=length).mean()
    elif ma_type == "EMA":
        return series.ewm(span=length, adjust=False).mean()
    elif ma_type == "WMA":
        weights = np.arange(1, length + 1)
        return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

# دالة الباك-تيست ومحاكاة الصفقات للشهر الحالي
@st.cache_data(ttl=300)
def run_strategy(ma1_t, ma1_l, ma2_t, ma2_l, tf, atr_mult, rr):
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    trades = []
    errors = []
    capital_per_trade = 100.0  # حجم الصفقة الافتراضي بالدولار

    for symbol in COINS:
        try:
            df = yf.download(symbol, period="60d", interval=tf, progress=False)
            if df.empty or len(df) < max(ma1_l, ma2_l) + 15:
                errors.append(symbol)
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df["MA1"] = calc_ma(df["Close"], ma1_t, ma1_l)
            df["MA2"] = calc_ma(df["Close"], ma2_t, ma2_l)
            
            # حساب ATR
            high_low = df["High"] - df["Low"]
            high_close = np.abs(df["High"] - df["Close"].shift())
            low_close = np.abs(df["Low"] - df["Close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df["ATR"] = tr.rolling(14).mean()

            in_pos = False
            entry_price = sl = tp = 0.0

            for i in range(1, len(df)):
                row = df.iloc[i]
                prev = df.iloc[i-1]
                ts = df.index[i]
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")

                if not in_pos:
                    # شرط تقاطع المتوسط السريع فوق البطيء (شراء سبوت)
                    if prev["MA1"] <= prev["MA2"] and row["MA1"] > row["MA2"] and ts >= start_of_month:
                        entry_price = float(row["Close"])
                        atr_val = float(row["ATR"])
                        if np.isnan(atr_val) or atr_val == 0: continue
                        sl = entry_price - (atr_val * atr_mult)
                        tp = entry_price + ((entry_price - sl) * rr)
                        in_pos = True
                else:
                    low_p = float(row["Low"])
                    high_p = float(row["High"])
                    if low_p <= sl:
                        pnl = -capital_per_trade * ((entry_price - sl) / entry_price)
                        trades.append({"time": ts, "pnl": pnl})
                        in_pos = False
                    elif high_p >= tp:
                        pnl = capital_per_trade * ((tp - entry_price) / entry_price)
                        trades.append({"time": ts, "pnl": pnl})
                        in_pos = False
        except Exception:
            errors.append(symbol)

    return pd.DataFrame(trades), errors

# تنفيذ الاستراتيجية بالقيم الحالية
trades_df, failed_coins = run_strategy(
    st.session_state.ma1_type, st.session_state.ma1_len,
    st.session_state.ma2_type, st.session_state.ma2_len,
    st.session_state.timeframe, st.session_state.atr_sl, st.session_state.rr_ratio
)

# حساب الإحصائيات
total_pnl = trades_df["pnl"].sum() if not trades_df.empty else 0.0
closed_count = len(trades_df)
win_rate = (len(trades_df[trades_df["pnl"] > 0]) / closed_count * 100) if closed_count > 0 else 0.0

# 1. مربع الربح الصافي للشهر الحالي
card_cls = "profit" if total_pnl > 0 else ""
num_cls = "pos" if total_pnl > 0 else ""
sign = "+" if total_pnl > 0 else ("-" if total_pnl < 0 else "")

st.markdown(f"""
<div class="main-card {card_cls}">
    <div class="sub-text">صافي ربح شهر نوفمبر 2026 (UTC)</div>
    <div class="big-num {num_cls}">{sign}${abs(total_pnl):.2f}</div>
    <div class="sub-text">{closed_count} صفقة مغلقة • نسبة النجاح {win_rate:.0f}% • عائم على المفتوحة: $0.00</div>
</div>
""", unsafe_allow_html=True)

# 2. زر الإعدادات بين مربع الشهر الحالي ومربعات الأسابيع
show_settings = st.checkbox("⚙️ إظهار الإعدادات")

if show_settings:
    with st.container(border=True):
        st.markdown("#### 🛠️ إعدادات استراتيجية تقاطع المتوسطين")
        
        # نافذة المتوسط الأول (السريع)
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.ma1_type = st.selectbox("نوع المتوسط الأول", ["EMA", "SMA", "WMA"], index=["EMA", "SMA", "WMA"].index(st.session_state.ma1_type))
        with c2:
            st.session_state.ma1_len = st.number_input("رقم المتوسط الأول", min_value=2, value=st.session_state.ma1_len, step=1)

        # نافذة المتوسط الثاني (البطيء)
        c3, c4 = st.columns(2)
        with c3:
            st.session_state.ma2_type = st.selectbox("نوع المتوسط الثاني", ["EMA", "SMA", "WMA"], index=["EMA", "SMA", "WMA"].index(st.session_state.ma2_type))
        with c4:
            st.session_state.ma2_len = st.number_input("رقم المتوسط الثاني", min_value=2, value=st.session_state.ma2_len, step=1)

        # نافذة الفريمات، ATR SL، و R:R
        c5, c6, c7 = st.columns(3)
        with c5:
            st.session_state.timeframe = st.selectbox("الفريم (Timeframe)", ["15m", "30m", "1h", "4h", "1d"], index=["15m", "30m", "1h", "4h", "1d"].index(st.session_state.timeframe))
        with c6:
            st.session_state.atr_sl = st.number_input("ATR SL (معامل الوقف)", min_value=0.1, value=st.session_state.atr_sl, step=0.1)
        with c7:
            st.session_state.rr_ratio = st.number_input("R : R (العائد للمخاطرة)", min_value=0.5, value=st.session_state.rr_ratio, step=0.1)

# 3. مربعات الربح الصافي للأسابيع
def get_week_pnl(start_day, end_day):
    if trades_df.empty: return 0.0
    mask = (trades_df["time"].dt.day >= start_day) & (trades_df["time"].dt.day <= end_day)
    return trades_df.loc[mask, "pnl"].sum()

w1 = get_week_pnl(1, 7)
w2 = get_week_pnl(8, 14)
w3 = get_week_pnl(15, 21)
w4 = get_week_pnl(22, 28)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f'<div class="week-card {"loss" if w1<0 else ("profit" if w1>0 else "")}"><div class="sub-text">الأسبوع 1 (1–7)</div><b>${w1:.2f}</b></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="week-card {"loss" if w2<0 else ("profit" if w2>0 else "")}"><div class="sub-text">الأسبوع 2 (8–14)</div><b>${w2:.2f}</b></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="week-card {"loss" if w3<0 else ("profit" if w3>0 else "")}"><div class="sub-text">الأسبوع 3 (15–21)</div><b>${w3:.2f}</b></div>', unsafe_allow_html=True)

col4, col5 = st.columns(2)
with col4:
    st.markdown(f'<div class="week-card {"loss" if w4<0 else ("profit" if w4>0 else "")}"><div class="sub-text">الأسبوع 4 (22–28)</div><b>${w4:.2f}</b></div>', unsafe_allow_html=True)
with col5:
    st.markdown('<div class="week-card"><div class="sub-text">الأسبوع 5 (29–30)</div><b>—</b></div>', unsafe_allow_html=True)

# تنبيهات البيانات
if failed_coins:
    st.warning(f"تعذّر جلب: {', '.join(failed_coins)} (تحقق من رمز Yahoo في COINS).")

st.caption(f"آخر تحديث: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC • بيانات yfinance • تتجدد كل 5 دقائق")
