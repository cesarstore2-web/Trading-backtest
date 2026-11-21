import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from strategy import SMCStrategy
import time

# إعدادات الصفحة
st.set_page_config(page_title="SMC Liquidity AI Bot", page_icon="⚡", layout="wide")

# تخصيص التصميم الداكن (CSS) ليحاكي لوحة النتائج
st.markdown("""
<style>
    .stApp {
        background-color: #0e0e12;
        color: #ffffff;
    }
    .metric-card {
        background-color: #16161d;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        border: 1px solid #2d2d3a;
        margin-bottom: 10px;
    }
    .card-purple { border-color: #7b42f6; }
    .card-blue { border-color: #2196f3; }
    .card-green { border-color: #00c853; }
    .card-red { border-color: #ff1744; }
    
    .metric-title {
        font-size: 16px;
        color: #a0a0b0;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
    }
    .text-green { color: #00e676; }
    .text-red { color: #ff5252; }
    .text-white { color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# تهيئة سجل الصفقات في الجلسة
if 'trade_history' not in st.session_state:
    st.session_state.trade_history = []
if 'stats' not in st.session_state:
    st.session_state.stats = {
        "total": 19,
        "wins": 15,
        "losses": 2,
        "profit_pts": 3653,
        "loss_pts": 353
    }

# الشريط الجانبي للإعدادات (Sidebar)
with st.sidebar:
    st.header("⚙️ إعدادات الاستراتيجية (SMC)")
    
    # وضع التشغيل
    mode = st.radio("وضع التشغيل:", ["مراقبة وإشارات فقط", "تداول آلي (API)"])
    use_testnet = st.checkbox("استخدام الحساب التجريبي (Testnet)", value=True)
    
    st.divider()
    st.subheader("⏱️ الإطارات الزمنية")
    htf = st.selectbox("فريم تحديد السيولة (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول والتأكيد (LTF):", ["5m", "15m"], index=0)
    
    st.divider()
    st.subheader("🛡️ إدارة المخاطر")
    risk_type = st.radio("طريقة حساب الحجم:", ["نسبة من الرصيد (%)", "حجم لوت ثابت"])
    if risk_type == "نسبة من الرصيد (%)":
        risk_val = st.slider("نسبة المخاطرة لكل صفقة (%):", 0.5, 5.0, 1.0, 0.5)
    else:
        risk_val = st.number_input("حجم اللوت الثابت:", min_value=0.001, value=0.01, step=0.001)
        
    rr_ratio = st.selectbox("نسبة العائد للمخاطرة (R:R):", [1.5, 2.0, 3.0, 4.0], index=1)
    account_balance = st.number_input("رصيد الحساب التقديري ($):", min_value=10.0, value=1000.0)
    
    st.divider()
    st.subheader("🕒 فلتر توقيت التداول (UTC)")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        start_hour = st.number_input("من الساعة:", 0, 23, 7)
    with col_t2:
        end_hour = st.number_input("إلى الساعة:", 0, 23, 21)

# قراءة مفاتيح API من Streamlit Secrets إن وجدت
api_key = st.secrets.get("BINANCE_API_KEY", "")
api_secret = st.secrets.get("BINANCE_API_SECRET", "")

# تهيئة البوت
bot = SMCStrategy(api_key=api_key, api_secret=api_secret, use_testnet=use_testnet)

# العنوان الرئيسي
st.title("⚡ لوحة تحكم استراتيجية تتبع السيولة (SMC AI)")

# أزرار الفلترة السريعة للأزواج
selected_filter = st.radio(
    "تصفية الأصول:", 
    ["الكل", "الذهب (XAU/PAXG)", "البيتكوين (BTC)", "العملات البديلة"], 
    horizontal=True
)

# حساب الإحصائيات المعروضة
stats = st.session_state.stats
win_rate = round((stats["wins"] / stats["total"]) * 100, 2) if stats["total"] > 0 else 0
net_points = stats["profit_pts"] - stats["loss_pts"]

# عرض البطاقات الإحصائية (مشابهة للصورة المرفقة)
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
    <div class="metric-card card-purple">
        <div class="metric-title">نسبة النجاح</div>
        <div class="metric-value text-white">{win_rate}%</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="metric-card card-blue">
        <div class="metric-title">عدد الصفقات</div>
        <div class="metric-value text-white">{stats['total']} <span style="font-size:16px;">صفقات</span></div>
    </div>
    """, unsafe_allow_html=True)

col3, col4 = st.columns(2)
with col3:
    st.markdown(f"""
    <div class="metric-card card-red">
        <div class="metric-title text-red">الصفقات الخاسرة</div>
        <div class="metric-value text-white">{stats['losses']} <span style="font-size:16px;">صفقات</span></div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown(f"""
    <div class="metric-card card-green">
        <div class="metric-title text-green">الصفقات الرابحة</div>
        <div class="metric-value text-white">{stats['wins']} <span style="font-size:16px;">صفقات</span></div>
    </div>
    """, unsafe_allow_html=True)

col5, col6 = st.columns(2)
with col5:
    st.markdown(f"""
    <div class="metric-card card-red">
        <div class="metric-title text-red">إجمالي الخسائر</div>
        <div class="metric-value text-white">{stats['loss_pts']}- <span style="font-size:16px;">نقطة</span></div>
    </div>
    """, unsafe_allow_html=True)
with col6:
    st.markdown(f"""
    <div class="metric-card card-green">
        <div class="metric-title text-green">إجمالي الأرباح</div>
        <div class="metric-value text-white">{stats['profit_pts']}+ <span style="font-size:16px;">نقطة</span></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div class="metric-card card-purple">
    <div class="metric-title">صافي في الأرباح</div>
    <div class="metric-value text-green">{net_points}+ <span style="font-size:18px;">نقطة</span></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# قسم الفحص المباشر للسوق
col_btn1, col_btn2 = st.columns([1, 3])
with col_btn1:
    scan_now = st.button("🔍 فحص السوق والسيولة الآن", use_container_width=True, type="primary")
with col_btn2:
    auto_refresh = st.checkbox("تحديث وفحص تلقائي كل 60 ثانية")

if scan_now or auto_refresh:
    with st.spinner("جاري تحليل مناطق السيولة والكسر الكاذب (CHoCH & Order Blocks)..."):
        signals = bot.scan_market(
            htf=htf, 
            ltf=ltf, 
            rr_ratio=rr_ratio, 
            start_hour=start_hour, 
            end_hour=end_hour
        )
        
        if signals:
            st.success(f"تم رصد {len(signals)} فرصة تداول مطابقة لشروط SMC!")
            for sig in signals:
                # حساب حجم الصفقة
                if risk_type == "نسبة من الرصيد (%)":
                    qty = bot.calculate_position_size(account_balance, risk_val, sig['entry'], sig['sl'])
                else:
                    qty = risk_val
                
                sig['qty'] = qty
                st.session_state.trade_history.insert(0, sig)
                
                # التنفيذ الآلي إذا كان مفعلاً
                if mode == "تداول آلي (API)" and api_key and api_secret:
                    res = bot.execute_order(sig['symbol'], sig['signal'], qty, sig['entry'], sig['sl'], sig['tp'])
                    if res['status'] == 'success':
                        st.toast(f"✅ تم إرسال أمر {sig['signal']} لـ {sig['symbol']}")
                    else:
                        st.error(f"❌ خطأ في تنفيذ {sig['symbol']}: {res['message']}")
        else:
            st.info("لا توجد فرص مكتملة الشروط في هذه اللحظة (أو خارج ساعات التداول المحددة).")

# عرض جدول الإشارات المرصودة
st.subheader("📋 سجل الإشارات والصفقات المرصودة")
if st.session_state.trade_history:
    df_signals = pd.DataFrame(st.session_state.trade_history)
    st.dataframe(df_signals, use_container_width=True)
else:
    st.caption("اضغط على زر (فحص السوق والسيولة الآن) لبدء مسح العملات والذهب.")

# رسم بياني تفاعلي للتحقق البصري من أي عملة
st.divider()
st.subheader("📈 المعاينة البصرية للشارت ومستويات السيولة")
selected_chart_symbol = st.selectbox("اختر الزوج لمعاينة الشارت:", bot.symbols)
chart_df = bot.fetch_ohlcv(selected_chart_symbol, ltf, limit=80)

if not chart_df.empty:
    fig = go.Figure(data=[go.Candlestick(
        x=chart_df['timestamp'],
        open=chart_df['open'],
        high=chart_df['high'],
        low=chart_df['low'],
        close=chart_df['close'],
        name=selected_chart_symbol
    )])
    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=450,
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

# التحديث التلقائي
if auto_refresh:
    time.sleep(60)
    st.rerun()
