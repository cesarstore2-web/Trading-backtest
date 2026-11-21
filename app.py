import streamlit as st
from strategy import run_analysis

st.set_page_config(page_title="نظام العرض والطلب - كريبتو", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0e0e12; color: #ffffff; }
    .metric-card { 
        background-color: #16161d; 
        border-radius: 15px; 
        padding: 15px; 
        text-align: center; 
        margin-bottom: 12px; 
        border: 1px solid #2d2d3a;
        direction: rtl;
    }
    .card-green { border: 1.5px solid #00e676; }
    .card-red { border: 1.5px solid #ff1744; }
    .card-blue { border: 1.5px solid #00b0ff; }
    .card-purple { border: 1.5px solid #b388ff; }
    .val-green { color: #00e676; font-size: 24px; font-weight: bold; }
    .val-red { color: #ff1744; font-size: 24px; font-weight: bold; }
    .val-white { color: #ffffff; font-size: 24px; font-weight: bold; }
    .card-title { color: #a0a0b0; font-size: 13px; margin-bottom: 5px; }
    .stButton>button { 
        background-color: #7c4dff; 
        color: white; 
        border-radius: 12px; 
        height: 50px; 
        width: 100%; 
        font-size: 17px; 
        font-weight: bold; 
        border: none;
        margin-top: 8px;
        margin-bottom: 15px;
    }
    .stButton>button:hover { background-color: #651fff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align: center; color: #b388ff; direction: rtl;'>📊 نظام توصيات العرض والطلب</h3>", unsafe_allow_html=True)

# --- نوافذ الإعدادات ---
with st.expander("⚙️ إعدادات العملة والاستراتيجية", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        coins = tuple([
            "XLMUSDT", "ZECUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT",
            "ADAUSDT", "LTCUSDT", "HBARUSDT", "XAUUSDT", "PAXGUSDT"
        ])
        selected_coin = st.selectbox("اختر العملة:", coins)

        timeframes = {"5 دقائق": "5m", "15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}
        tf_label = st.selectbox("نافذة الفريمات:", tuple(timeframes.keys()))
        tf_code = timeframes[tf_label]

        ema_period = st.selectbox("نافذة EMA:", (20, 50, 100, 200))

    with col2:
        # نافذة ATR SL (مضاعف وقف الخسارة)
        atr_sl_mult = st.number_input("نافذة ATR SL (مضاعف الوقف):", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
        
        # نافذة العائد للمخاطرة
        rr_ratio = st.slider("نافذة العائد للمخاطرة (R : R):", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

# --- زر الفحص ---
if st.button("🔍 فحص العملة واستخراج التوصيات والنتائج"):
    with st.spinner(f"جاري تحليل {selected_coin} وحساب سجل الصفقات..."):
        res = run_analysis(selected_coin, tf_code, ema_period, atr_sl_mult, rr_ratio)
        
        if res:
            # السعر واتجاه 4 ساعات
            c1, c2 = st.columns(2)
            c1.markdown(f"<div class='metric-card card-purple'><div class='card-title'>السعر الحالي ({selected_coin})</div><div class='val-white'>{res['current_price']:.4f}</div></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الاتجاه العام (4 ساعات)</div><div class='val-white'>{res['trend_4h']}</div></div>", unsafe_allow_html=True)

            # بطاقة الإشارة
            c_style = "card-green" if "شراء" in res['signal'] else ("card-red" if "بيع" in res['signal'] else "card-purple")
            v_style = "val-green" if "شراء" in res['signal'] else ("val-red" if "بيع" in res['signal'] else "val-white")
            st.markdown(f"<div class='metric-card {c_style}'><div class='card-title'>التوصية الحالية</div><div class='{v_style}'>{res['signal']}</div><p style='color:#ccc; margin-top:6px; font-size:13px;'>{res['reason']}</p></div>", unsafe_allow_html=True)

            if res['entry'] > 0:
                p1, p2, p3 = st.columns(3)
                p1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الدخول</div><div class='val-white'>{res['entry']:.4f}</div></div>", unsafe_allow_html=True)
                p2.markdown(f"<div class='metric-card card-green'><div class='card-title'>الهدف (TP)</div><div class='val-green'>{res['tp']:.4f}</div></div>", unsafe_allow_html=True)
                p3.markdown(f"<div class='metric-card card-red'><div class='card-title'>الوقف (ATR SL)</div><div class='val-red'>{res['sl']:.4f}</div></div>", unsafe_allow_html=True)

            # المناطق المستقبلية
            st.markdown("<h4 style='text-align: right; color: #ffffff; direction: rtl; margin-top:10px;'>🔮 المناطق المستقبلية و EMA</h4>", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.markdown(f"<div class='metric-card card-green'><div class='card-title'>منطقة الطلب</div><div style='font-size:15px; font-weight:bold; color:#00e676;'>{res['demand_bottom']:.4f} - {res['demand_top']:.4f}</div></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card card-red'><div class='card-title'>منطقة العرض</div><div style='font-size:15px; font-weight:bold; color:#ff1744;'>{res['supply_bottom']:.4f} - {res['supply_top']:.4f}</div></div>", unsafe_allow_html=True)
            m3.markdown(f"<div class='metric-card'><div class='card-title'>EMA ({ema_period})</div><div style='font-size:16px; font-weight:bold;'>{res['ema']:.4f}</div></div>", unsafe_allow_html=True)

            # --- سجل الأداء والنتائج ---
            st.markdown("<h4 style='text-align: right; color: #b388ff; direction: rtl; margin-top:15px;'>📈 سجل الأداء والنتائج السابقة</h4>", unsafe_allow_html=True)
            st_data = res['stats']
            
            s1, s2 = st.columns(2)
            s1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>عدد الصفقات</div><div class='val-white'>{st_data['total_trades']}</div></div>", unsafe_allow_html=True)
            s2.markdown(f"<div class='metric-card card-purple'><div class='card-title'>نسبة النجاح</div><div class='val-white'>{st_data['win_rate']:.2f}%</div></div>", unsafe_allow_html=True)

            s3, s4 = st.columns(2)
            s3.markdown(f"<div class='metric-card card-green'><div class='card-title'>الصفقات الرابحة</div><div class='val-green'>{st_data['wins']}</div></div>", unsafe_allow_html=True)
            s4.markdown(f"<div class='metric-card card-red'><div class='card-title'>الصفقات الخاسرة</div><div class='val-red'>{st_data['losses']}</div></div>", unsafe_allow_html=True)

            s5, s6 = st.columns(2)
            s5.markdown(f"<div class='metric-card card-green'><div class='card-title'>إجمالي الأرباح</div><div class='val-green'>+{st_data['gross_profit']:.2f}%</div></div>", unsafe_allow_html=True)
            s6.markdown(f"<div class='metric-card card-red'><div class='card-title'>إجمالي الخسائر</div><div class='val-red'>-{st_data['gross_loss']:.2f}%</div></div>", unsafe_allow_html=True)

            net_color = "val-green" if st_data['net_profit'] >= 0 else "val-red"
            net_sign = "+" if st_data['net_profit'] >= 0 else ""
            st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>صافي الأرباح</div><div class='{net_color}'>{net_sign}{st_data['net_profit']:.2f}%</div></div>", unsafe_allow_html=True)
        else:
            st.error("تعذر جلب بيانات العملة حالياً، يرجى المحاولة مرة أخرى.")
