import streamlit as st
from strategy import run_analysis, scan_all_coins

st.set_page_config(page_title="نظام اختراق الشمعة والتوصيات المستقبلية", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0b0b0f; color: #ffffff; }
    
    /* تصميم البطاقات المطابق للصورة المرفقة */
    .box-win {
        background: linear-gradient(145deg, #0c1f17, #12141a);
        border: 1.5px solid #00c853;
        border-radius: 16px;
        padding: 18px;
        text-align: center;
        direction: rtl;
        margin-bottom: 12px;
    }
    .box-loss {
        background: linear-gradient(145deg, #240e13, #12141a);
        border: 1.5px solid #ff1744;
        border-radius: 16px;
        padding: 18px;
        text-align: center;
        direction: rtl;
        margin-bottom: 12px;
    }
    .box-net {
        background: linear-gradient(145deg, #1b1429, #13131a);
        border: 1.5px solid #7c4dff;
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        direction: rtl;
        margin-bottom: 15px;
    }
    .box-future {
        background-color: #15151e;
        border: 1.5px solid #00b0ff;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        direction: rtl;
        margin-bottom: 12px;
    }
    .box-gold {
        background: linear-gradient(145deg, #1f1c14, #14141c);
        border: 1.5px solid #ffd740;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        direction: rtl;
        margin-bottom: 12px;
    }
    
    .title-win { color: #00e676; font-size: 16px; font-weight: bold; margin-bottom: 6px; }
    .title-loss { color: #ff5252; font-size: 16px; font-weight: bold; margin-bottom: 6px; }
    .title-net { color: #b388ff; font-size: 17px; font-weight: bold; margin-bottom: 6px; }
    
    .num-white { color: #ffffff; font-size: 34px; font-weight: 900; line-height: 1.2; }
    .num-green { color: #00e676; font-size: 36px; font-weight: 900; line-height: 1.2; }
    .num-red { color: #ff1744; font-size: 36px; font-weight: 900; line-height: 1.2; }
    .sub-label { color: #9e9eb0; font-size: 13px; margin-top: 4px; }

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

st.markdown("<h3 style='text-align: center; color: #b388ff; direction: rtl;'>📊 نظام اختراق الشمعة والتوصيات المستقبلية</h3>", unsafe_allow_html=True)

coins = (
    "XLMUSDT", "ZECUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT",
    "ADAUSDT", "LTCUSDT", "HBARUSDT", "XAUUSDT", "PAXGUSDT"
)

# --- نوافذ الإعدادات ---
with st.expander("⚙️ إعدادات العملة وإدارة المخاطر", expanded=True):
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

def highlight_signals(row):
    signal = str(row['الحالة'])
    if 'شراء' in signal:
        return ['background-color: rgba(0, 230, 118, 0.25); color: #00e676; font-weight: bold;'] * len(row)
    elif 'بيع' in signal:
        return ['background-color: rgba(255, 23, 68, 0.25); color: #ff1744; font-weight: bold;'] * len(row)
    return ['background-color: #16161d; color: #e0e0e0;'] * len(row)

# --- تنفيذ الفحص الفردي ---
if single_scan:
    with st.spinner(f"جاري فحص {selected_coin} وحساب التوصيات المستقبلية..."):
        res = run_analysis(selected_coin, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
        
        if res:
            st_data = res['stats']
            
            # --- 1. بطاقات الأداء (الصفقات الناجحة، الخاسرة، والربح الصافي بالدولار) ---
            st.markdown("<h4 style='text-align: right; color: #ffffff; direction: rtl;'>📈 تقييم الشهر السابق (30 يوماً)</h4>", unsafe_allow_html=True)
            c_win, c_loss = st.columns(2)
            with c_win:
                st.markdown(f"""
                <div class='box-win'>
                    <div class='title-win'>📈 الصفقات الناجحة</div>
                    <div class='num-white'>{st_data['wins']}</div>
                    <div class='sub-label'>صفقات</div>
                </div>
                """, unsafe_allow_html=True)
            with c_loss:
                st.markdown(f"""
                <div class='box-loss'>
                    <div class='title-loss'>📉 الصفقات الخاسرة</div>
                    <div class='num-white'>{st_data['losses']}</div>
                    <div class='sub-label'>صفقات</div>
                </div>
                """, unsafe_allow_html=True)

            net_usd = st_data['net_profit_usd']
            net_cls = "num-green" if net_usd >= 0 else "num-red"
            net_sign = "+" if net_usd >= 0 else ""
            st.markdown(f"""
            <div class='box-net'>
                <div class='title-net'>صافي الأرباح (بالدولار الأمريكي)</div>
                <div class='{net_cls}'>{net_sign}{net_usd:.2f} $</div>
            </div>
            """, unsafe_allow_html=True)

            # --- 2. التوصية المستقبلية للعملة ---
            st.markdown("<h4 style='text-align: right; color: #00b0ff; direction: rtl; margin-top:15px;'>🔮 التوصية المستقبلية القادمة</h4>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class='box-future'>
                <div style='color:#00b0ff; font-size:15px; font-weight:bold;'>{selected_coin} — السعر الحالي: {res['current_price']:.4f}</div>
                <div style='color:#ffffff; font-size:20px; font-weight:bold; margin:8px 0;'>{res['future_dir']}</div>
                <div style='font-size:15px; color:#e0e0e0;'>
                    نقطة الدخول (الاختراق): <b style='color:#ffffff;'>{res['fut_entry']:.4f}</b> &nbsp;|&nbsp; 
                    الهدف: <b style='color:#00e676;'>{res['fut_tp']:.4f}</b> &nbsp;|&nbsp; 
                    الوقف: <b style='color:#ff1744;'>{res['fut_sl']:.4f}</b>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("تعذر جلب بيانات العملة حالياً.")

# --- تنفيذ الفحص الشامل + أفضل 3 توصيات مستقبلية ---
if full_scan:
    with st.spinner("جاري مسح العملات العشر واستخراج التوصيات المستقبلية..."):
        df_scan, top_3 = scan_all_coins(coins, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
        
        if not df_scan.empty:
            st.markdown("<h4 style='text-align: right; color: #b388ff; direction: rtl;'>🌐 جدول الفحص الشامل والتوصيات المستقبلية</h4>", unsafe_allow_html=True)
            styled_df = df_scan.style.apply(highlight_signals, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            st.markdown("<h4 style='text-align: right; color: #ffd740; direction: rtl; margin-top:20px;'>🏆 أفضل 3 توصيات مستقبلية (الأكثر دقة وتقييماً)</h4>", unsafe_allow_html=True)
            t_cols = st.columns(3)
            for idx, item in enumerate(top_3):
                with t_cols[idx]:
                    net_u = item['stats']['net_profit_usd']
                    u_color = "#00e676" if net_u >= 0 else "#ff1744"
                    dir_color = "#00e676" if "شراء" in item['future_dir'] else "#ff1744"
                    
                    st.markdown(f"""
                    <div class='box-gold'>
                        <div style='color:#ffd740; font-size:15px; font-weight:bold;'>المركز #{idx+1} — {item['coin']}</div>
                        <div style='color:{dir_color}; font-size:17px; font-weight:bold; margin:8px 0;'>{item['future_dir']}</div>
                        <div style='font-size:14px; color:#ffffff; margin-bottom:6px;'>
                            دخول: <b>{item['fut_entry']:.4f}</b><br>
                            هدف: <b style='color:#00e676;'>{item['fut_tp']:.4f}</b> | وقف: <b style='color:#ff1744;'>{item['fut_sl']:.4f}</b>
                        </div>
                        <hr style='border-color:#2d2d3a; margin:8px 0;'>
                        <div style='font-size:13px; color:#ccc;'>
                            ناجحة: <b style='color:#00e676;'>{item['stats']['wins']}</b> | 
                            خاسرة: <b style='color:#ff1744;'>{item['stats']['losses']}</b> | 
                            الصافي: <b style='color:{u_color};'>{net_u:+.2f}$</b>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.error("تعذر إتمام الفحص الشامل حالياً.")
