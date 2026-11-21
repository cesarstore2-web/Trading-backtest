import streamlit as st
import pandas as pd
import plotly.express as px
from smc_engine import ASSETS_MAP, fetch_data, analyze_smc_strategy

# 1. إعداد الصفحة (إغلاق القائمة الجانبية افتراضياً لمنع تداخل النصوص على الهاتف)
st.set_page_config(
    page_title="SMC AI Pro Trading",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تصميم CSS متجاوب مع الهاتف والحاسوب بدون أي تشوه
st.markdown("""
<style>
    @import url('https://googleapis.com');
    
    .stApp {
        background-color: #09090d;
        color: #ffffff;
        font-family: 'Cairo', sans-serif;
    }
    
    /* تنسيق النصوص العربية بدون كسر عناصر Streamlit */
    .rtl-text {
        direction: rtl;
        text-align: right;
        font-family: 'Cairo', sans-serif;
    }
    
    /* تنسيق زر الفحص والبحث */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #7c4dff, #00b0ff);
        color: white;
        font-family: 'Cairo', sans-serif;
        font-size: 1.15rem;
        font-weight: 800;
        border: none;
        border-radius: 14px;
        padding: 0.75rem 1.5rem;
        width: 100%;
        box-shadow: 0 4px 15px rgba(124, 77, 255, 0.4);
        transition: 0.3s;
    }
    div.stButton > button:first-child:hover {
        transform: scale(1.01);
        box-shadow: 0 6px 20px rgba(124, 77, 255, 0.6);
    }

    /* البطاقات الإحصائية */
    .stat-box {
        background: linear-gradient(145deg, #13131b, #191924);
        border-radius: 16px;
        padding: 18px;
        text-align: center;
        border: 1px solid #262636;
        box-shadow: 0 8px 20px rgba(0,0,0,0.4);
        margin-bottom: 12px;
        direction: rtl;
    }
    .box-purple { border-top: 4px solid #8c52ff; }
    .box-blue { border-top: 4px solid #00b0ff; }
    .box-green { border-top: 4px solid #00e676; }
    .box-red { border-top: 4px solid #ff1744; }
    .box-net {
        background: linear-gradient(135deg, #161324, #22193d);
        border: 1px solid #7c4dff;
        border-radius: 18px;
        padding: 22px;
        text-align: center;
        margin: 10px 0 20px 0;
        direction: rtl;
    }
    .stat-label { font-size: 1rem; color: #a5a5c0; font-weight: 700; }
    .stat-number { font-size: 2.2rem; font-weight: 900; margin: 5px 0; }
    .stat-sub { font-size: 0.82rem; color: #7a7a95; }
</style>
""", unsafe_allow_html=True)

# 3. القائمة الجانبية للإعدادات المتقدمة (تفتح من السهم الصغير أعلى اليسار عند الحاجة)
with st.sidebar:
    st.markdown('<h3 class="rtl-text">⚙️ إعدادات الاستراتيجية</h3>', unsafe_allow_html=True)
    htf = st.selectbox("فريم تحديد المناطق (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول والتأكيد (LTF):", ["15m", "5m"], index=0)
    rr_ratio = st.slider("نسبة العائد للمخاطرة (Risk : Reward):", 1.5, 5.0, 2.0, 0.5)
    risk_per_trade = st.number_input("نسبة المخاطرة لكل صفقة (%):", 0.5, 5.0, 1.0, 0.5)
    start_h, end_h = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI (%):", 55, 95, 65)

# 4. العنوان الرئيسي
st.markdown("""
<div class="rtl-text">
    <h2 style="margin-bottom:0;">⚡ نظام التداول الذكي (SMC + AI)</h2>
    <p style="color:#9e9eb8; font-size:0.95rem;">تتبع السيولة، الكسر الكاذب، وتأكيد CHoCH للعملات الرقمية والذهب</p>
</div>
""", unsafe_allow_html=True)

# 5. نافذة واحدة لاختيار المدة + اختيار العملة + زر الفحص
col1, col2 = st.columns(2)
with col1:
    timeframe_view = st.selectbox("📅 سجل الأداء والنتائج:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with col2:
    selected_asset = st.selectbox("🪙 اختر العملة أو الذهب:", ["الكل"] + list(ASSETS_MAP.keys()))

# زر الفحص والبحث عن توصيات
search_clicked = st.button("🔍 فحص والبحث عن توصيات الآن")

# تشغيل الفحص تلقائياً عند فتح الصفحة أو عند الضغط على الزر
days_back = 30 if "شهري" in timeframe_view else 7
cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_back)

with st.spinner("جاري فحص مناطق السيولة وتقييم التوصيات بالذكاء الاصطناعي..."):
    all_results = []
    targets = ASSETS_MAP.items() if selected_asset == "الكل" else [(selected_asset, ASSETS_MAP[selected_asset])]
    
    for name, ticker in targets:
        df_h = fetch_data(ticker, interval=htf, period="60d")
        df_l = fetch_data(ticker, interval=ltf, period="60d")
        res = analyze_smc_strategy(df_h, df_l, rr_ratio=rr_ratio, start_hour=start_h, end_hour=end_h)
        if not res.empty:
            res['symbol'] = name
            all_results.append(res)

    if all_results:
        df_all = pd.concat(all_results, ignore_index=True)
        df_filtered = df_all[(df_all['timestamp'] >= cutoff_date) & (df_all['ai_score'] >= min_ai)].copy()
    else:
        df_filtered = pd.DataFrame()

# 6. حساب الإحصائيات
if not df_filtered.empty:
    completed = df_filtered[df_filtered['status'].isin(['رابحة', 'خاسرة'])]
    total_count = len(completed)
    win_count = len(completed[completed['status'] == 'رابحة'])
    loss_count = len(completed[completed['status'] == 'خاسرة'])
    
    win_rate = round((win_count / total_count * 100), 2) if total_count > 0 else 0.0
    gross_profit = round(completed[completed['status'] == 'رابحة']['points'].sum(), 1)
    gross_loss = round(completed[completed['status'] == 'خاسرة']['points'].sum(), 1)
    net_points = round(gross_profit + gross_loss, 1)
    net_percent = round((win_count * risk_per_trade * rr_ratio) - (loss_count * risk_per_trade), 2)
else:
    total_count = win_count = loss_count = 0
    win_rate = gross_profit = gross_loss = net_points = net_percent = 0.0

# 7. عرض البطاقات الإحصائية (متناسقة تماماً مع شاشة الجوال)
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""
    <div class="stat-box box-purple">
        <div class="stat-label">🎯 نسبة النجاح</div>
        <div class="stat-number" style="color:#b388ff;">{win_rate}%</div>
        <div class="stat-sub">تقييم ذكاء اصطناعي ≥ {min_ai}%</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="stat-box box-blue">
        <div class="stat-label">📊 الصفقات المكتملة</div>
        <div class="stat-number" style="color:#40c4ff;">{total_count}</div>
        <div class="stat-sub">خلال {timeframe_view}</div>
    </div>
    """, unsafe_allow_html=True)

c3, c4 = st.columns(2)
with c3:
    st.markdown(f"""
    <div class="stat-box box-green">
        <div class="stat-label">✅ الصفقات الناجحة</div>
        <div class="stat-number" style="color:#00e676;">{win_count}</div>
        <div class="stat-sub">الأرباح: +{gross_profit} نقطة</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="stat-box box-red">
        <div class="stat-label">❌ الصفقات الخاسرة</div>
        <div class="stat-number" style="color:#ff5252;">{loss_count}</div>
        <div class="stat-sub">الخسائر: {gross_loss} نقطة</div>
    </div>
    """, unsafe_allow_html=True)

# بطاقة صافي الأرباح
net_color = "#00e676" if net_points >= 0 else "#ff5252"
net_sign = "+" if net_points > 0 else ""
st.markdown(f"""
<div class="box-net">
    <div class="stat-label">✨ صافي الأرباح ({timeframe_view})</div>
    <div class="stat-number" style="color:{net_color};">{net_sign}{net_points} نقطة</div>
    <div class="stat-sub" style="font-size:1rem; color:#ffffff;">نمو المحفظة: <b>{net_sign}{net_percent}%</b> (مخاطرة {risk_per_trade}% | عائد 1:{rr_ratio})</div>
</div>
""", unsafe_allow_html=True)

# 8. جدول التوصيات الأعلى تقييماً + الرسم البياني
if not df_filtered.empty:
    st.markdown('<h4 class="rtl-text">🔥 التوصيات الأعلى تقييماً بالذكاء الاصطناعي</h4>', unsafe_allow_html=True)
    top_recs = df_filtered.sort_values(by=['ai_score', 'timestamp'], ascending=[False, False]).head(15)
    
    display_df = top_recs[['timestamp', 'symbol', 'type', 'entry', 'sl', 'tp', 'ai_score', 'status', 'points']].copy()
    display_df.columns = ['التوقيت', 'العملة', 'النوع', 'الدخول', 'الوقف', 'الهدف', 'تقييم AI%', 'الحالة', 'النقاط']
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown('<h4 class="rtl-text">📈 منحنى نمو الأرباح التراكمي</h4>', unsafe_allow_html=True)
    df_chart = df_filtered.sort_values('timestamp').copy()
    df_chart['cumulative'] = df_chart['points'].cumsum()
    
    fig = px.area(df_chart, x='timestamp', y='cumulative', template="plotly_dark")
    fig.update_traces(line_color='#8c52ff', fillcolor='rgba(140, 82, 255, 0.25)')
    fig.update_layout(plot_bgcolor='#09090d', paper_bgcolor='#09090d', margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("اضغط على زر الفحص أعلاه أو اختر (الكل) من قائمة العملات لعرض جميع الفرص المكتشفة.")
