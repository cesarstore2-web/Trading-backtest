import streamlit as st
import yfinance as yf
import pandas as pd

# إعدادات الصفحة
st.set_page_config(page_title="استراتيجية تقاطع 3 متوسطات", layout="centered")

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

# واجهة المستخدم
col_tf, col_type = st.columns(2)
with col_tf:
    timeframe = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
with col_type:
    ma_type = st.selectbox("نوع المتوسطات:", ["EMA", "SMA"], index=0)

# نوافذ تعديل المتوسطات الثلاثة
c1, c2, c3 = st.columns(3)
with c1:
    fast_len = st.number_input("السريع (1):", min_value=2, max_value=100, value=9, step=1)
with c2:
    med_len = st.number_input("المتوسط (2):", min_value=5, max_value=200, value=21, step=1)
with c3:
    slow_len = st.number_input("البطيء (3):", min_value=10, max_value=500, value=55, step=5)

rr_ratio = st.number_input(
    "نسبة العائد للمخاطرة (R:R):",
    min_value=0.50,
    max_value=10.00,
    value=2.00,
    step=0.10,
    format="%.2f"
)

st.caption(f"الاستراتيجية: تقاطع {ma_type} ({fast_len} / {med_len} / {slow_len}) | عمولة السبوت 0.1%")
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

# حساب المتوسطات ومحاكاة الصفقات على آخر 7 أيام
def backtest_triple_ma(df, tf, ma_type, fast, med, slow, rr_ratio, amount=TRADE_AMOUNT):
    # التأكد من ترتيب المتوسطات منطقياً
    if not (fast < med < slow):
        return 0, 0, 0, 0.0

    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    
    if len(df) < slow + 10:
        return 0, 0, 0, 0.0

    # حساب المتوسطات حسب النوع المختار (EMA أو SMA)
    if ma_type == "EMA":
        df['Fast'] = df['Close'].ewm(span=fast, adjust=False).mean()
        df['Med'] = df['Close'].ewm(span=med, adjust=False).mean()
        df['Slow'] = df['Close'].ewm(span=slow, adjust=False).mean()
    else:
        df['Fast'] = df['Close'].rolling(window=fast).mean()
        df['Med'] = df['Close'].rolling(window=med).mean()
        df['Slow'] = df['Close'].rolling(window=slow).mean()

    start_idx = max(slow + 1, len(df) - candles_7d[tf])
    
    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    fee_rate = 0.001

    i = start_idx
    while i < len(df) - 1:
        prev_row = df.iloc[i - 1]
        curr_row = df.iloc[i]
        
        # التحقق من عدم وجود قيم فارغة
        if pd.isna(prev_row['Slow']) or pd.isna(curr_row['Slow']):
            i += 1
            continue

        # شرط الدخول الشرائي:
        # 1. المتوسط السريع والمتوسط فوق البطيء (اتجاه صاعد عام)
        # 2. تقاطع المتوسط السريع صعوداً فوق المتوسط المتوسط في الشمعة الحالية
        bullish_alignment = (curr_row['Fast'] > curr_row['Med']) and (curr_row['Med'] > curr_row['Slow'])
        crossover_happened = (prev_row['Fast'] <= prev_row['Med']) or (prev_row['Med'] <= prev_row['Slow'])
        
        if bullish_alignment and crossover_happened and float(curr_row['Close']) > float(curr_row['Open']):
            entry_price = float(curr_row['Close'])
            # وقف الخسارة أسفل المتوسط البطيء أو قاع الشمعة السابقة
            stop_loss = min(float(curr_row['Slow']), float(prev_row['Low']))
            risk = entry_price - stop_loss
            
            # استبعاد الصفقات ذات المخاطرة الضيقة جداً لتغطية الرسوم
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

# تنبيه في حال أدخل المستخدم أرقاماً غير مرتبة
if not (fast_len < med_len < slow_len):
    st.warning("⚠️ يرجى التأكد أن: المتوسط السريع < المتوسط المتوسط < المتوسط البطيء")

# تشغيل التحليل على جميع العملات
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []

with st.spinner("جاري فحص تقاطعات المتوسطات الثلاثة..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df = fetch_yf_data(ticker, timeframe)
            if not df.empty:
                w, l, o, p = backtest_triple_ma(
                    df, timeframe, ma_type, int(fast_len), int(med_len), int(slow_len), rr_ratio
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
st.markdown(f"**الربح الصافي سبوت - {ma_type} {int(fast_len)}/{int(med_len)}/{int(slow_len)} (7 أيام | {timeframe})**")
st.title(f"$ {total_profit:.2f}")

st.markdown("**نسبة النجاح**")
st.title(f"{win_rate:.1f}%")

st.info(f"↑ مغلقة: {closed_trades} | مفتوحة: {total_open}")
st.success(f"✅ {total_wins} ناجحة")
st.error(f"❌ {total_losses} خاسرة")

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
