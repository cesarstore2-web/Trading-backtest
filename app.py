import streamlit as st
from strategy import run_analysis, scan_all_coins

st.set_page_config(page_title="نظام اختراق الشمعة و EMA", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0e0e12; color: #ffffff; }
    .metric-card { 
        background-color: #16161d; 
        border-radius: 15px; 
        padding: 18px; 
        text-align: center; 
        margin-bottom: 12px; 
        border: 1px solid #2d2d3a;
        direction: rtl;
    }
    .card-green { border: 2px solid #00e676; }
    .card-red { border: 2px solid #ff1744; }
    .card-blue { border: 1.5px solid #00b0ff; }
    .card-purple { border: 2px solid #b388ff; }
    .card-gold { border: 2px solid #ffd740; background-color: #1c1b24; }
    
    /* خط وألوان واضحة للنتائج */
    .big-green { color: #00e676; font-size: 32px; font-weight: 900; }
    .big-red { color: #ff1744; font-size: 32px; font-weight: 900; }
    .big-white { color: #ffffff; font-size: 28px; font-weight: bold; }
    .card-title { color: #b0b0c0; font-size: 15px; font-weight: bold; margin-bottom: 6px; }
    
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

st.markdown("<h3 style='text-align: center; color: #b388ff; direction: rtl;'>📊 استراتيجية اختراق الشمعة + متوسطات (5 / 13 / 34)</h3>", unsafe_allow_html=True)

coins = (
    "XLMUSDT", "ZECUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT",
    "ADAUSDT", "LTCUSDT", "HBARUSDT", "XAUUSDT", "PAXGUSDT"
)

# --- نوافذ الإعدادات ---
with st.expander("⚙️ إعدادات العملة وإدارة رأس المال", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        selected_coin = st.selectbox("اختر العملة:", coins)

        timeframes = {"5 دقائق": "5m", "15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}
        tf_label = st.selectbox("نافذة الفريمات:", tuple(timeframes.keys()))
        tf_code = timeframes[tf_label]

        use_4h_filter = st.checkbox("تفعيل فلتر الاتجاه العام (4 ساعات)", value=True)

    with col2:
        atr_sl_mult = st.number_input("نافذة ATR SL (مضاعف الوقف):", min_value=0.1, max_value=10.0, value=1.5, step=0.1)
        rr_ratio = st.number_input("نافذة العائد للمخاطرة (R : R):", min_value=0.5, max_value=20.0, value=2.0, step=0.5)
        trade_size_usd = st.number_input("حجم الصفقة بالدولار ($):", min_value=10.0, max_value=100000.0, value=100.0, step=10.0)

# --- أزرار الفحص ---
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    single_scan = st.button("🔍 فحص العملة المختارة")
with btn_col2:
    full_scan = st.button("🌐 فحص شامل واستخراج أفضل 3 توصيات")

# --- التلوين التلقائي للجدول ---
def highlight_signals(row):
    signal = str(row['التوصية'])
    if 'شراء' in signal:
        return ['background-color: rgba(0, 230, 118, 0.25); color: #00e676; font-weight: bold;'] * len(row)
    elif 'بيع' in signal:
        return ['background-color: rgba(255, 23, 68, 0.25); color: #ff1744; font-weight: bold;'] * len(row)
    return ['background-color: #16161d; color: #e0e0e0;'] * len(row)

# --- تنفيذ الفحص الفردي ---
if single_scan:
    with st.spinner(f"جاري فحص اختراق الشمعة لعملة {selected_coin}..."):
        res = run_analysis(selected_coin, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
        
        if res:
            c1, c2 = st.columns(2)
            c1.markdown(f"<div class='metric-card card-purple'><div class='card-title'>السعر الحالي ({selected_coin})</div><div class='big-white'>{res['current_price']:.4f}</div></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card card-blue'><div class='card-title'>فلتر الاتجاه (4 ساعات)</div><div class='big-white'>{res['trend_4h']}</div></div>", unsafe_allow_html=True)

            c_style = "card-green" if "شراء" in res['signal'] else ("card-red" if "بيع" in res['signal'] else "card-purple")
            v_style = "big-green" if "شراء" in res['signal'] else ("big-red" if "بيع" in res['signal'] else "big-white")
            st.markdown(f"<div class='metric-card {c_style}'><div class='card-title'>توصية اختراق الشمعة</div><div class='{v_style}'>{res['signal']}</div><p style='color:#ccc; margin-top:6px; font-size:14px;'>{res['reason']}</p></div>", unsafe_allow_html=True)

            if res['entry'] > 0:
                p1, p2, p3 = st.columns(3)
                p1.markdown(f"<div class='metric-card card-blue'><div class='card-title'>الدخول</div><div class='big-white'>{res['entry']:.4f}</div></div>", unsafe_allow_html=True)
                p2.markdown(f"<div class='metric-card card-green'><div class='card-title'>الهدف (TP)</div><div class='big-green'>{res['tp']:.4f}</div></div>", unsafe_allow_html=True)
                p3.markdown(f"<div class='metric-card card-red'><div class='card-title'>الوقف (ATR SL)</div><div class='big-red'>{res['sl']:.4f}</div></div>", unsafe_allow_html=True)

            # --- الثلاث بطاقات المطلوبة فقط بخط وألوان واضحة ---
            st.markdown("<h4 style='text-align: right; color: #b388ff; direction: rtl; margin-top:15px;'>📈 ملخص تقييم الشهر السابق (30 يوماً)</h4>", unsafe_allow_html=True)
            st_data = res['stats']
            
            s1, s2, s3 = st.columns(3)
            s1.markdown(f"<div class='metric-card card-green'><div class='card-title'>الصفقات الناجحة</div><div class='big-green'>{st_data['wins']}</div></div>", unsafe_allow_html=True)
            s2.markdown(f"<div class='metric-card card-red'><div class='card-title'>الصفقات الخاسرة</div><div class='big-red'>{st_data['losses']}</div></div>", unsafe_allow_html=True)
            
            net_usd = st_data['net_profit_usd']
            net_color = "big-green" if net_usd >= 0 else "big-red"
            net_card = "card-green" if net_usd >= 0 else "card-red"
            net_sign = "+" if net_usd >= 0 else ""
            s3.markdown(f"<div class='metric-card {net_card}'><div class='card-title'>الربح الصافي ($)</div><div class='{net_color}'>{net_sign}{net_usd:.2f}$</div></div>", unsafe_allow_html=True)
        else:
            st.error("تعذر جلب بيانات العملة حالياً.")

# --- تنفيذ الفحص الشامل + أفضل 3 توصيات ---
if full_scan:
    with st.spinner("جاري مسح العملات العشر وتقييم نتائج الشهر السابق..."):
        df_scan, top_3 = scan_all_coins(coins, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
        
        if not df_scan.empty:
            st.markdown("<h4 style='text-align: right; color: #b388ff; direction: rtl;'>🌐 جدول الفحص الشامل للعملات</h4>", unsafe_allow_html=True)
            styled_df = df_scan.style.apply(highlight_signals, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            # --- عرض أفضل 3 توصيات في الأخير ---
            st.markdown("<h4 style='text-align: right; color: #ffd740; direction: rtl; margin-top:20px;'>🏆 أفضل 3 توصيات (الأكثر دقة وتقييماً خلال الشهر)</h4>", unsafe_allow_html=True)
            t_cols = st.columns(3)
            for idx, item in enumerate(top_3):
                with t_cols[idx]:
                    sig_color = "#00e676" if "شراء" in item['signal'] else ("#ff1744" if "بيع" in item['signal'] else "#ffffff")
                    net_u = item['stats']['net_profit_usd']
                    u_color = "#00e676" if net_u >= 0 else "#ff1744"
                    
                    targets_html = ""
                    if item['entry'] > 0:
                        targets_html = f"<div style='font-size:13px; color:#ccc; margin-top:6px;'>دخول: <b>{item['entry']:.4f}</b> | هدف: <b style='color:#00e676;'>{item['tp']:.4f}</b> | وقف: <b style='color:#ff1744;'>{item['sl']:.4f}</b></div>"
                    
                    st.markdown(f"""
                    <div class='metric-card card-gold'>
                        <div style='color:#ffd740; font-size:14px; font-weight:bold;'>المركز #{idx+1} — {item['coin']}</div>
                        <div style='color:{sig_color}; font-size:22px; font-weight:900; margin:6px 0;'>{item['signal']}</div>
                        <div style='font-size:14px; color:#e0e0e0;'>ناجحة: <b style='color:#00e676;'>{item['stats']['wins']}</b> | خاسرة: <b style='color:#ff1744;'>{item['stats']['losses']}</b></div>
                        <div style='font-size:16px; margin-top:4px;'>الربح الصافي: <b style='color:{u_color};'>{net_u:+.2f}$</b></div>
                        {targets_html}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.error("تعذر إتمام الفحص الشامل حالياً.")
