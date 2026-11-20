import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score

# إعداد صفحة Streamlit
st.set_page_config(page_title="نموذج AI لتوقع شمعة 4 ساعات", layout="centered")
st.title("🤖 نموذج الذكاء الاصطناعي وتوليد التوصيات (4H)")

# القائمة الكاملة للعملات الرقمية والذهب
ASSETS = {
    "العملات الرقمية": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", 
        "XLM/USDT", "ZEC/USDT", "XRP/USDT", 
        "HBAR/USDT", "ADA/USDT", "LTC/USDT"
    ],
    "الذهب والمعادن": [
        "PAXG/USDT", # عملة الذهب الرقمي (فوري وعقود)
        "XAU/USDT:USDT" # عقد الذهب مقابل USDT في العقود الآجلة
    ]
}

@st.cache_data(ttl=300)
def fetch_data(symbol, timeframe='4h', limit=1000):
    # استخدام Bybit (يدعم الفوري والعقود الآجلة مثل XAUUSDT)
    exchange = ccxt.bybit({'enableRateLimit': True})
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception:
        # في حال عدم توفر الزوج في الفوري، المحاولة عبر سوق العقود الآجلة (Linear)
        exchange.options['defaultType'] = 'linear'
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def add_features(df):
    df = df.copy()
    # العوائد السعرية
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_6'] = df['close'].pct_change(6)
    
    # المتوسطات المتحركة
    df['sma_10'] = df['close'].rolling(10).mean() / df['close']
    df['sma_30'] = df['close'].rolling(30).mean() / df['close']
    
    # مؤشر القوة النسبية RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # التقلب السعري (ATR مبسط)
    df['volatility'] = (df['high'] - df['low']) / df['close']
    
    # الهدف: هل ستغلق شمعة الـ 4 ساعات القادمة أعلى من الحالية؟
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df

# واجهة اختيار الفئة والأصل المالي
category = st.radio("اختر السوق:", list(ASSETS.keys()), horizontal=True)
symbol = st.selectbox("اختر الزوج المراد تحليله:", ASSETS[category])

# عتبة الثقة لإصدار التوصية
min_confidence = st.slider("الحد الأدنى لثقة النموذج لإصدار توصية (%):", 50, 75, 55)

if st.button("تحليل السوق وإصدار التوصية 🚀"):
    with st.spinner(f"جاري سحب بيانات {symbol} وتدريب نموذج AI..."):
        try:
            raw_df = fetch_data(symbol=symbol, timeframe='4h', limit=1000)
            df = add_features(raw_df)
            
            features = ['return_1', 'return_3', 'return_6', 'sma_10', 'sma_30', 'rsi', 'volatility']
            current_candle = df.iloc[-1:][features]
            current_price = df.iloc[-1]['close']
            
            train_df = df.iloc[:-1].dropna()
            split = int(len(train_df) * 0.8)
            X_train, y_train = train_df[features][:split], train_df['target'][:split]
            X_test, y_test = train_df[features][split:], train_df['target'][split:]
            
            model = LGBMClassifier(n_estimators=120, learning_rate=0.03, max_depth=4, random_state=42, verbose=-1)
            model.fit(X_train, y_train)
            
            preds = model.predict(X_test)
            acc = accuracy_score(y_test, preds)
            
            # استخراج احتمالات التوقع
            prob_up = float(model.predict_proba(current_candle)[0][1])
            prob_down = 1.0 - prob_up
            
            st.divider()
            st.subheader(f"📊 بطاقة التوصية لـ {symbol} (فريم 4H)")
            st.caption(f"السعر الحالي: {current_price}")
            
            # تحديد التوصية بناءً على عتبة الثقة
            if prob_up * 100 >= min_confidence:
                st.success(f"🟢 **التوصية: شراء (LONG)** — ثقة النموذج: {prob_up*100:.1f}%")
            elif prob_down * 100 >= min_confidence:
                st.error(f"🔴 **التوصية: بيع (SHORT)** — ثقة النموذج: {prob_down*100:.1f}%")
            else:
                st.warning(f"🟡 **التوصية: انتظار / حياد** — الثقة غير كافية للدخول (صعود {prob_up*100:.1f}% / هبوط {prob_down*100:.1f}%)")
                
            col1, col2 = st.columns(2)
            with col1:
                st.metric("دقة النموذج التاريخية", f"{acc*100:.1f}%")
            with col2:
                st.metric("احتمال الصعود القادم", f"{prob_up*100:.1f}%")
                
            st.progress(prob_up, text=f"صعود {prob_up*100:.1f}%  |  هبوط {prob_down*100:.1f}%")
            
        except Exception as e:
            st.error(f"حدث خطأ أثناء جلب البيانات لهذا الزوج: {e}")
