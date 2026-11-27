import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="متتبع التداول الفوري - RSI (1h)", layout="centered")

# تنسيق الواجهة باللغة العربية (RTL) وتصميم الصناديق
st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stCheckbox"] { direction: rtl; text-align: right; }
    .profit-box {
        background-color: #0d3b1e;
        border: 2px solid #28a745;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
    .profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }
    .profit-amount { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }
    .info-bar {
        color: #aaaaaa;
        font-size: 14px;
        text-align: center;
        margin: 15px 0;
        padding: 8px;
        background-color: #1e1e1e;
        border-radius: 8px;
    }
    .alert-box {
        background-color: #162436;
        border: 1px solid #2b4c7e;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        color: #90caf9;
    }
    </style>
""", unsafe_allow_html=True)

# قائمة بـ 22 عملة رقمية (رموز Yahoo Finance)
COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", 
    "XLM-USD", "VET-USD", "HBAR-USD", "FIL-USD", "ICP-USD", 
    "APT-USD", "ARB-USD", "OP-USD", "RENDER-USD", "GRT-USD", 
    "TIA-USD", "SUI-USD"
]

# دالة حساب مؤشر RSI (فترة 14)
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# جلب البيانات وتطبيق الاستراتيجية على الإطار الزمني 1 ساعة
@st.cache_data(ttl=900) # تحديث البيانات تلقائياً كل 15 دقيقة
def run_scanner(trade_amount=100.0):
    trades_history = []
    current_opportunities = []

    for symbol in COINS:
        try:
            # جلب بيانات 45 يوماً على فريم 1 ساعة (1h)
            df = yf.download(symbol, period="45d", interval="1h", progress=False)
            if df.empty or len(df) < 20:
                continue
            
            # توحيد أسماء الأعمدة
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df['RSI'] = calculate_rsi(df['Close'], period=14)
            df['Prev_RSI'] = df['RSI'].shift(1)
            df['Is_Green'] = df['Close'] > df['Open'] # شمعة صاعدة

            # شرط الشراء: RSI يخترق مستوى 20 صعوداً + شمعة صاعدة
            df['Buy_Signal'] = (df['Prev_RSI'] <= 20) & (df['RSI'] > 20) & df['Is_Green']
            
            # شرط البيع: RSI يخترق مستوى 80 صعوداً + شمعة صاعدة
            df['Sell_Signal'] = (df['Prev_RSI'] <= 80) & (df['RSI'] > 80) & df['Is_Green']

            # فحص الفرص الحالية (في الشمعة الحالية أو السابقة)
            last_2 = df.tail(2)
            if last_2['Buy_Signal'].any():
                last_price = df['Close'].iloc[-1]
                last_rsi = df['RSI'].iloc[-1]
                current_opportunities.append({
                    "العملة": symbol.replace("-USD", ""),
                    "السعر الحالي": round(float(last_price), 4),
                    "مؤشر RSI": round(float(last_rsi), 2),
                    "الوقت": str(df.index[-1])[:16]
                })

            # محاكاة الصفقات التاريخية (تداول فوري Spot)
            in_position = False
            buy_price = 0.0
            buy_time = None

            for idx, row in df.iterrows():
                if not in_position and row['Buy_Signal']:
                    in_position = True
                    buy_price = float(row['Close'])
                    buy_time = idx
                elif in_position and row['Sell_Signal']:
                    sell_price = float(row['Close'])
                    profit_pct = (sell_price - buy_price) / buy_price
                    profit_usd = trade_amount * profit_pct
                    trades_history.append({
                        "العملة": symbol.replace("-USD", ""),
                        "تاريخ الشراء": str(buy_time)[:16],
                        "سعر الشراء": round(buy_price, 4),
                        "تاريخ البيع": str(idx)[:16],
                        "سعر البيع": round(sell_price, 4),
                        "الربح ($)": round(profit_usd, 2),
                        "النسبة (%)": round(profit_pct * 100, 2)
                    })
                    in_position = False

        except Exception:
            continue

    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities)

# تشغيل الفحص بحجم صفقة افتراضي 100 دولار
trades_df, opps_df = run_scanner(trade_amount=100.0)

# تصفية الصفقات حسب الشهر الحالي والأسبوع الحالي
weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()

if not trades_df.empty:
    trades_df['تاريخ البيع_dt'] = pd.to_datetime(trades_df['تاريخ البيع'])
    now = pd.Timestamp.now(tz=trades_df['تاريخ البيع_dt'].dt.tz)
    
    # بداية الشهر الحالي (اليوم الأول في الشهر الساعة 00:00)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_month]
    
    # بداية الأسبوع الحالي (يوم الإثنين)
    start_of_week = (now - pd.Timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_week]
    weekly_profit = weekly_trades['الربح ($)'].sum()

# 1. صندوق الربح الصافي للأسبوع الحالي
sign = "+" if weekly_profit >= 0 else ""
st.markdown(f"""
    <div class="profit-box">
        <div class="profit-title">الربح الصافي للأسبوع الحالي 💰</div>
        <div class="profit-amount">{sign}{weekly_profit:.2f}$</div>
    </div>
""", unsafe_allow_html=True)

# 2. الخيارات التفاعلية (Checkboxes)
if st.checkbox("🔥 إظهار ملخص الأداء للأسبوع الحالي"):
    if not weekly_trades.empty:
        st.write(f"عدد الصفقات المغلقة هذا الأسبوع: **{len(weekly_trades)}**")
        st.dataframe(weekly_trades.drop(columns=['تاريخ البيع_dt']), use_container_width=True)
    else:
        st.info("لا توجد صفقات مغلقة خلال الأسبوع الحالي.")

if st.checkbox("📋 إظهار تفاصيل الصفقات"):
    if not current_month_trades.empty:
        st.dataframe(current_month_trades.drop(columns=['تاريخ البيع_dt']), use_container_width=True)
    else:
        st.info("لم يتم تسجيل صفقات مكتملة خلال الشهر الحالي.")

if st.checkbox("📅 إظهار سجل 4 أسابيع (الشهر الحالي)"):
    if not current_month_trades.empty:
        total_month = current_month_trades['الربح ($)'].sum()
        st.metric("إجمالي ربح الشهر الحالي (بحجم صفقة 100$)", f"{total_month:.2f}$")
        
        # تقسيم أرباح الشهر الحالي حسب الأسابيع
        cm_copy = current_month_trades.copy()
        cm_copy['الأسبوع'] = "الأسبوع " + ((cm_copy['تاريخ البيع_dt'].dt.day - 1) // 7 + 1).astype(str)
        weekly_summary = cm_copy.groupby('الأسبوع', as_index=False).agg(
            عدد_الصفقات=('العملة', 'count'),
            إجمالي_الربح=('الربح ($)', 'sum')
        )
        st.dataframe(weekly_summary, use_container_width=True)
    else:
        st.info("لا توجد صفقات مغلقة في الشهر الحالي حتى الآن.")

if st.checkbox("⚙️ إظهار إعدادات الاستراتيجية"):
    st.markdown("""
    - **الإطار الزمني:** 1 ساعة (`1h`).
    - **نوع التداول:** فوري (`Spot`) بدون رافعة مالية.
    - **شرط الشراء:** اختراق RSI لمستوى `20` صعوداً مع إغلاق شمعة صاعدة.
    - **شرط البيع:** اختراق RSI لمستوى `80` صعوداً مع إغلاق شمعة صاعدة.
    - **حجم الصفقة الافتراضي للحساب:** `100$` لكل صفقة.
    """)

# 3. شريط المعلومات المختصر
st.markdown(f"""
    <div class="info-bar">
        العملات: {len(COINS)} | الشراء: RSI > 20 | البيع: RSI > 80 | الفريم: 1h
    </div>
""", unsafe_allow_html=True)

# 4. قسم التوصيات المستقبلية (الفرص الحالية)
st.markdown("### 🎯 التوصيات المستقبلية (الفرص الحالية)")

if not opps_df.empty:
    st.success(f"تم العثور على {len(opps_df)} فرصة مطابقة للشروط!")
    st.dataframe(opps_df, use_container_width=True)
else:
    st.markdown("""
        <div class="alert-box">
            لا توجد فرص مطابقة للشروط في الشمعة الحالية أو السابقة.
        </div>
    """, unsafe_allow_html=True)
