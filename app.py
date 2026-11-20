import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score

# إعداد صفحة Streamlit
st.set_page_config(page_title="ماسح AI الذكي للتوصيات (4H)", layout="wide")
st.title("🤖 ماسح الذكاء الاصطناعي الشامل للعملات والذهب (فريم 4H)")
st.caption("يتم تحليل جميع الأزواج في الخلفية وترتيب التوصيات حسب أعلى نسبة ثقة وتقييم للنموذج.")

# القائمة الكاملة للعملات الرقمية والذهب
ALL_ASSETS = [
    ("BTC/USDT", "عملة رقمية"),
    ("ETH/USDT", "عملة رقمية"),
    ("SOL/USDT", "عملة رقمية"),
    ("XLM/USDT", "عملة رقمية"),
    ("ZEC/USDT", "عملة رقمية"),
    ("XRP/USDT", "عملة رقمية"),
    ("HBAR/USDT", "عملة رقمية"),
    ("ADA/USDT", "عملة رقمية"),
    ("LTC/USDT", "عملة رقمية"),
    ("PAXG/USDT", "ذهب رقمي (PAXG)"),
    ("XAUT/USDT", "ذهب (Tether Gold)")
]

@st.cache_data(ttl=600) # حفظ البيانات في الذاكرة لمدة 10 دقائق لتسريع الفحص
def fetch_data(symbol, timeframe='4h', limit=720):
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange = getattr(ccxt, ex_id)({'enableRateLimit': True})
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 150:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df, exchange.name
        except Exception:
            continue
    return None, None

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
    
    # حساب مؤشر التقلب الحقيقي ATR (14) لتحديد الأهداف ووقف الخسارة بدقة
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    df['volatility'] = df['atr'] / df['close']
    
    # الهدف: هل ستغلق شمعة الـ 4 ساعات القادمة أعلى من الحالية؟
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df

def analyze_asset(symbol, category):
    raw_df, source = fetch_data(symbol)
    if raw_df is None:
        return None
        
    df = add_features(raw_df)
    features = ['return_1', 'return_3', 'return_6', 'sma_10', 'sma_30', 'rsi', 'volatility']
    
    current_row = df.iloc[-1]
    current_candle = df.iloc[-1:][features]
    entry_price = float(current_row['close'])
    atr_value = float(current_row['atr'])
    
    # ضبط عدد الخانات العشرية تلقائياً حسب سعر العملة
    decimals = 2 if entry_price >= 10 else (4 if entry_price >= 0.1 else 5)
    
    train_df = df.iloc[:-1].dropna()
    split = int(len(train_df) * 0.8)
    X_train, y_train = train_df[features][:split], train_df['target'][:split]
    X_test, y_test = train_df[features][split:], train_df['target'][split:]
    
    model = LGBMClassifier(n_estimators=120, learning_rate=0.03, max_depth=4, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    hist_acc = accuracy_score(y_test, preds) * 100
    
    probs = model.predict_proba(current_candle)[0]
    prob_down = float(probs[0]) * 100
    prob_up = float(probs[1]) * 100
    
    # تحديد الاتجاه، الثقة، الهدف، ووقف الخسارة بناءً على ATR
    if prob_up >= prob_down:
        direction = "شراء (LONG) 🟢"
        confidence = prob_up
        # وقف الخسارة = 1.0 ATR | الهدف = 1.5 ATR
        stop_loss = round(entry_price - (1.0 * atr_value), decimals)
        take_profit = round(entry_price + (1.5 * atr_value), decimals)
    else:
        direction = "بيع (SHORT) 🔴"
        confidence = prob_down
        stop_loss = round(entry_price + (1.0 * atr_value), decimals)
        take_profit = round(entry_price - (1.5 * atr_value), decimals)
        
    # حساب تقييم شامل يجمع بين ثقة التوقع الحالي ودقة النموذج التاريخية
    overall_score = round((confidence * 0.7) + (hist_acc * 0.3), 1)
    
    return {
        "الزوج": symbol,
        "النوع": category,
        "التوصية": direction,
        "نسبة الثقة (%)": round(confidence, 1),
        "دقة النموذج (%)": round(hist_acc, 1),
        "التقييم العام": overall_score,
        "سعر الدخول": round(entry_price, decimals),
        "الهدف (TP)": take_profit,
        "وقف الخسارة (SL)": stop_loss,
        "المصدر": source
    }

# إعدادات الفلترة في الواجهة
col_filter1, col_filter2 = st.columns(2)
with col_filter1:
    min_conf = st.slider("الحد الأدنى لنسبة الثقة لعرض التوصية (%):", 50, 75, 54)
with col_filter2:
    top_n = st.selectbox("عدد التوصيات الأعلى تقييماً للعرض:", [3, 5, 11], index=1)

if st.button("🚀 ابدأ الفحص الشامل في الخلفية واستخرج أفضل التوصيات", use_container_width=True):
    results = []
    progress_bar = st.progress(0, text="جاري الاتصال بالأسواق وتحليل العملات والذهب...")
    
    for idx, (sym, cat) in enumerate(ALL_ASSETS):
        progress_bar.progress((idx + 1) / len(ALL_ASSETS), text=f"جاري تحليل {sym}...")
        res = analyze_asset(sym, cat)
        if res is not None:
            results.append(res)
            
    progress_bar.empty()
    
    if not results:
        st.error("تعذر جلب البيانات في الوقت الحالي. يرجى المحاولة بعد قليل.")
    else:
        results_df = pd.DataFrame(results)
        # ترتيب النتائج تنازلياً حسب التقييم العام ونسبة الثقة
        results_df = results_df.sort_values(by=["التقييم العام", "نسبة الثقة (%)"], ascending=False)
        
        # تصفية التوصيات حسب الحد الأدنى للثقة
        filtered_df = results_df[results_df["نسبة الثقة (%)"] >= min_conf].head(top_n)
        
        st.subheader(f"🏆 أفضل {len(filtered_df)} توصيات لشمعة الـ 4 ساعات القادمة")
        
        if filtered_df.empty:
            st.warning(f"لا توجد عملات تتجاوز نسبة ثقة {min_conf}% حالياً. جرب خفض نسبة الثقة من الشريط أعلاه.")
        else:
            # عرض بطاقات لأفضل التوصيات
            for _, row in filtered_df.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 1.2, 1.2, 1.2])
                    c1.markdown(f"### {row['الزوج']}\n`{row['النوع']}`")
                    c2.markdown(f"**{row['التوصية']}**\nثقة: **{row['نسبة الثقة (%)']}%** | تقييم: **{row['التقييم العام']}**")
                    c3.metric("سعر الدخول", f"{row['سعر الدخول']}")
                    c4.metric("🎯 الهدف (TP)", f"{row['الهدف (TP)']}")
                    c5.metric("🛑 وقف الخسارة (SL)", f"{row['وقف الخسارة (SL)']}")
                    
        st.divider()
        st.subheader("📋 جدول الفحص الكامل لجميع العملات والذهب")
        st.dataframe(results_df, use_container_width=True, hide_index=True)
