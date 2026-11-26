import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="ماسح موجات إليوت الشرائية", layout="centered")

# رموز العملات الرقمية عالية التذبذب
VOLATILE_COINS = {
    "SOL-USD": "Solana",
    "AVAX-USD": "Avalanche",
    "NEAR-USD": "NEAR Protocol",
    "SUI20947-USD": "Sui",
    "APT21794-USD": "Aptos",
    "INJ-USD": "Injective",
    "SEI-USD": "Sei",
    "TIA-USD": "Celestia",
    "FET-USD": "Artificial Superintelligence",
    "RENDER-USD": "Render",
    "ARB11841-USD": "Arbitrum",
    "DOT-USD": "Polkadot"
}

# واجهة المستخدم
timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)

rr_ratio = st.number_input(
    "نسبة العائد للمخاطرة (R:R):",
    min_value=0.50,
    max_value=10.00,
    value=2.00,
    step=0.10,
    format="%.2f"
)

wave_sensitivity = st.number_input(
    "حساسية اكتشاف القمم والقيعان (عدد الشموع):",
    min_value=2,
    max_value=10,
    value=3,
    step=1
)

trade_amount = st.number_input(
    "حجم الصفقة الواحدة ($):",
    min_value=10.0,
    max_value=10000.0,
    value=100.0,
    step=10.0
)

col1, col2 = st.columns(2)
with col1:
    trade_w2 = st.checkbox("دخول نهاية الموجة 2 (بداية 3)", value=True)
with col2:
    trade_w4 = st.checkbox("دخول نهاية الموجة 4 (بداية 5)", value=True)

use_ema = st.checkbox("فلتر الاتجاه العام (EMA 100)", value=False)

st.caption(f"الاستراتيجية: موجات إليوت الشرائية وقوانين فيبوناتشي | عمولة السبوت 0.1%")
st.divider()

# جلب البيانات الحقيقية من yfinance
@st.cache_data(ttl=300)
def fetch_yf_data(ticker, tf):
    yf_interval = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="30d", interval=yf_interval, progress=False)
    
    if df.empty:
        return pd.DataFrame()
        
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    if tf == "4h":
        df = df.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
    return df

# استخراج نقاط الارتكاز (القمم والقيعان الموجية) دون نظرة مستقبلية (No Lookahead Bias)
def get_confirmed_pivots(df, current_idx, order):
    pivots = []
    # نتوقف عند current_idx - order لضمان أن القمة أو القاع قد تأكد فعلياً وقت التداول
    search_start = max(order, current_idx - 80)
    search_end = current_idx - order
    
    highs = df['High'].values
    lows = df['Low'].values
    
    for k in range(search_start, search_end):
        # فحص قمة محلية
        if highs[k] == np.max(highs[k - order : k + order + 1]):
            if not pivots or pivots[-1][1] == 'L':
                pivots.append((k, 'H', float(highs[k])))
            elif pivots[-1][1] == 'H' and float(highs[k]) > pivots[-1][2]:
                pivots[-1] = (k, 'H', float(highs[k]))
                
        # فحص قاع محلي
        elif lows[k] == np.min(lows[k - order : k + order + 1]):
            if not pivots or pivots[-1][1] == 'H':
                pivots.append((k, 'L', float(lows[k])))
            elif pivots[-1][1] == 'L' and float(lows[k]) < pivots[-1][2]:
                pivots[-1] = (k, 'L', float(lows[k]))
                
    return pivots

# فحص شروط موجات إليوت الشرائية
def check_elliott_wave(df, i, order, enable_w2, enable_w4):
    pivots = get_confirmed_pivots(df, i, order)
    curr_candle = df.iloc[i]
    prev_candle = df.iloc[i - 1]
    
    curr_close = float(curr_candle['Close'])
    curr_open = float(curr_candle['Open'])
    
    # شرط التأكيد: شمعة حالية خضراء تغلق فوق قمة الشمعة السابقة
    if curr_close <= curr_open or curr_close <= float(prev_candle['High']):
        return None, 0.0

    # الحالة الأولى: صيد بداية الموجة 3 (بعد اكتمال القاع 0 -> القمة 1 -> القاع 2)
    if enable_w2 and len(pivots) >= 3:
        p0, p1, p2 = pivots[-3], pivots[-2], pivots[-1]
        if p0[1] == 'L' and p1[1] == 'H' and p2[1] == 'L':
            w0_price, w1_price, w2_price = p0[2], p1[2], p2[2]
            wave1_len = w1_price - w0_price
            
            if wave1_len > 0:
                retrace = (w1_price - w2_price) / wave1_len
                # قانون إليوت: الموجة 2 تصحح بين 38.2% و 78.6% ولا تكسر قاع الموجة 1 أبداً
                if 0.382 <= retrace <= 0.786 and w2_price > w0_price and curr_close > w2_price:
                    return "موجة إليوت (بداية الموجة 3)", w0_price

    # الحالة الثانية: صيد بداية الموجة 5 (بعد اكتمال 0 -> 1 -> 2 -> 3 -> 4)
    if enable_w4 and len(pivots) >= 5:
        p0, p1, p2, p3, p4 = pivots[-5], pivots[-4], pivots[-3], pivots[-2], pivots[-1]
        if p0[1] == 'L' and p1[1] == 'H' and p2[1] == 'L' and p3[1] == 'H' and p4[1] == 'L':
            w0, w1, w2, w3, w4 = p0[2], p1[2], p2[2], p3[2], p4[2]
            wave1_len = w1 - w0
            wave3_len = w3 - w2
            
            # قوانين إليوت الصارمة للموجة 3 و 4:
            # 1. الموجة 3 تتجاوز قمة 1 وليست الأقصر
            # 2. الموجة 4 تصحح بين 23.6% و 50% من الموجة 3
            # 3. قاع الموجة 4 لا يتداخل مع قمة الموجة 1 (w4 > w1)
            if wave3_len > 0 and w3 > w1 and wave3_len >= wave1_len:
                retrace_w4 = (w3 - w4) / wave3_len
                if 0.236 <= retrace_w4 <= 0.50 and w4 > w1 and curr_close > w4:
                    return "موجة إليوت (بداية الموجة 5)", w1

    return None, 0.0

# محاكاة الصفقات على آخر 7 أيام
def backtest_elliott(df, tf, rr_ratio, order, enable_w2, enable_w4, use_ema, amount):
    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    
    if use_ema:
        df['EMA'] = df['Close'].ewm(span=100, adjust=False).mean()
        start_idx = max(100, len(df) - candles_7d[tf])
    else:
        start_idx = max(30, len(df) - candles_7d[tf])
        
    if len(df) <= start_idx + 1:
        return 0, 0, 0, 0.0, []

    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    fee_rate = 0.001
    wave_signals = []

    i = start_idx
    while i < len(df) - 1:
        curr_candle = df.iloc[i]
        
        if use_ema and float(curr_candle['Close']) < float(curr_candle['EMA']):
            i += 1
            continue
            
        wave_name, stop_loss = check_elliott_wave(df, i, order, enable_w2, enable_w4)
        
        if wave_name is not None:
            entry_price = float(curr_candle['Close'])
            risk = entry_price - stop_loss
            
            # استبعاد الصفقات ذات المخاطرة الصغيرة جداً لتغطية الرسوم
            if risk > 0 and (risk / entry_price) >= 0.0025:
                take_profit = entry_price + (risk * rr_ratio)
                wave_signals.append(wave_name)
                
                trade_closed = False
                for j in range(i + 1, len(df)):
                    future_candle = df.iloc[j]
                    if float(future_candle['Low']) <= stop_loss:
                        losses += 1
                        gross_loss = amount * (risk / entry_price)
                        net_profit -= (gross_loss + amount * (fee_rate * 2))
                        trade_closed = True
                        i = j
                        break
                    elif float(future_candle['High']) >= take_profit:
                        wins += 1
                        gross_win = amount * ((take_profit - entry_price) / entry_price)
                        net_profit += (gross_win - amount * (fee_rate * 2))
                        trade_closed = True
                        i = j
                        break
                        
                if not trade_closed:
                    open_trades += 1
                    break
        i += 1

    return wins, losses, open_trades, net_profit, wave_signals

# تشغيل التحليل على جميع العملات
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []
all_waves = []

with st.spinner("جاري ترقيم موجات إليوت وحساب نسب فيبوناتشي..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df = fetch_yf_data(ticker, timeframe)
            if not df.empty:
                w, l, o, p, waves = backtest_elliott(
                    df, timeframe, rr_ratio, int(wave_sensitivity), trade_w2, trade_w4, use_ema, trade_amount
                )
                total_wins += w
                total_losses += l
                total_open += o
                total_profit += p
                all_waves.extend(waves)
                if (w + l + o) > 0:
                    details.append({
                        "العملة": name,
                        "ناجحة": w,
                        "خاسرة": l,
                        "مفتوحة": o,
                        "الربح ($)": round(p, 2)
                    })
        except Exception:
            pass

closed_trades = total_wins + total_losses
win_rate = (total_wins / closed_trades * 100) if closed_trades > 0 else 0.0

# عرض النتائج
st.markdown(f"**الربح الصافي سبوت - موجات إليوت (7 أيام | {timeframe})**")
st.title(f"$ {total_profit:.2f}")

st.markdown("**نسبة النجاح**")
st.title(f"{win_rate:.1f}%")

st.info(f"↑ مغلقة: {closed_trades} | مفتوحة: {total_open}")
st.success(f"✅ {total_wins} ناجحة")
st.error(f"❌ {total_losses} خاسرة")

if all_waves:
    st.subheader("توزيع الموجات المكتشفة")
    wave_series = pd.Series(all_waves).value_counts().reset_index()
    wave_series.columns = ["نقطة الدخول الموجية", "عدد الصفقات"]
    st.dataframe(wave_series, use_container_width=True, hide_index=True)

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
