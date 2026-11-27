import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# إعدادات الصفحة
st.set_page_config(page_title="متتبع التداول الفوري المطور - RSI (1h)", layout="centered")

# تنسيق الواجهة باللغة العربية (RTL)
st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div[data-testid="stCheckbox"] { direction: rtl; text-align: right; }
    .profit-box-green {
        background-color: #0d3b1e;
        border: 2px solid #28a745;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
    .profit-box-red {
        background-color: #3b0d0d;
        border: 2px solid #dc3545;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
    .profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }
    .profit-amount-green { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }
    .profit-amount-red { color: #ff6b6b; font-size: 36px; font-weight: bold; direction: ltr; }
    .info-bar {
        color: #aaaaaa;
        font-size: 13px;
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

# قائمة بـ 22 عملة رقمية
COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", 
    "XLM-USD", "VET-USD", "HBAR-USD", "FIL-USD", "ICP-USD", 
    "APT-USD", "ARB-USD", "OP-USD", "RENDER-USD", "GRT-USD", 
    "TIA-USD", "SUI-USD"
]

# إعدادات إدارة المخاطر والاستراتيجية
TAKE_PROFIT_PCT = 0.06  # جني ربح تلقائي عند +6%
STOP_LOSS_PCT = 0.04    # وقف خسارة لحماية رأس المال عند -4%
RSI_BUY_LEVEL = 20      # مستوى اختراق الشراء
RSI_SELL_LEVEL = 70     # مستوى اختراق البيع (تم تعديله من 80 إلى 70)

# دالة حساب مؤشر RSI
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=900)
def run_scanner(trade_amount=100.0):
    trades_history = []
    current_opportunities = []

    for symbol in COINS:
        try:
            df = yf.download(symbol, period="45d", interval="1h", progress=False)
            if df.empty or len(df) < 20:
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df['RSI'] = calculate_rsi(df['Close'], period=14)
            df['Prev_RSI'] = df['RSI'].shift(1)
            df['Is_Green'] = df['Close'] > df['Open']

            # شرط الشراء: اختراق RSI لمستوى 20 صعوداً + شمعة صاعدة
            df['Buy_Signal'] = (df['Prev_RSI'] <= RSI_BUY_LEVEL) & (df['RSI'] > RSI_BUY_LEVEL) & df['Is_Green']
            
            # شرط البيع بالمؤشر: اختراق RSI لمستوى 70 صعوداً + شمعة صاعدة
            df['Sell_Signal'] = (df['Prev_RSI'] <= RSI_SELL_LEVEL) & (df['RSI'] > RSI_SELL_LEVEL) & df['Is_Green']

            # فحص الفرص الحالية (آخر شمعتين)
            last_2 = df.tail(2)
            if last_2['Buy_Signal'].any():
                last_price = float(df['Close'].iloc[-1])
                last_rsi = float(df['RSI'].iloc[-1])
                current_opportunities.append({
                    "العملة": symbol.replace("-USD", ""),
                    "السعر الحالي": round(last_price, 4),
                    "هدف الربح (+6%)": round(last_price * (1 + TAKE_PROFIT_PCT), 4),
                    "وقف الخسارة (-4%)": round(last_price * (1 - STOP_LOSS_PCT), 4),
                    "مؤشر RSI": round(last_rsi, 2),
                    "الوقت": str(df.index[-1])[:16]
                })

            # محاكاة الصفقات التاريخية (تداول فوري Spot)
            in_position = False
            buy_price = 0.0
            buy_time = None

            for idx, row in df.iterrows():
                current_close = float(row['Close'])
                current_high = float(row['High'])
                current_low = float(row['Low'])

                if not in_position and row['Buy_Signal']:
                    in_position = True
                    buy_price = current_close
                    buy_time = idx

                elif in_position:
                    tp_price = buy_price * (1 + TAKE_PROFIT_PCT)
                    sl_price = buy_price * (1 - STOP_LOSS_PCT)
                    sell_reason = None
                    sell_price = 0.0

                    # 1. التحقق من وقف الخسارة
                    if current_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = "وقف خسارة (-4%)"
                    # 2. التحقق من هدف الربح
                    elif current_high >= tp_price:
                        sell_price = tp_price
                        sell_reason = "جني ربح (+6%)"
                    # 3. التحقق من إشارة بيع RSI > 70
                    elif row['Sell_Signal']:
                        sell_price = current_close
                        sell_reason = "إشارة RSI > 70"

                    if sell_reason:
                        profit_pct = (sell_price - buy_price) / buy_price
                        profit_usd = trade_amount * profit_pct
                        trades_history.append({
                            "العملة": symbol.replace("-USD", ""),
                            "تاريخ الشراء": str(buy_time)[:16],
                            "سعر الشراء": round(buy_price, 4),
                            "تاريخ البيع": str(idx)[:16],
                            "سعر البيع": round(sell_price, 4),
                            "سبب الإغلاق": sell_reason,
                            "الربح ($)": round(profit_usd, 2),
                            "النسبة (%)": round(profit_pct * 100, 2)
                        })
                        in_position = False

        except Exception:
            continue

    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities)

# تشغيل الفحص بحجم صفقة 100$
trades_df, opps_df = run_scanner(trade_amount=100.0)

# تصفية الصفقات حسب الشهر الحالي والأسبوع الحالي
weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()

if not trades_df.empty:
    trades_df['تاريخ البيع_dt'] = pd.to_datetime(trades_df['تاريخ البيع'])
    now = pd.Timestamp.now(tz=trades_df['تاريخ البيع_dt'].dt.tz)
    
    # بداية الشهر الحالي
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_month]
    
    # بداية الأسبوع الحالي (الإثنين)
    start_of_week = (now - pd.Timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_week]
    weekly_profit = weekly_trades['الربح ($)'].sum()

# 1. صندوق الربح الصافي للأسبوع الحالي
box_class = "profit-box-green" if weekly_profit >= 0 else "profit-box-red"
amount_class = "profit-amount-green" if weekly_profit >= 0 else "profit-amount-red"
sign = "+" if weekly_profit > 0 else ""

st.markdown(f"""
    <div class="{box_class}">
        <div class="profit-title">الربح الصافي للأسبوع الحالي 💰</div>
        <div class="{amount_class}">{sign}{weekly_profit:.2f}$</div>
    </div>
""", unsafe_allow_html=True)

# 2. الخيارات التفاعلية
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
    st.markdown(f"""
    - **الإطار الزمني:** 1 ساعة (`1h`).
    - **نوع التداول:** فوري (`Spot`) بدون رافعة مالية.
    - **شرط الشراء:** اختراق RSI لمستوى `{RSI_BUY_LEVEL}` صعوداً مع شمعة صاعدة.
    - **شروط البيع (أيهما أسبق):** اختراق RSI لمستوى `{RSI_SELL_LEVEL}` صعوداً، أو جني ربح **`+{int(TAKE_PROFIT_PCT*100)}%`**، أو وقف خسارة **`-{int(STOP_LOSS_PCT*100)}%`**.
    - **حجم الصفقة للحساب:** `100$` لكل صفقة.
    """)

# 3. شريط المعلومات المختصر
st.markdown(f"""
    <div class="info-bar">
        العملات: {len(COINS)} | الشراء: RSI > {RSI_BUY_LEVEL} | البيع: RSI > {RSI_SELL_LEVEL} أو +6% | الفريم: 1h
    </div>
""", unsafe_allow_html=True)

# 4. قسم التوصيات المستقبلية (الفرص الحالية)
st.markdown("### 🎯 التوصيات المستقبلية (الفرص الحالية)")

if not opps_df.empty:
    st.success(f"تم العثور على {len(opps_df)} فرصة مطابقة للشروط!")
