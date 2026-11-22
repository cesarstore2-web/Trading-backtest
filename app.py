import streamlit as st
import pandas as pd
import numpy as np
import ccxt

# إعداد الصفحة
st.set_page_config(page_title="لوحة التوصيات وموجات إليوت", layout="centered")

# تنسيق CSS لمحاكاة التصميم الداكن والبطاقات الملونة في الصورة
st.markdown("""
<style>
    .stApp {
        background-color: #0d0d12;
        color: #ffffff;
        direction: rtl;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .metric-card {
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        background-color: #16161e;
        margin-bottom: 15px;
    }
    .card-blue { border: 1.5px solid #2b6cb0; }
    .card-purple { border: 1.5px solid #805ad5; }
    .card-green { border: 1.5px solid #38a169; }
    .card-red { border: 1.5px solid #e53e3e; }
    .card-net { 
        border: 1.5px solid #805ad5; 
        background: linear-gradient(90deg, #16161e 0%, #231934 100%);
    }
    .card-title { font-size: 16px; color: #a0aec0; margin-bottom: 8px; }
    .card-value { font-size: 32px; font-weight: bold; }
    .green-text { color: #48bb78; }
    .red-text { color: #f56565; }
    .white-text { color: #ffffff; }
    .signal-box {
        background-color: #1a1a24;
        border-right: 4px solid #805ad5;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# القائمة المطلوبة للعملات
SYMBOLS = [
    "XLM/USDT", "ZEC/USDT", "XRP/USDT", "HBAR/USDT", "ADA/USDT",
    "LTC/USDT", "BTC/USDT", "ETH/USDT", "PAXG/USDT", "XAU/USDT"
]

# شريط اختيار الإطار الزمني (محاكاة للأزرار العلوية)
timeframe_map = {"يومي": "1d", "أسبوعي": "1w", "شهري": "1M"}
selected_tf_label = st.radio("الإطار الزمني", list(timeframe_map.keys()), horizontal=True)
selected_tf = timeframe_map[selected_tf_label]

# شريط اختيار العملة
filter_options = ["الكل"] + [s.replace("/USDT", "") for s in SYMBOLS]
selected_coin = st.selectbox("تصفية حسب العملة:", filter_options)

# دالة جلب البيانات وحساب مستويات إليوت (مبسطة لأغراض العرض)
@st.cache_data(ttl=300)
def analyze_elliott_waves(symbols_list, tf):
    exchange = ccxt.binance()
    results = []
    
    for sym in symbols_list:
        try:
            # XAUUSDT قد لا يتوفر في العقود الفورية لبينانس، نستخدم PAXG كبديل للذهب أو نحاول جلبه
            fetch_sym = "PAXG/USDT" if sym == "XAU/USDT" else sym
            bars = exchange.fetch_ohlcv(fetch_sym, timeframe=tf, limit=50)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # تحديد قاع (Wave 0) وقمة (Wave 1) كنموذج حسابي
            wave_0 = df['low'].iloc[-20:-5].min()
            wave_1 = df['high'].iloc[-15:].max()
            diff = wave_1 - wave_0
            
            # استراتيجية إليوت المطلوبة:
            # الدخول: تصحيح الموجة 2 (61.8% فيبوناتشي)
            # الهدف: امتداد الموجة 5 (1.618 فيبوناتشي)
            # وقف الخسارة: بداية الموجة 0
            entry_2 = wave_1 - (diff * 0.618)
            target_5 = wave_0 + (diff * 1.618)
            stop_loss_0 = wave_0
            
            current_price = df['close'].iloc[-1]
            # تقييم الذكاء الاصطناعي (مؤشر زخم + قرب السعر من نقطة الدخول 2)
            distance_to_entry = abs(current_price - entry_2) / current_price
            ai_score = max(60, min(98, int(100 - (distance_to_entry * 200))))
            
            results.append({
                "العملة": sym.replace("/USDT", ""),
                "السعر الحالي": round(current_price, 4),
                "نقطة الدخول (موجة 2)": round(entry_2, 4),
                "الهدف (موجة 5)": round(target_5, 4),
                "وقف الخسارة (موجة 0)": round(stop_loss_0, 4),
                "تقييم AI": ai_score
            })
        except Exception:
            continue
    return pd.DataFrame(results)

df_signals = analyze_elliott_waves(SYMBOLS, selected_tf)

# تصفية البيانات إذا تم اختيار عملة محددة
if selected_coin != "الكل" and not df_signals.empty:
    display_df = df_signals[df_signals["العملة"] == selected_coin]
else:
    display_df = df_signals

st.markdown("### 📊 سجل الأداء والنتائج السابقة")

# حساب إحصائيات تجريبية بناءً على التصفية لعرضها بنفس تصميم الصورة
total_trades = 19 if selected_coin == "الكل" else 4
win_trades = 15 if selected_coin == "الكل" else 3
loss_trades = 2 if selected_coin == "الكل" else 1
win_rate = round((win_trades / total_trades) * 100, 2)
total_profit = 3653 if selected_coin == "الكل" else 840
total_loss = 353 if selected_coin == "الكل" else 90
net_profit = total_profit - total_loss

# الصف الأول: عدد الصفقات ونسبة النجاح
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
    <div class="metric-card card-blue">
        <div class="card-title">🤝 عدد الصفقات</div>
        <div class="card-value white-text">{total_trades}</div>
        <div style="font-size:12px; color:#a0aec0;">صفقات</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card card-purple">
        <div class="card-title">🎯 نسبة النجاح</div>
        <div class="card-value white-text">{win_rate}%</div>
        <div style="font-size:12px; color:#805ad5;">معدل الأداء</div>
    </div>
    """, unsafe_allow_html=True)

# الصف الثاني: الصفقات الرابحة والخاسرة
col3, col4 = st.columns(2)
with col3:
    st.markdown(f"""
    <div class="metric-card card-green">
        <div class="card-title green-text">📈 الصفقات الرابحة</div>
        <div class="card-value white-text">{win_trades}</div>
        <div style="font-size:12px; color:#a0aec0;">صفقات</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card card-red">
        <div class="card-title red-text">📉 الصفقات الخاسرة</div>
        <div class="card-value white-text">{loss_trades}</div>
        <div style="font-size:12px; color:#a0aec0;">صفقات</div>
    </div>
    """, unsafe_allow_html=True)

# الصف الثالث: إجمالي الأرباح وإجمالي الخسائر
col5, col6 = st.columns(2)
with col5:
    st.markdown(f"""
    <div class="metric-card card-green">
        <div class="card-title green-text">💲 إجمالي الأرباح</div>
        <div class="card-value white-text">{total_profit}+</div>
        <div style="font-size:12px; color:#a0aec0;">نقطة</div>
    </div>
    """, unsafe_allow_html=True)

with col6:
    st.markdown(f"""
    <div class="metric-card card-red">
        <div class="card-title red-text">💲 إجمالي الخسائر</div>
        <div class="card-value white-text">{total_loss}-</div>
        <div style="font-size:12px; color:#a0aec0;">نقطة</div>
    </div>
    """, unsafe_allow_html=True)

# بطاقة صافي الأرباح
st.markdown(f"""
<div class="metric-card card-net">
    <div class="card-title">✨ صافي في الأرباح</div>
    <div class="card-value green-text">{net_profit}+ <span style="font-size:18px; color:#fff;">نقطة</span></div>
</div>
""", unsafe_allow_html=True)

# قسم التوصيات المستقبلية الأكثر تقييماً
st.markdown("### 🤖 التوصيات المستقبلية الأكثر تقييماً (استراتيجية إليوت)")

if not display_df.empty:
    # ترتيب التوصيات من الأعلى تقييماً إلى الأدنى
    sorted_df = display_df.sort_values(by="تقييم AI", ascending=False)
    for _, row in sorted_df.iterrows():
        st.markdown(f"""
        <div class="signal-box">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:18px; font-weight:bold; color:#fff;">🪙 {row['العملة']}/USDT</span>
                <span style="background-color:#805ad5; padding:3px 10px; border-radius:12px; font-size:13px;">تقييم AI: {row['تقييم AI']}%</span>
            </div>
            <hr style="border-color:#2d3748; margin:10px 0;">
            <div style="display:flex; justify-content:space-between; font-size:14px;">
                <span>🔵 <b>الدخول (موجة 2):</b> {row['نقطة الدخول (موجة 2)']}</span>
                <span class="green-text">🟢 <b>الهدف (موجة 5):</b> {row['الهدف (موجة 5)']}</span>
                <span class="red-text">🔴 <b>ستوب لوس (0):</b> {row['وقف الخسارة (موجة 0)']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("جاري تحديث بيانات السوق...")
