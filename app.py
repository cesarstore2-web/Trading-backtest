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
        "PAXG/USDT", # عملة الذهب الرقمي (مدعومة بأونصة الذهب الفعلي)
        "XAUT/USDT"  # تيثير الذهب (Tether Gold - يعادل سعر أونصة الذهب XAU)
    ]
}

@st.cache_data(ttl=300)
def fetch_data(symbol, timeframe='4h', limit=720):
    # أسماء المنصات المحدثة في مكتبة ccxt والمتوافقة مع خوادم Streamlit
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    
    last_error = ""
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange_class = getattr(ccxt, ex_id)
            exchange = exchange_class({'enableRateLimit': True})
            
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 100:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df, exchange.name
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(f"تعذر جلب البيانات لهذا الزوج. آخر خطأ: {last_error}")

def add_features(df):
    df = df.copy()
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_6'] = df['close'].pct_change(6)
    
    df['sma_10'] = df['close'].rolling(10).mean() / df['close']
    df['sma_30'] = df['close'].rolling(30).mean() / df['close']
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['volatility'] = (df['high'] - df['low']) / df['close']
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df

# واجهة اختيار الفئة والأصل المالي
category = st.radio("اختر السوق:", list(ASSETS.keys()), horizontal=True)
symbol = st.selectbox("اختر الزوج المراد تحليله:", ASSETS[category])

min_confidence = st.slider("الحد الأدنى لثقة النموذج لإصدار توصية (%):", 50, 75, 55)

if st.button("تحليل السوق وإصدار التوصية 🚀"):
    with st.spinner(f"جاري سحب بيانات {symbol} وتدريب نموذج AI..."):
        try:
            raw_df, source_name = fetch_data(symbol=symbol, timeframe='4h', limit=720)
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
            
            # استخراج احتمالات التوقع (الصف 0، العمود 0 للهبوط والعمود 1 للصعود)
            probs = model.predict_proba(current_candle)
            prob_down = float(probs[0][0])
            prob_up = float(probs[0][1])
            
            st.divider()
            st.subheader(f"📊 بطاقة التوصية لـ {symbol} (فريم 4H)")
            st.caption(f"السعر الحالي: {current_price} | مصدر البيانات: {source_name}")
            
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
            st.error(f"حدث خطأ: {e}")
