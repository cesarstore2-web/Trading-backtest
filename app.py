import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="ماسح النماذج الفنية الشرائية", layout="centered")

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

lookback_window = st.number_input(
    "طول نافذة اكتشاف النموذج (عدد الشموع):",
    min_value=10,
    max_value=60,
    value=20,
    step=2
)

trade_amount = st.number_input(
    "حجم الصفقة الواحدة ($):",
    min_value=10.0,
    max_value=10000.0,
    value=100.0,
    step=10.0
)

use_ema = st.checkbox("فلتر الاتجاه العام (EMA 100)", value=False)

st.caption(f"الاستراتيجية: نماذج الشراء الفنية فقط (قاع مزدوج، رأس وكتفين مقلوب، وتد هابط، مستطيل/علم صاعد) | عمولة 0.1%")
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

# دالة اكتشاف نماذج الشراء عند لحظة الاختراق (Breakout)
def detect_bullish_pattern(window_df, current_candle):
    highs = window_df['High'].values
    lows = window_df['Low'].values
    closes = window_df['Close'].values
    
    curr_close = float(current_candle['Close'])
    curr_open = float(current_candle['Open'])
    
    # يجب أن تكون شمعة الاختراق خضراء (صاعدة)
    if curr_close <= curr_open:
        return None, 0.0

    # تقسيم نافذة النموذج إلى 3 أجزاء لتحليل القيعان والقمم
    n = len(window_df)
    part = n // 3
    if part < 3:
        return None, 0.0
        
    low1, low2, low3 = np.min(lows[:part]), np.min(lows[part:2*part]), np.min(lows[2*part:])
    high1, high2, high3 = np.max(highs[:part]), np.max(highs[part:2*part]), np.max(highs[2*part:])
    neckline = max(high2, high3)
    pattern_low = min(low1, low2, low3)

    # 1. نموذج رأس وكتفين مقلوب (Inverted Head & Shoulders)
    # القاع الأوسط أعمق من الكتفين، والكتف الأيمن أعلى أو مساوٍ للأيسر، مع اختراق خط العنق
    if low2 < low1 and low2 < low3 and abs(low1 - low3) / low1 < 0.025:
        if curr_close > neckline and closes[-1] <= neckline:
            return "رأس وكتفين مقلوب", low3

    # 2. نموذج قاع مزدوج (Double Bottom)
    # قاعان متقاربان في المستوى مع قمة بينهما واختراق خط العنق
    mid_low1 = np.min(lows[:n//2])
    mid_low2 = np.min(lows[n//2:])
    mid_neckline = np.max(highs[n//4 : 3*n//4])
    if abs(mid_low1 - mid_low2) / mid_low1 < 0.015 and mid_neckline > mid_low1 * 1.01:
        if curr_close > mid_neckline and closes[-1] <= mid_neckline:
            return "قاع مزدوج", min(mid_low1, mid_low2)

    # 3. نموذج وتد هابط (Falling Wedge)
    # قمم متناقصة وقيعان متناقصة (تضييق) ثم اختراق المقاومة الأخيرة للأعلى
    if high1 > high2 > high3 and low1 > low2 > low3:
        if curr_close > high3 and closes[-1] <= high3:
            return "وتد هابط", low3

    # 4. نموذج مستطيل صاعد أو علم/راية صاعدة (Bullish Rectangle / Flag)
    # ثبات السعر في نطاق عرضي ضيق ثم اختراق سقف النطاق للأعلى
    box_high = np.max(highs[-part*2:])
    box_low = np.min(lows[-part*2:])
    if (box_high - box_low) / box_low < 0.035: # تذبذب محصور أقل من 3.5%
        if curr_close > box_high and closes[-1] <= box_high:
            return "مستطيل / علم صاعد", box_low

    return None, 0.0

# محاكاة الصفقات على آخر 7 أيام
def backtest_patterns(df, tf, rr_ratio, window_size, use_ema, amount):
    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    
    if use_ema:
        df['EMA'] = df['Close'].ewm(span=100, adjust=False).mean()
        start_idx = max(100, window_size, len(df) - candles_7d[tf])
    else:
        start_idx = max(window_size, len(df) - candles_7d[tf])
        
    if len(df) <= start_idx + 1:
        return 0, 0, 0, 0.0, []

    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    fee_rate = 0.001
    pattern_counts = []

    i = start_idx
    while i < len(df) - 1:
        window_df = df.iloc[i - window_size : i]
        curr_candle = df.iloc[i]
        
        if use_ema and float(curr_candle['Close']) < float(curr_candle['EMA']):
            i += 1
            continue
            
        pattern_name, stop_loss = detect_bullish_pattern(window_df, curr_candle)
        
        if pattern_name is not None:
            entry_price = float(curr_candle['Close'])
            risk = entry_price - stop_loss
            
            # التأكد أن وقف الخسارة منطقي (أكبر من 0.2% لتجنب التذبذب العشوائي)
            if risk > 0 and (risk / entry_price) >= 0.002:
                take_profit = entry_price + (risk * rr_ratio)
                pattern_counts.append(pattern_name)
                
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

    return wins, losses, open_trades, net_profit, pattern_counts

# تشغيل الفحص على العملات
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []
all_patterns = []

with st.spinner("جاري مسح الشارت بحثاً عن نماذج الشراء الفنية..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df = fetch_yf_data(ticker, timeframe)
            if not df.empty:
                w, l, o, p, pats = backtest_patterns(df, timeframe, rr_ratio, int(lookback_window), use_ema, trade_amount)
                total_wins += w
                total_losses += l
                total_open += o
                total_profit += p
                all_patterns.extend(pats)
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
st.markdown(f"**الربح الصافي سبوت - نماذج الشراء (7 أيام | {timeframe})**")
st.title(f"$ {total_profit:.2f}")

st.markdown("**نسبة النجاح**")
st.title(f"{win_rate:.1f}%")

st.info(f"↑ مغلقة: {closed_trades} | مفتوحة: {total_open}")
st.success(f"✅ {total_wins} ناجحة")
st.error(f"❌ {total_losses} خاسرة")

# إحصائية النماذج المكتشفة
if all_patterns:
    st.subheader("توزيع النماذج الشرائية المكتشفة")
    pat_series = pd.Series(all_patterns).value_counts().reset_index()
    pat_series.columns = ["النموذج الفني", "عدد الفرص"]
    st.dataframe(pat_series, use_container_width=True, hide_index=True)

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
