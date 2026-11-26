import streamlit as st
import yfinance as yf
import pandas as pd

# إعدادات الصفحة
st.set_page_config(page_title="ماسح استراتيجية جسم الشمعة", layout="centered")

# رموز العملات الرقمية عالية التذبذب بصيغة Yahoo Finance
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
timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=4)

# نافذة R:R بشريط تمرير وأزرار (+/-) مطابقة للصورة
rr_ratio = st.slider(
    "نسبة العائد للمخاطرة (R:R):",
    min_value=0.50,
    max_value=5.00,
    value=1.50,
    step=0.10,
    format="%.2f"
)

trade_amount = st.number_input("حجم الصفقة الواحدة ($):", min_value=10.0, max_value=10000.0, value=100.0, step=10.0)

# مربع تفعيل EMA الاختياري
use_ema = st.checkbox("تفعيل فلتر الاتجاه العام (EMA)", value=False)
if use_ema:
    ema_period = st.number_input("قيمة المتوسط المتحرك (EMA):", min_value=10, max_value=500, value=100, step=10)
else:
    ema_period = 100

st.caption(f"حالة الاتصال بالسوق: متصل بـ {len(VOLATILE_COINS)} عملة رقمية | التوقيت: المغرب (UTC+1)")
st.divider()

# دالة جلب البيانات الحقيقية من yfinance
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

# دالة محاكاة الاستراتيجية (بقيود مخفضة لالتقاط معظم الشموع)
def backtest_coin(df, tf, rr_ratio, use_ema, ema_period, amount):
    candles_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    
    if use_ema:
        if len(df) < ema_period + 5:
            return 0, 0, 0, 0.0
        df['EMA'] = df['Close'].ewm(span=ema_period, adjust=False).mean()
        start_idx = max(ema_period, len(df) - candles_7d[tf])
    else:
        if len(df) < 5:
            return 0, 0, 0, 0.0
        start_idx = max(1, len(df) - candles_7d[tf])
    
    wins = 0
    losses = 0
    open_trades = 0
    net_profit = 0.0
    
    for i in range(start_idx, len(df) - 1):
        prev_candle = df.iloc[i - 1]
        entry_candle = df.iloc[i]
        
        prev_open = float(prev_candle['Open'])
        prev_close = float(prev_candle['Close'])
        body_size = prev_close - prev_open
        
        # قيود مخفضة جداً: أي شمعة صاعدة جسمها أكبر من 0.05% (تجنب الدوجي الصفرية فقط)
        if body_size > 0 and (body_size / prev_open) >= 0.0005:
            if use_ema and prev_close < float(prev_candle['EMA']):
                continue
                
            entry_price = prev_open
            take_profit = prev_close
            stop_loss = entry_price - (body_size / rr_ratio)
            
            # تفعيل الصفقة إذا لامس السعر افتتاح الشمعة السابقة
            if float(entry_candle['Low']) <= entry_price:
                trade_closed = False
                for j in range(i, len(df)):
                    future_candle = df.iloc[j]
                    if float(future_candle['Low']) <= stop_loss:
                        losses += 1
                        net_profit -= amount * ((entry_price - stop_loss) / entry_price)
                        trade_closed = True
                        break
                    elif float(future_candle['High']) >= take_profit:
                        wins += 1
                        net_profit += amount * ((take_profit - entry_price) / entry_price)
                        trade_closed = True
                        break
                        
                if not trade_closed:
                    open_trades += 1
                    
    return wins, losses, open_trades, net_profit

# تشغيل التحليل على جميع العملات
total_wins = 0
total_losses = 0
total_open = 0
total_profit = 0.0
details = []

with st.spinner("جاري سحب البيانات الحقيقية وتحليل الصفقات..."):
    for ticker, name in VOLATILE_COINS.items():
        try:
            df = fetch_yf_data(ticker, timeframe)
            if not df.empty:
                w, l, o, p = backtest_coin(df, timeframe, rr_ratio, use_ema, ema_period, trade_amount)
                total_wins += w
                total_losses += l
                total_open += o
                total_profit += p
                details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح ($)": round(p, 2)})
        except Exception:
            pass

# حساب نسبة النجاح
closed_trades = total_wins + total_losses
win_rate = (total_wins / closed_trades * 100) if closed_trades > 0 else 0.0

# عرض النتائج بنفس تصميم صورتك
ema_status = f" | EMA {ema_period}" if use_ema else ""
st.markdown(f"**الربح الصافي سبوت (7 أيام | {timeframe}{ema_status})**")
st.title(f"$ {total_profit:.2f}")

st.markdown("**نسبة النجاح**")
st.title(f"{win_rate:.1f}%")

st.info(f"↑ مغلقة: {closed_trades} | مفتوحة: {total_open}")
st.success(f"✅ {total_wins} ناجحة")
st.error(f"❌ {total_losses} خاسرة")

if details:
    with st.expander("عرض تفاصيل الصفقات لكل عملة"):
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
