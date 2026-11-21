import streamlit as st
from strategy import run_analysis

# إعدادات الصفحة والتصميم الداكن
st.set_page_config(page_title="نظام العرض والطلب", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e0e12; color: #ffffff; direction: rtl; text-align: right; }
    .metric-card { background-color: #16161d; border-radius: 15px; padding: 18px; text-align: center; margin-bottom: 15px; border: 1px solid #2d2d3a; }
    .card-green { border: 1.5px solid #00e676; }
    .card-red { border: 1.5px solid #ff1744; }
    .card-blue { border: 1.5px solid #00b0ff; }
    .card-purple { border: 1.5px solid #b388ff; }
    .val-green { color: #00e676; font-size: 28px; font-weight: bold; }
    .val-red { color: #ff1744; font-size: 28px; font-weight: bold; }
    .val-white { color: #ffffff; font-size: 28px; font-weight: bold; }
    .card-title { color: #a0a0b0; font-size: 15px; margin-bottom: 6px; }
    .stButton>button { background-color: #7c4dff; color: white; border-radius: 12px; height: 50px; width: 100%; font-size: 18px; font-weight: bold; border: none; }
    .stButton>button:hover { background-color: #651fff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='text-align: center; color: #b388ff;'>📊 لوحة تحكم استراتيجية العرض والطلب</h2>", unsafe_allow_html=True)

# --- الشريط الجانبي (النوافذ المطلوبة) ---
st.sidebar.header("⚙️ نوافذ التحكم")

assets = {
    "الذهب (Gold)": "GC=F",
    "البيتكوين (BTC)": "BTC-USD",
    "النفط (Crude Oil)": "CL=F",
    "الفضة (Silver)": "SI=F"
}
selected_asset = st.sidebar.selectbox("الأصل المالي:", list(assets.keys()))
ticker = assets[selected_asset]

# نافذة الفريمات 5 و 15 و 30 دقيقة و 1 ساعة
timeframes = {"5 دقائق": "5m", "15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}
tf_label = st.sidebar.selectbox("نافذة الفريمات:", list(timeframes.keys()))
tf_code = timeframes[tf_label]

# نافذة EMA 20 50 100 200
ema_period = st.sidebar.selectbox("نافذة EMA:", [20, 50, 100, 200])

# نافذة ATR
atr_period = st.sidebar.number_input("نافذة ATR:", min_value=5, max_value=50, value=14)

# نافذة R : R
rr_ratio = st.sidebar.slider("نافذة R : R (العائد للمخاطرة):", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

# --- زر الفحص والتوصيات المستقبلية ---
if st.button("🔍 فحص السوق واستخراج التوصيات المستقبلية"):
    with st.spinner("جاري تحليل السوق وفحص اتجاه 4 ساعات وشمعة 5 دقائق..."):
        res = run_analysis(ticker, tf_code, ema_period, atr_period, rr_ratio)
        
        if res:
            # السعر واتجاه 4 ساعات
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>السعر الحالي ({selected_asset})</div><div class='val-white'>{res['current_price']:.2f}</div></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الاتجاه العام في الخفاء (4 ساعات)</div><div class='val-white'>{res['trend_4h']}</div></div>", unsafe_allow_html=True)

            # بطاقة الإشارة الرئيسية
            c_style = "card-green" if "شراء" in res['signal'] else ("card-red" if "بيع" in res['signal'] else "card-purple")
            v_style = "val-green" if "شراء" in res['signal'] else ("val-red" if "بيع" in res['signal'] else "val-white")
            st.markdown(f"<div class='metric-card {c_style}'><div class='card-title'>نتيجة الفحص</div><div class='{v_style}'>{res['signal']}</div><p style='color:#ccc; margin-top:8px;'>{res['reason']}</p></div>", unsafe_allow_html=True)

            # تفاصيل الصفقة إن وجدت
            if res['entry'] > 0:
                p1, p2, p3 = st.columns(3)
                p1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>نقطة الدخول</div><div class='val-white'>{res['entry']:.2f}</div></div>", unsafe_allow_html=True)
                p2.markdown(f"<div class='metric-card card-green'><div class='card-title'>الهدف (TP)</div><div class='val-green'>{res['tp']:.2f}</div></div>", unsafe_allow_html=True)
                p3.markdown(f"<div class='metric-card card-red'><div class='card-title'>وقف الخسارة (SL)</div><div class='val-red'>{res['sl']:.2f}</div></div>", unsafe_allow_html=True)

            # التوصيات والمناطق المستقبلية
            st.markdown("### 🔮 المناطق المستقبلية والمؤشرات")
            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(f"<div class='metric-card card-green'><div class='card-title'>منطقة الطلب (للشراء)</div><div style='font-size:18px; font-weight:bold; color:#00e676;'>{res['demand_bottom']:.2f} - {res['demand_top']:.2f}</div></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card card-red'><div class='card-title'>منطقة العرض (للبيع)</div><div style='font-size:18px; font-weight:bold; color:#ff1744;'>{res['supply_bottom']:.2f} - {res['supply_top']:.2f}</div></div>", unsafe_allow_html=True)
            m3.markdown(f"<div class='metric-card'><div class='card-title'>EMA ({ema_period})</div><div style='font-size:20px; font-weight:bold;'>{res['ema']:.2f}</div></div>", unsafe_allow_html=True)
            m4.markdown(f"<div class='metric-card'><div class='card-title'>ATR ({atr_period})</div><div style='font-size:20px; font-weight:bold;'>{res['atr']:.2f}</div></div>", unsafe_allow_html=True)
        else:
            st.error("تعذر جلب البيانات حالياً، حاول مرة أخرى.")
