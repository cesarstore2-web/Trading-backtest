import streamlit as st
import pandas as pd
from smc_engine import ASSETS_MAP, fetch_data, analyze_smc_strategy

st.set_page_config(
    page_title="Whale SMC AI Pro ($)",
    page_icon="🐋",
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
    .rec-card {
        background: linear-gradient(145deg, #14141f, #1c1c2b);
        border-right: 5px solid #00e676;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 12px;
        direction: rtl;
        text-align: right;
        box-shadow: 0 6px 16px rgba(0,0,0,0.35);
    }
    .rec-sell { border-right-color: #ff1744; }
    .stat-label { font-size: 1rem; color: #a5a5c0; font-weight: 700; }
    .stat-number { font-size: 2.1rem; font-weight: 900; margin: 5px 0; }
    .stat-sub { font-size: 0.85rem; color: #9a9ab5; }
</style>
""", unsafe_allow_html=True)

# القائمة الجانبية لإدارة رأس المال والإعدادات
with st.sidebar:
    st.markdown('<h3 class="rtl-text">💰 إدارة رأس المال والإعدادات</h3>', unsafe_allow_html=True)
    capital = st.number_input("رأس مال المحفظة ($ USD):", min_value=100.0, max_value=1000000.0, value=1000.0, step=100.0)
    risk_per_trade = st.number_input("نسبة المخاطرة لكل صفقة (%):", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
    rr_ratio = st.slider("نسبة العائد للمخاطرة (Risk : Reward):", 1.5, 5.0, 2.0, 0.5)
    
    st.markdown("---")
    htf = st.selectbox("فريم تحديد المناطق (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول والتأكيد (LTF):", ["15m", "5m"], index=0)
    start_h, end_h = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI (%):", 65, 95, 75)

st.markdown("""
<div class="rtl-text">
    <h2 style="margin-bottom:0;">🐋 نظام تتبع سيولة الحيتان (SMC + FVG + AI)</h2>
    <p style="color:#9e9eb8; font-size:0.95rem;">أقوى 3 توصيات مؤسسية بالدولار الأمريكي ($)</p>
</div>
""", unsafe_allow_html=True)

# الفلاتر الرئيسية
col1, col2 = st.columns(2)
with col1:
    timeframe_view = st.selectbox("📅 سجل الأداء والنتائج:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with col2:
    selected_asset = st.selectbox("🪙 اختر العملة أو الذهب:", ["الكل"] + list(ASSETS_MAP.keys()))

st.button("🔍 فحص والبحث عن أعلى 3 توصيات")

days_back = 30 if "شهري" in timeframe_view else 7
cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_back)

with st.spinner("جاري تتبع بصمة الحيتان وفجوات القيمة العادلة (FVG)..."):
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
    win_count = len(df_filtered[df_filtered['status'] == 'رابحة'])
    loss_count = len(df_filtered[df_filtered['status'] == 'خاسرة'])
    be_count = len(df_filtered[df_filtered['status'].str.contains('مؤمّنة')])
    total_count = win_count + loss_count + be_count
    
    decisive_trades = win_count + loss_count
    win_rate = round((win_count / decisive_trades * 100), 2) if decisive_trades > 0 else 0.0
    
    gross_profit_usd = round(df_filtered[df_filtered['status'] == 'رابحة']['pnl_usd'].sum(), 2)
    gross_loss_usd = round(df_filtered[df_filtered['status'] == 'خاسرة']['pnl_usd'].sum(), 2)
    net_profit_usd = round(gross_profit_usd + gross_loss_usd, 2)
    net_percent = round((net_profit_usd / capital) * 100, 2)
else:
    total_count = win_count = loss_count = be_count = 0
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
        <div class="stat-sub">منها {be_count} صفقة مؤمّنة على الدخول</div>
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

# عرض أعلى 3 توصيات فقط
if not df_filtered.empty:
    st.markdown('<h3 class="rtl-text">🏆 أعلى 3 توصيات تقييماً بالذكاء الاصطناعي</h3>', unsafe_allow_html=True)
    top_3 = df_filtered.sort_values(by=['ai_score', 'timestamp'], ascending=[False, False]).head(3)
    
    for idx, row in top_3.iterrows():
        is_sell = "بيع" in row['type']
        card_class = "rec-card rec-sell" if is_sell else "rec-card"
        type_color = "#ff5252" if is_sell else "#00e676"
        pnl_val = row['pnl_usd']
        pnl_str = f"+${pnl_val}" if pnl_val > 0 else (f"-${abs(pnl_val)}" if pnl_val < 0 else ("$0.0 (مؤمّنة)" if "مؤمّنة" in row['status'] else "جارية الآن ⏳"))
        pnl_color = "#00e676" if pnl_val > 0 else ("#ff5252" if pnl_val < 0 else "#ffd740")

        st.markdown(f"""
        <div class="{card_class}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:1.2rem; font-weight:900; color:#ffffff;">🪙 {row['symbol']} &nbsp;|&nbsp; <span style="color:{type_color};">{row['type']}</span></span>
                <span style="background:#2a2245; color:#b388ff; padding:4px 12px; border-radius:20px; font-weight:800; font-size:0.85rem;">🤖 AI: {row['ai_score']}%</span>
            </div>
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; font-size:0.95rem; color:#d0d0e0; margin-bottom:8px;">
                <span>🎯 <b>الدخول:</b> ${row['entry']}</span>
                <span>🛑 <b>الوقف:</b> ${row['sl']}</span>
                <span>💰 <b>الهدف:</b> ${row['tp']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; font-size:0.82rem; color:#8e8ea8; border-top:1px solid #28283a; padding-top:8px;">
                <span>🕒 {row['timestamp'].strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; 📌 {row['fvg_tag']}</span>
                <span style="font-weight:800; color:{pnl_color};">النتيجة: {row['status']} ({pnl_str})</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("لا توجد توصيات مطابقة لشروط السيولة المؤسسية حالياً. جرب اختيار (الكل) من قائمة العملات.")
