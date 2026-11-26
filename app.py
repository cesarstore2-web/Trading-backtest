import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="استراتيجية تقاطع المتوسطات + ATR", layout="centered")

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

# اختيار الإطار الزمني
timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)

st.markdown("**إعدادات المتوسطات (Moving Averages)**")
ma_options = ["EMA", "SMA", "WMA", "RMA"]

# المتوسط السريع (Fast MA)
c1, c2 = st.columns(2)
with c1:
    fast_type = st.selectbox("Fast MA Type", ma_options, index=0) # EMA
with c2:
    fast_len = st.number_input("Fast MA Length", min_value=1, max_value=200, value=2, step=1)

# المتوسط المتوسط (Medium MA)
c3, c4 = st.columns(2)
with c3:
    med_type = st.selectbox("Medium MA Type", ma_options, index=2) # WMA
with c4:
    med_len = st.number_input("Medium MA Length", min_value=2, max_value=300, value=20, step=1)

# المتوسط البطيء (Slow MA)
c5, c6 = st.columns(2)
with c5:
    slow_type = st.selectbox("Slow MA Type (Trend)", ma_options, index=3) # RMA
with c6:
    slow_len = st.number_input("Slow MA Length", min_value=5, max_value=500, value=50, step=5)

st.markdown("**إدارة المخاطر (RISK MANAGEMENT - ATR / RR)**")
r1, r2, r3 = st.columns(3)
with r1:
    atr_len = st.number_input("ATR Length", min_value=2, max_value=100, value=14, step=1)
with r2:
    atr_mult = st.number_input("ATR Multiplier (SL)", min_value=0.1, max_value=10.0, value=2.5, step=0.1, format="%.1f")
with r3:
    rr_ratio = st.number_input("Risk-to-Reward (1:X)", min_value=0.1, max_value=10.0, value=1.5, step=0.1, format="%.1f")

st.markdown("**فلاتر الاتجاه العام (Multi-Timeframe Trend Filter)**")
f1, f2 = st.columns(2)
with f1:
    use_trend_1h = st.checkbox("تفعيل اتجاه 1 ساعة (1H)", value=False)
with f2:
    use_trend_1d = st.checkbox("تفعيل اتجاه 1 يوم (1D)", value=False)

if use_trend_1h or use_trend_1d:
    trend_ema_len = st.number_input("طول متوسط الاتجاه العام (EMA):", min_value=10, max_value=200, value=50, step=10)
else:
    trend_ema_len = 50

st.caption(f"الاستراتيجية: {fast_type}({fast_len}) × {med_type}({med_len}) فوق {slow_type}({slow_len}) | SL: {atr_mult}x ATR | عمولة 0.1%")
st.divider()

# دالة حساب أنواع المتوسطات الأربعة بدقة
def calc_ma(series, length, ma_type):
    if ma_type == "EMA":
        return series.ewm(span=length, adjust=False).mean()
    elif ma_type == "SMA":
        return series.rolling(window=length).mean()
    elif ma_type == "WMA":
        weights = np.arange(1, length + 1)
        return series.rolling(window=length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    elif ma_type == "RMA":
        return series.ewm(alpha=1.0 / length, adjust=False).mean()
    return series

# دالة حساب مؤشر ATR
def calc_atr(df, length):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

# جلب البيانات الحقيقية للفريم الأساسي وفريمات الاتجاه (1h و 1d)
@st.cache_data(ttl=300)
def fetch_all_timeframes(ticker, tf):
    # 1. الفريم الأساسي
    yf_interval = "1h" if tf == "4h" else tf
    df_main = yf.download(ticker, period="30d", interval=yf_interval, progress=False)
    if df_main.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if isinstance(df_main.columns, pd.MultiIndex):
        df_main.columns = df_main.columns.get_level_values(0)
    if tf == "4h":
        df_main = df_main.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()

    # 2. فريم الساعة (1h) للاتجاه العام
    df_1h = yf.download(ticker, period="30d", interval="1h", progress=False)
    if not df_1h.empty and isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = df_1h.columns.get_level_values(0)

    # 3. فريم اليوم (1d) للاتجاه العام
    df_1d = yf.download(ticker, period="1y", interval="1d", progress=False)
    if not df_1d.empty and isinstance(df_1d.columns, pd.MultiIndex):
        df_1d.columns = df_1d.columns.get_level_values(0)

    return df_main, df_1h, df_1d

# دمج حالة الاتجاه العام (1H و 1D) مع الفريم الأساسي بدقة زمنية
def attach_trend_filters(df_main, df_1h, df_1d, ema_len, check_1h, check_1d):
    df = df_main.copy()
    df['Bull_1H'] = True
    df['Bull_1D'] = True

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    if check_1h and not df_1h.empty:
        d1h = df_1h.copy()
        if d1h.index.tz is not None:
            d1h.index = d1h.index.tz_localize(None)
        d1h['EMA_1H'] = d1h['Close'].ewm(span=ema_len, adjust=False).mean()
        # نستخدم الشمعة المغلقة السابقة (shift(1)) لتجنب النظرة المستقبلية
        d1h['Bull_1H'] = (d1h['Close'] > d1h['EMA_1H']).shift(1).fillna(False)
        merged_1h = pd.merge_asof(
            df.sort_index(), d1h[['Bull_1H']].sort_index(), left_index=True, right_index=True, direction='backward'
        )
        df['Bull_1H'] = merged_1h['Bull_1H'].fillna(False)

    if check_1d and not df_1d.empty:
        d1d = df_1d.copy()
        if d1d.index.tz is not None:
            d1d.index = d1d.index.tz_localize(None)
        d1d['EMA_1D'] = d1d['Close'].ewm(span=ema_len, adjust=False).mean()
        d1d['Bull_1D'] = (d1d['Close'] > d1d['EMA_1D']).shift(1).fillna(False)
        merged_1d = pd.merge_asof(
            df.sort_index(), d1d[['Bull_1D']].sort_index(), left_index=True, right_index=True, direction='backward'
        )
        df['Bull_1D'] = merged_1d['Bull_1D'].fillna(False)

    return df

# محاكاة الاستراتيجية على آخر 7 أيام
def backtest_strategy(df, tf, f_type, f_len, m_type, m_len, s_type, s_len, a_len, a_mult, rr, amount=TRADE_AMOUNT):
    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    max_len = max(f_len, m_len, s_len, a_len)
    
    if len(df) < max_len + 10:
        return 0, 0, 0, 0.0

    df['Fast'] = calc_ma(df['Close'], f_len, f_type)
    df['Med'] = calc_ma(df['Close'], m_len, m_type)
    df['Slow'] = calc_ma(df['Close'], s_len, s_type)
    df['ATR'] = calc_atr(df, a_len)

    start_idx = max(max_len + 1, len(df) - candles_7d[tf])
    
    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    fee_rate = 0.001

    i = start_idx
    while i < len(df) - 1:
        prev_row = df.iloc[i - 1]
        curr_row = df.iloc[i]
        
        if pd.isna(prev_row['Slow']) or pd.isna(curr_row['Slow']) or pd.isna(curr_row['ATR']):
            i += 1
            continue

        # التحقق من مربعي تفعيل الاتجاه العام (1H و 1D)
        if not bool(curr_row['Bull_1H']) or not bool(curr_row['Bull_1D']):
            i += 1
            continue

        # شرط التقاطع الشرائي
        crossover = (prev_row['Fast'] <= prev_row['Med']) and (curr_row['Fast'] > curr_row['Med'])
        above_slow = (curr_row['Fast'] > curr_row['Slow']) and (curr_row['Med'] > curr_row['Slow'])
        
        if crossover and above_slow:
            entry_price = float(curr_row['Close'])
            atr_val = float(curr_row['ATR'])
            sl_distance = atr_val * a_mult
            
            if sl_distance > 0:
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + (sl_distance * rr)
                
                trade_closed = False
                for j in range(i + 1, len(df)):
                    future_candle = df.iloc[j]
                    if float(future_candle['Low']) <= stop_loss:
                        losses += 1
                        gross_loss = amount * (sl_distance / entry_price)
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

# تشغيل التحليل
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []

with st.spinner("جاري فحص تقاطعات المتوسطات ومطابقة اتجاه 1H و 1D..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df_main, df_1h, df_1d = fetch_all_timeframes(ticker, timeframe)
            if not df_main.empty:
                df_filtered = attach_trend_filters(
                    df_main, df_1h, df_1d, int(trend_ema_len), use_trend_1h, use_trend_1d
                )
                w, l, o, p = backtest_strategy(
                    df_filtered, timeframe,
                    fast_type, int(fast_len),
                    med_type, int(med_len),
                    slow_type, int(slow_len),
                    int(atr_len), float(atr_mult), float(rr_ratio)
                )
                total_wins += w
                total_losses += l
                total_open += o
                total_profit += p
                if (w + l + o) > 0:
                    details.append({
                        "العملة": name,
                        "ناجحة": w,
