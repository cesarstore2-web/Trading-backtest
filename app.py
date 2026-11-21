import streamlit as st
import pandas as pd
import plotly.express as px
from smc_engine import ASSETS_MAP, fetch_data, analyze_smc_strategy

# إعداد الصفحة
st.set_page_config(page_title="SMC AI Pro Trading", page_icon="⚡", layout="wide")

# تصميم CSS احترافي يتفوق على الصورة المرفقة
st.markdown("""
<style>
    @import url('https://googleapis.com');
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stApp { background-color: #09090d; color: #ffffff; }
    
    .stat-box {
        background: linear-gradient(145deg, #13131b, #191924);
        border-radius: 18px;
        padding: 20px;
        text-align: center;
        border: 1px solid #262636;
        box-shadow: 0 10px 25px rgba(0,0,0,0.45);
        margin-bottom: 14px;
    }
    .box-purple { border-top: 4px solid #8c52ff; }
    .box-blue { border-top: 4px solid #00b0ff; }
    .box-green { border-top: 4px solid #00e676; }
    .box-red { border-top: 4px solid #ff1744; }
    .box-net {
        background: linear-gradient(135deg, #161324, #22193d);
        border: 1px solid #7c4dff;
        border-radius: 20px;
        padding: 25px;
        text-align: center;
        margin-top: 5px;
        margin-bottom: 25px;
    }
    .stat-label { font-size: 1.05rem; color: #a5a5c0; font-weight: 600; }
    .stat-number { font-size: 2.5rem; font-weight: 900; margin: 6px 0; }
    .stat-sub { font-size: 0.85rem; color: #7a7a95; }
</style>
""", unsafe_allow_html=True)

# القائمة الجانبية للإعدادات القابلة للتعديل
with st.sidebar:
    st.header("⚙️ إعدادات استراتيجية SMC")
    htf = st.selectbox("فريم تحديد المناطق (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول والتأكيد (LTF):", ["15m", "5m"], index=0)
    rr_ratio = st.slider("نسبة العائد للمخاطرة (Risk : Reward):", 1.5, 5.0, 2.5, 0.5)
    risk_per_trade = st.number_input("نسبة المخاطرة لكل صفقة (%):", 0.5, 5.0, 1.0, 0.5)
    
    st.markdown("---")
    st.subheader("🕒 فلتر توقيت التداول (UTC)")
    start_h, end_h = st.slider("ساعات عمل الاستراتيجية:", 0, 23, (0, 23))
    
    st.markdown("---")
    st.subheader("🤖 فلتر الذكاء الاصطناعي")
    min_ai = st.slider("الحد الأدنى لتقييم التوصية (%):", 60, 95, 75)

# رأس الصفحة والفلاتر العلوية
st.title("⚡ نظام التداول الذكي (SMC + AI)")
st.caption("تتبع السيولة، الكسر الكاذب، وتأكيد CHoCH للعملات الرقمية والذهب")

col_f1, col_f2 = st.columns([1.2, 1])
with col_f1:
    timeframe_view = st.radio("سجل الأداء والنتائج:", ["شهري (30 يوم)", "أسبوعي (7 أيام)", "يومي (24 ساعة)"], horizontal=True)
with col_f2:
    selected_asset = st.selectbox("اختر العملة أو الذهب:", ["الكل"] + list(ASSETS_MAP.keys()))

# جلب البيانات وتحليلها
days_back = 30 if "شهري" in timeframe_view else (7 if "أسبوعي" in timeframe_view else 1)
cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_back)

with st.spinner("جاري فحص السيولة وتقييم التوصيات بالذكاء الاصطناعي..."):
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
        # تصفية حسب الفترة الزمنية وتقييم الذكاء الاصطناعي
        df_filtered = df_all[(df_all['timestamp'] >= cutoff_date) & (df_all['ai_score'] >= min_ai)].copy()
    else:
        df_filtered = pd.DataFrame()

# حساب الإحصائيات بدقة
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

# --- عرض البطاقات البصرية ---
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
        <div class="stat-label">📊 عدد الصفقات المكتملة</div>
        <div class="stat-number" style="color:#40c4ff;">{total_count}</div>
        <div class="stat-sub">صفقات خلال الفترة المحددة</div>
    </div>
    """, unsafe_allow_html=True)

c3, c4 = st.columns(2)
with c3:
    st.markdown(f"""
    <div class="stat-box box-green">
        <div class="stat-label">✅ الصفقات الناجحة</div>
        <div class="stat-number" style="color:#00e676;">{win_count}</div>
        <div class="stat-sub">إجمالي الأرباح: +{gross_profit} نقطة</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="stat-box box-red">
        <div class="stat-label">❌ الصفقات الخاسرة</div>
        <div class="stat-number" style="color:#ff5252;">{loss_count}</div>
        <div class="stat-sub">إجمالي الخسائر: {gross_loss} نقطة</div>
    </div>
    """, unsafe_allow_html=True)

# بطاقة صافي الأرباح
net_color = "#00e676" if net_points >= 0 else "#ff5252"
net_sign = "+" if net_points > 0 else ""
st.markdown(f"""
<div class="box-net">
    <div class="stat-label">✨ صافي الأرباح ({timeframe_view})</div>
    <div class="stat-number" style="color:{net_color};">{net_sign}{net_points} نقطة &nbsp;|&nbsp; ({net_sign}{net_percent}% للمحفظة)</div>
    <div class="stat-sub">بناءً على مخاطرة {risk_per_trade}% وعائد 1:{rr_ratio}</div>
</div>
""", unsafe_allow_html=True)

# --- الرسوم البيانية وجدول التوصيات الأعلى تقييماً ---
if not df_filtered.empty:
    st.subheader("📈 منحنى نمو الأرباح التراكمي")
    df_chart = df_filtered.sort_values('timestamp').copy()
    df_chart['cumulative'] = df_chart['points'].cumsum()
    
    fig = px.area(
        df_chart, x='timestamp', y='cumulative',
        labels={'timestamp': 'التوقيت', 'cumulative': 'صافي النقاط'},
        template="plotly_dark"
    )
    fig.update_traces(line_color='#8c52ff', fillcolor='rgba(140, 82, 255, 0.25)')
    fig.update_layout(plot_bgcolor='#09090d', paper_bgcolor='#09090d')
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🔥 التوصيات الأعلى تقييماً بالذكاء الاصطناعي")
    top_recs = df_filtered.sort_values(by=['ai_score', 'timestamp'], ascending=[False, False]).head(15)
    
    # تنسيق الجدول للعرض
    display_df = top_recs[['timestamp', 'symbol', 'type', 'entry', 'sl', 'tp', 'ai_score', 'status', 'points']].copy()
    display_df.columns = ['التوقيت', 'الأصل', 'النوع', 'نقطة الدخول', 'وقف الخسارة', 'الهدف', 'تقييم AI %', 'الحالة', 'النقاط']
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.warning("لا توجد صفقات مطابقة للشروط في هذه الفترة. جرب خفض الحد الأدنى لتقييم الذكاء الاصطناعي من القائمة الجانبية.")
