import streamlit as st
from strategy import run_analysis, scan_all_coins

st.set_page_config(page_title="استراتيجية تقاطع EMA 5-13-34", layout="wide", initial_sidebar_state="collapsed")

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
        height: 48px; 
        width: 100%; 
        font-size: 16px; 
        font-weight: bold; 
        border: none;
        margin-top: 5px;
        margin-bottom: 10px;
    }
    .stButton>button:hover { background-color: #651fff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align: center; color: #b388ff; direction: rtl;'>📊 استراتيجية تقاطع 3 متوسطات (EMA 5 / 13 / 34)</h3>", unsafe_allow_html=True)

coins = (
    "XLMUSDT", "ZECUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT",
    "ADAUSDT", "LTCUSDT", "HBARUSDT", "XAUUSDT", "PAXGUSDT"
)

# --- نوافذ الإعدادات ---
with st.expander("⚙️ إعدادات العملة وإدارة المخاطر", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        selected_coin = st.selectbox("اختر العملة (للفحص الفردي):", coins)

        timeframes = {"5 دقائق": "5m", "15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}
        tf_label = st.selectbox("نافذة الفريمات:", tuple(timeframes.keys()))
        tf_code = timeframes[tf_label]

        # فلتر اتجاه 4 ساعات الاختياري
        use_4h_filter = st.checkbox("تفعيل فلتر الاتجاه العام (4 ساعات)", value=True)

    with col2:
        atr_sl_mult = st.number_input("نافذة ATR SL (مضاعف الوقف):", min_value=0.1, max_value=10.0, value=1.5, step=0.1)
        rr_ratio = st.number_input("نافذة العائد للمخاطرة (R : R):", min_value=0.5, max_value=20.0, value=2.0, step=0.5)

# --- أزرار الفحص (فردي + شامل) ---
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    single_scan = st.button("🔍 فحص العملة المختارة")

with btn_col2:
    full_scan = st.button("🌐 فحص شامل لجميع العملات (10)")

# --- تنفيذ الفحص الفردي ---
if single_scan:
    with st.spinner(f"جاري فحص {selected_coin}..."):
        res = run_analysis(selected_coin, tf_code, atr_sl_mult, rr_ratio, use_4h_filter)
        
        if res:
            c1, c2 = st.columns(2)
            c1.markdown(f"<div class='metric-card card-purple'><div class='card-title'>السعر الحالي ({selected_coin})</div><div class='val-white'>{res['current_price']:.4f}</div></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card card-blue'><div class='card-title'>فلتر الاتجاه (4 ساعات)</div><div class='val-white'>{res['trend_4h']}</div></div>", unsafe_allow_html=True)

            c_style = "card-green" if "شراء" in res['signal'] else ("card-red" if "بيع" in res['signal'] else "card-purple")
            v_style = "val-green" if "شراء" in res['signal'] else ("val-red" if "بيع" in res['signal'] else "val-white")
            st.markdown(f"<div class='metric-card {c_style}'><div class='card-title'>حالة التقاطع والتوصية</div><div class='{v_style}'>{res['signal']}</div><p style='color:#ccc; margin-top:6px; font-size:13px;'>{res['reason']}</p></div>", unsafe_allow_html=True)

            if res['entry'] > 0:
                p1, p2, p3 = st.columns(3)
                p1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الدخول</div><div class='val-white'>{res['entry']:.4f}</div></div>", unsafe_allow_html=True)
                p2.markdown(f"<div class='metric-card card-green'><div class='card-title'>الهدف (TP)</div><div class='val-green'>{res['tp']:.4f}</div></div>", unsafe_allow_html=True)
                p3.markdown(f"<div class='metric-card card-red'><div class='card-title'>الوقف (ATR SL)</div><div class='val-red'>{res['sl']:.4f}</div></div>", unsafe_allow_html=True)

            st.markdown("<h4 style='text-align: right; color: #ffffff; direction: rtl; margin-top:10px;'>📉 قيم المتوسطات المتحركة</h4>", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.markdown(f"<div class='metric-card card-green'><div class='card-title'>EMA 5</div><div style='font-size:17px; font-weight:bold; color:#00e676;'>{res['ema_5']:.4f}</div></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card card-blue'><div class='card-title'>EMA 13</div><div style='font-size:17px; font-weight:bold; color:#00b0ff;'>{res['ema_13']:.4f}</div></div>", unsafe_allow_html=True)
            m3.markdown(f"<div class='metric-card card-purple'><div class='card-title'>EMA 34</div><div style='font-size:17px; font-weight:bold; color:#b388ff;'>{res['ema_34']:.4f}</div></div>", unsafe_allow_html=True)

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
            st.error("تعذر جلب بيانات العملة حالياً.")

# --- تنفيذ الفحص الشامل لجميع العملات ---
if full_scan:
    with st.spinner("جاري مسح العملات العشر واستخراج الفرص الجاهزة..."):
        df_scan = scan_all_coins(coins, tf_code, atr_sl_mult, rr_ratio, use_4h_filter)
        if not df_scan.empty:
            st.markdown("<h4 style='text-align: right; color: #b388ff; direction: rtl;'>🌐 نتائج الفحص الشامل للعملات</h4>", unsafe_allow_html=True)
            st.dataframe(df_scan, use_container_width=True, hide_index=True)
        else:
            st.error("تعذر إتمام الفحص الشامل حالياً.")
