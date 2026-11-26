import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="استراتيجية موجات إليوت - الموجة 2", layout="centered")

# رأس مال كل صفقة ثابت في الخفاء (100 دولار)
TRADE_AMOUNT = 100.0

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

# واجهة المستخدم (نظيفة بدون حقل رأس المال)
timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)

entry_mode = st.selectbox(
    "طريقة الدخول في الموجة 2:",
    [
        "دخول مؤكد (نهاية الموجة 2 وبداية 3)",
        "دخول مبكر داخل الموجة 2 (مستوى فيبوناتشي 61.8%)"
    ],
    index=0
)

rr_ratio = st.number_input(
    "نسبة العائد للمخاطرة (R:R):",
    min_value=0.50,
    max_value=10.00,
    value=2.00,
    step=0.10,
    format="%.2f"
)

wave_sensitivity = st.number_input(
    "حساسية اكتشاف الموجة 1 (عدد الشموع):",
    min_value=2,
    max_value=10,
    value=3,
    step=1
)

use_ema = st.checkbox("فلتر الاتجاه العام (EMA 100)", value=False)

st.caption(f"الاستراتيجية: اقتناص الموجة 2 التصحيحية للانطلاق مع الموجة 3 | عمولة السبوت 0.1%")
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

# استخراج نقاط الارتكاز المؤكدة (قاع 0 -> قمة 1 -> قاع 2)
def get_confirmed_pivots(df, current_idx, order):
    pivots = []
    search_start = max(order, current_idx - 60)
    search_end = current_idx - order
    
    highs = df['High'].values
    lows = df['Low'].values
    
    for k in range(search_start, search_end):
        if highs[k] == np.max(highs[k - order : k + order + 1]):
            if not pivots or pivots[-1] == 'L':
                pivots.append((k, 'H', float(highs[k])))
            elif pivots[-1] == 'H' and float(highs[k]) > pivots[-1]:
                pivots[-1] = (k, 'H', float(highs[k]))
                
        elif lows[k] == np.min(lows[k - order : k + order + 1]):
            if not pivots or pivots[-1] == 'H':
                pivots.append((k, 'L', float(lows[k])))
            elif pivots[-1] == 'L' and float(lows[k]) < pivots[-1]:
                pivots[-1] = (k, 'L', float(lows[k]))
                
    return pivots

# فحص شروط الموجة 2 (قاع 0 -> قمة 1 -> تصحيح فيبوناتشي 2)
def check_wave2_entry(df, i, order, mode):
    pivots = get_confirmed_pivots(df, i, order)
    curr_candle = df.iloc[i]
    prev_candle = df.iloc[i - 1]
    
    curr_close = float(curr_candle['Close'])
    curr_open = float(curr_candle['Open'])
    curr_low = float(curr_candle['Low'])

    # الوضع الأول: الدخول المؤكد عند اكتمال قاع الموجة 2 وبداية الموجة 3
    if "مؤكد" in mode:
        if len(pivots) >= 3:
            p0, p1, p2 = pivots[-3], pivots[-2], pivots[-1]
            if p0 == 'L' and p1 == 'H' and p2 == 'L':
                w0_price, w1_price, w2_price = p0, p1, p2
                wave1_len = w1_price - w0_price
                
                if wave1_len > 0:
                    retrace = (w1_price - w2_price) / wave1_len
                    # تصحيح الموجة 2 بين 38.2% و 78.6% دون كسر قاع الموجة 1
                    if 0.382 <= retrace <= 0.786 and w2_price > w0_price:
                        if curr_close > curr_open and curr_close > float(prev_candle['High']) and curr_close > w2_price:
                            return curr_close, w0_price

    # الوضع الثاني: الدخول المبكر داخل الموجة 2 عند ملامسة مستوى فيبوناتشي 61.8%
    else:
        if len(pivots) >= 2:
            p0, p1 = pivots[-2], pivots[-1]
            if p0 == 'L' and p1 == 'H':
                w0_price, w1_price = p0, p1
                wave1_len = w1_price - w0_price
                
                if wave1_len > 0:
                    fib_618 = w1_price - (wave1_len * 0.618)
                    if curr_low <= fib_618 and curr_low > w0_price and float(prev_candle['Low']) > fib_618:
                        return fib_618, w0_price

    return None, 0.0

# محاكاة الصفقات على آخر 7 أيام برأس مال ثابت 100$
def backtest_wave2(df, tf, rr_ratio, order, mode, use_ema, amount=TRADE_AMOUNT):
    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    
    if use_ema:
        df['EMA'] = df['Close'].ewm(span=100, adjust=False).mean()
        start_idx = max(100, len(df) - candles_7d[tf])
    else:
        start_idx = max(25, len(df) - candles_7d[tf])
        
    if len(df) <= start_idx + 1:
        return 0, 0, 0, 0.0

    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    fee_rate = 0.001

    i = start_idx
    while i < len(df) - 1:
        curr_candle = df.iloc[i]
        
        if use_ema and float(curr_candle['Close']) < float(curr_candle['EMA']):
            i += 1
            continue
            
        entry_price, stop_loss = check_wave2_entry(df, i, order, mode)
        
        if entry_price is not None:
            risk = entry_price - stop_loss
            
            if risk > 0 and (risk / entry_price) >= 0.0025:
                take_profit = entry_price + (risk * rr_ratio)
                
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

    return wins, losses, open_trades, net_profit

# تشغيل التحليل على جميع العملات
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []

with st.spinner("جاري فحص تصحيحات الموجة 2 ونسب فيبوناتشي..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df = fetch_yf_data(ticker, timeframe)
            if not df.empty:
                w, l, o, p = backtest_wave2(
                    df, timeframe, rr_ratio, int(wave_sensitivity), entry_mode, use_ema
                )
                total_wins += w
                total_losses += l
                total_open += o
                total_profit += p
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
st.markdown(f"**الربح الصافي سبوت - الموجة 2 (7 أيام | {timeframe})**")
st.title(f"$ {total_profit:.2f}")

st.markdown("**نسبة النجاح**")
st.title(f"{win_rate:.1f}%")

st.info(f"↑ مغلقة: {closed_trades} | مفتوحة: {total_open}")
st.success(f"✅ {total_wins} ناجحة")
st.error(f"❌ {total_losses} خاسرة")

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
