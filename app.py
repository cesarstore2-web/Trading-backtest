import streamlit as st
import pandas as pd
import plotly.express as px
from smc_engine import ASSETS_MAP, fetch_data, analyze_smc_strategy

st.set_page_config(
    page_title="SMC AI Pro Trading ($)",
    page_icon="💵",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://googleapis.com');
    
    .stApp {
        background-color: #09090d;
        color: #ffffff;
        font-family: 'Cairo', sans-serif;
    }
    .rtl-text {
        direction: rtl;
        text-align: right;
        font-family: 'Cairo', sans-serif;
    }
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
    }
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
    .stat-number { font-size: 2.1rem; font-weight: 900; margin: 5px 0; }
    .stat-sub { font-size: 0.85rem; color: #9a9ab5; }
</style>
""", unsafe_allow_html=True)

# القائمة الجانبية للإعدادات وإدارة رأس المال
with st.sidebar:
    st.markdown('<h3 class="rtl-text">💰 إدارة رأس المال والإعدادات</h3>', unsafe_allow_html=True)
    capital = st.number_input("رأس مال المحفظة ($ USD):", min_value=100.0, max_value=1000000.0, value=1000.0, step=100.0)
    risk_per_trade = st.number_input("نسبة المخاطرة لكل صفقة (%):", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
    rr_ratio = st.slider("نسبة العائد للمخاطرة (Risk : Reward):", 1.5, 5.0, 2.0, 0.5)
    
    st.markdown("---")
    htf = st.selectbox("فريم تحديد المناطق (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول والتأكيد (LTF):", ["15m", "5m"], index=0)
    start_h, end_h = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI (%):", 55, 95, 65)

st.markdown("""
<div class="rtl-text">
    <h2 style="margin-bottom:0;">⚡ نظام التداول الذكي (SMC + AI)</h2>
    <p style="color:#9e9eb8; font-size:0.95rem;">تتبع السيولة، الكسر الكاذب، وتأكيد CHoCH بالدولار الأمريكي ($)</p>
</div>
""", unsafe_allow_html=True)

# الفلاتر الرئيسية
col1, col2 = st.columns(2)
with col1:
    timeframe_view = st.selectbox("📅 سجل الأداء والنتائج:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with col2:
    selected_asset = st.selectbox("🪙 اختر العملة أو الذهب:", ["الكل"] + list(ASSETS_MAP.keys()))

st.button("🔍 فحص والبحث عن توصيات الآن")

days_back = 30 if "شهري" in timeframe_view else 7
cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_back)

with st.spinner("جاري فحص السيولة وحساب الأرباح بالدولار الأمريكي..."):
    all_results = []
    targets = ASSETS_MAP.items() if selected_asset == "الكل" else [(selected_asset, ASSETS_MAP[selected_asset])]
    
    for name, ticker in targets:
        df_h = fetch_data(ticker, interval=htf, period="60d")
        df_l = fetch_data(ticker, interval=ltf, period="60d")
        res = analyze_smc_strategy(
            df_h, df_l, rr_ratio=rr_ratio, start_hour=start_h, end_hour=end_h,
            capital=capital, risk_pct=risk_per_trade
        )
        if not res.empty:
            res['symbol'] = name
            all_results.append(res)

    if all_results:
        df_all = pd.concat(all_results, ignore_index=True)
        df_filtered = df_all[(df_all['timestamp'] >= cutoff_date) & (df_all['ai_score'] >= min_ai)].copy()
    else:
        df_filtered = pd.DataFrame()

# حساب الإحصائيات بالدولار الأمريكي
if not df_filtered.empty:
    completed = df_filtered[df_filtered['status'].isin(['رابحة', 'خاسرة'])]
    total_count = len(completed)
    win_count = len(completed[completed['status'] == 'رابحة'])
    loss_count = len(completed[completed['status'] == 'خاسرة'])
    
    win_rate = round((win_count / total_count * 100), 2) if total_count > 0 else 0.0
    gross_profit_usd = round(completed[completed['status'] == 'رابحة']['pnl_usd'].sum(), 2)
    gross_loss_usd = round(completed[completed['status'] == 'خاسرة']['pnl_usd'].sum(), 2)
    net_profit_usd = round(gross_profit_usd + gross_loss_usd, 2)
    net_percent = round((net_profit_usd / capital) * 100, 2)
else:
    total_count = win_count = loss_count = 0
    win_rate = gross_profit_usd = gross_loss_usd = net_profit_usd = net_percent = 0.0

# عرض البطاقات الإحصائية
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
        <div class="stat-sub">إجمالي الأرباح: <b>+${gross_profit_usd}</b></div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="stat-box box-red">
        <div class="stat-label">❌ الصفقات الخاسرة</div>
        <div class="stat-number" style="color:#ff5252;">{loss_count}</div>
        <div class="stat-sub">إجمالي الخسائر: <b>${gross_loss_usd}</b></div>
    </div>
    """, unsafe_allow_html=True)

# بطاقة صافي الأرباح بالدولار الأمريكي
net_color = "#00e676" if net_profit_usd >= 0 else "#ff5252"
net_sign = "+" if net_profit_usd > 0 else ""
st.markdown(f"""
<div class="box-net">
    <div class="stat-label">💵 صافي الأرباح بالدولار ({timeframe_view})</div>
    <div class="stat-number" style="color:{net_color};">{net_sign}${net_profit_usd} USD</div>
    <div class="stat-sub" style="font-size:0.95rem; color:#ffffff;">
        رأس المال: <b>${capital:,.0f}</b> &nbsp;|&nbsp; العائد: <b>{net_sign}{net_percent}%</b> (مخاطرة {risk_per_trade}% = ${capital*(risk_per_trade/100):.1f})
    </div>
</div>
""", unsafe_allow_html=True)

# جدول التوصيات الأعلى تقييماً بالدولار الأمريكي
if not df_filtered.empty:
    st.markdown('<h4 class="rtl-text">🔥 التوصيات الأعلى تقييماً بالذكاء الاصطناعي ($)</h4>', unsafe_allow_html=True)
    top_recs = df_filtered.sort_values(by=['ai_score', 'timestamp'], ascending=[False, False]).head(15)
    
    display_df = top_recs[['timestamp', 'symbol', 'type', 'entry', 'sl', 'tp', 'ai_score', 'status', 'pnl_usd']].copy()
    display_df['entry'] = display_df['entry'].apply(lambda x: f"${x}")
    display_df['sl'] = display_df['sl'].apply(lambda x: f"${x}")
    display_df['tp'] = display_df['tp'].apply(lambda x: f"${x}")
    display_df['pnl_usd'] = display_df['pnl_usd'].apply(lambda x: f"+${x}" if x > 0 else (f"-${abs(x)}" if x < 0 else "$0.0"))
    
    display_df.columns = ['التوقيت', 'العملة/الذهب', 'النوع', 'سعر الدخول ($)', 'وقف الخسارة ($)', 'الهدف ($)', 'تقييم AI%', 'الحالة', 'الربح/الخسارة ($)']
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown('<h4 class="rtl-text">📈 منحنى نمو المحفظة بالدولار ($)</h4>', unsafe_allow_html=True)
    df_chart = df_filtered.sort_values('timestamp').copy()
    df_chart['cumulative_usd'] = capital + df_chart['pnl_usd'].cumsum()
    
    fig = px.area(df_chart, x='timestamp', y='cumulative_usd', labels={'timestamp': 'التوقيت', 'cumulative_usd': 'رصيد المحفظة ($)'}, template="plotly_dark")
    fig.update_traces(line_color='#00e676', fillcolor='rgba(0, 230, 118, 0.2)')
    fig.update_layout(plot_bgcolor='#09090d', paper_bgcolor='#09090d', margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("اضغط على زر الفحص أعلاه أو اختر (الكل) من قائمة العملات لعرض جميع التوصيات والأرباح بالدولار.")
