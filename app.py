import streamlit as st
from strategy import run_analysis

# جعل الشريط الجانبي مطوياً افتراضياً ليناسب شاشة الهاتف
st.set_page_config(page_title="نظام العرض والطلب", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0e0e12; color: #ffffff; }
    .rtl-box { direction: rtl; text-align: right; }
    .metric-card { 
        background-color: #16161d; 
        border-radius: 15px; 
        padding: 16px; 
        text-align: center; 
        margin-bottom: 12px; 
        border: 1px solid #2d2d3a;
        direction: rtl;
    }
    .card-green { border: 1.5px solid #00e676; }
    .card-red { border: 1.5px solid #ff1744; }
    .card-blue { border: 1.5px solid #00b0ff; }
    .card-purple { border: 1.5px solid #b388ff; }
    .val-green { color: #00e676; font-size: 26px; font-weight: bold; }
    .val-red { color: #ff1744; font-size: 26px; font-weight: bold; }
    .val-white { color: #ffffff; font-size: 26px; font-weight: bold; }
    .card-title { color: #a0a0b0; font-size: 14px; margin-bottom: 5px; }
    .stButton>button { 
        background-color: #7c4dff; 
        color: white; 
        border-radius: 12px; 
        height: 50px; 
        width: 100%; 
        font-size: 17px; 
        font-weight: bold; 
        border: none;
        margin-top: 10px;
        margin-bottom: 15px;
    }
    .stButton>button:hover { background-color: #651fff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align: center; color: #b388ff; direction: rtl;'>📊 لوحة تحكم استراتيجية العرض والطلب</h3>", unsafe_allow_html=True)

# --- نوافذ التحكم في قائمة قابلة للطي مناسبة للهاتف ---
with st.expander("⚙️ إعدادات الاستراتيجية والنوافذ (اضغط للتعديل)", expanded=True):
    col_set1, col_set2 = st.columns(2)
    
    with col_set1:
        assets = {
            "الذهب (Gold)": "GC=F",
            "البيتكوين (BTC)": "BTC-USD",
            "النفط (Crude Oil)": "CL=F",
            "الفضة (Silver)": "SI=F"
        }
        selected_asset = st.selectbox("الأصل المالي:", list(assets.keys()))
        ticker = assets[selected_asset]

        timeframes = {"5 دقائق": "5m", "15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}
        tf_label = st.selectbox("نافذة الفريمات:", list(timeframes.keys()))
        tf_code = timeframes[tf_label]

        ema_period = st.selectbox("نافذة EMA:", [20, 50, 100, 200], index=0)

    with col_set2:
        atr_period = st.number_input("نافذة ATR:", min_value=5, max_value=50, value=14)
        rr_ratio = st.slider("نافذة R : R (العائد للمخاطرة):", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

# --- زر الفحص والتوصيات المستقبلية ---
if st.button("🔍 فحص السوق واستخراج التوصيات المستقبلية"):
    with st.spinner("جاري فحص اتجاه 4 ساعات وشمعة 5 دقائق..."):
        res = run_analysis(ticker, tf_code, ema_period, atr_period, rr_ratio)
        
        if res:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>السعر الحالي ({selected_asset})</div><div class='val-white'>{res['current_price']:.2f}</div></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الاتجاه العام (4 ساعات)</div><div class='val-white'>{res['trend_4h']}</div></div>", unsafe_allow_html=True)

            c_style = "card-green" if "شراء" in res['signal'] else ("card-red" if "بيع" in res['signal'] else "card-purple")
            v_style = "val-green" if "شراء" in res['signal'] else ("val-red" if "بيع" in res['signal'] else "val-white")
            st.markdown(f"<div class='metric-card {c_style}'><div class='card-title'>نتيجة الفحص</div><div class='{v_style}'>{res['signal']}</div><p style='color:#ccc; margin-top:8px; font-size:14px;'>{res['reason']}</p></div>", unsafe_allow_html=True)

            if res['entry'] > 0:
                p1, p2, p3 = st.columns(3)
                p1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>نقطة الدخول</div><div class='val-white'>{res['entry']:.2f}</div></div>", unsafe_allow_html=True)
                p2.markdown(f"<div class='metric-card card-green'><div class='card-title'>الهدف (TP)</div><div class='val-green'>{res['tp']:.2f}</div></div>", unsafe_allow_html=True)
                p3.markdown(f"<div class='metric-card card-red'><div class='card-title'>وقف الخسارة (SL)</div><div class='val-red'>{res['sl']:.2f}</div></div>", unsafe_allow_html=True)

            st.markdown("<h4 style='text-align: right; color: #ffffff; direction: rtl; margin-top:15px;'>🔮 المناطق المستقبلية والمؤشرات</h4>", unsafe_allow_html=True)
            m1, m2 = st.columns(2)
            m1.markdown(f"<div class='metric-card card-green'><div class='card-title'>منطقة الطلب (شراء)</div><div style='font-size:17px; font-weight:bold; color:#00e676;'>{res['demand_bottom']:.2f} - {res['demand_top']:.2f}</div></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card card-red'><div class='card-title'>منطقة العرض (بيع)</div><div style='font-size:17px; font-weight:bold; color:#ff1744;'>{res['supply_bottom']:.2f} - {res['supply_top']:.2f}</div></div>", unsafe_allow_html=True)
            
            m3, m4 = st.columns(2)
            m3.markdown(f"<div class='metric-card'><div class='card-title'>EMA ({ema_period})</div><div style='font-size:19px; font-weight:bold;'>{res['ema']:.2f}</div></div>", unsafe_allow_html=True)
            m4.markdown(f"<div class='metric-card'><div class='card-title'>ATR ({atr_period})</div><div style='font-size:19px; font-weight:bold;'>{res['atr']:.2f}</div></div>", unsafe_allow_html=True)
        else:
            st.error("تعذر جلب البيانات حالياً، حاول مرة أخرى.")
