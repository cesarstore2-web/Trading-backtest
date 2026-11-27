import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="متتبع التداول الفوري المرن - RSI", layout="centered")

css = (
    "<style>"
    ".main { direction: rtl; text-align: right; }"
    "div[data-testid='stCheckbox'] { direction: rtl; text-align: right; }"
    "div[data-testid='stSelectbox'], div[data-testid='stNumberInput'] { direction: rtl; text-align: right; }"
    ".profit-box-green { background-color: #0d3b1e; border: 2px solid #28a745; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-box-red { background-color: #3b0d0d; border: 2px solid #dc3545; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }"
    ".profit-amount-green { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".profit-amount-red { color: #ff6b6b; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".info-bar { color: #aaaaaa; font-size: 13px; text-align: center; margin: 15px 0; padding: 8px; background-color: #1e1e1e; border-radius: 8px; }"
    ".alert-box { background-color: #162436; border: 1px solid #2b4c7e; border-radius: 10px; padding: 15px; text-align: center; color: #90caf9; }"
    "</style>"
)
st.markdown(css, unsafe_allow_html=True)

COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", 
    "XLM-USD", "VET-USD", "HBAR-USD", "FIL-USD", "ICP-USD", 
    "APT-USD", "ARB-USD", "OP-USD", "RENDER-USD", "GRT-USD", 
    "TIA-USD", "SUI-USD"
]

if 'rsi_buy' not in st.session_state:
    st.session_state.rsi_buy = 15
if 'rsi_sell' not in st.session_state:
    st.session_state.rsi_sell = 50
if 'tp_pct' not in st.session_state:
    st.session_state.tp_pct = 2.5
if 'rsi_period' not in st.session_state:
    st.session_state.rsi_period = 14
if 'trade_amount' not in st.session_state:
    st.session_state.trade_amount = 100.0

TIMEFRAME_OPTIONS = {
    "5 دقائق (5m)": ("5m", "35d"),
    "15 دقيقة (15m)": ("15m", "35d"),
    "30 دقيقة (30m)": ("30m", "35d"),
    "1 ساعة (1h)": ("1h", "45d"),
    "4 ساعات (4h)": ("4h", "60d"),
    "يومي (1d)": ("1d", "180d")
}

selected_tf_label = st.selectbox(
    "⏱️ اختر الإطار الزمني للتداول:",
    options=list(TIMEFRAME_OPTIONS.keys()),
    index=0
)
TIMEFRAME, DATA_PERIOD = TIMEFRAME_OPTIONS[selected_tf_label]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=180)
def run_scanner(timeframe, period_str, rsi_buy, rsi_sell, tp_pct, rsi_period, trade_amount):
    trades_history = []
    current_opportunities = []
    tp_decimal = tp_pct / 100.0

    for symbol in COINS:
        try:
            df = yf.download(symbol, period=period_str, interval=timeframe, progress=False)
            if df.empty or len(df) < rsi_period + 5:
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df['RSI'] = calculate_rsi(df['Close'], period=rsi_period)
            df['Prev_RSI'] = df['RSI'].shift(1)
            df['Is_Green'] = df['Close'] > df['Open']

            df['Buy_Signal'] = (df['Prev_RSI'] <= rsi_buy) & (df['RSI'] > rsi_buy) & df['Is_Green']
            df['Sell_Signal'] = (df['Prev_RSI'] <= rsi_sell) & (df['RSI'] > rsi_sell) & df['Is_Green']

            last_2 = df.tail(2)
            if last_2['Buy_Signal'].any():
                last_price = float(df['Close'].iloc[-1])
                last_rsi = float(df['RSI'].iloc[-1])
                opp_data = {
                    "العملة": symbol.replace("-USD", ""),
                    "السعر الحالي": round(last_price, 4),
                    "مؤشر RSI": round(last_rsi, 2),
                    "الوقت": str(df.index[-1])[:16]
                }
                if tp_pct > 0:
                    opp_data[f"هدف الربح (+{tp_pct}%)"] = round(last_price * (1 + tp_decimal), 4)
                current_opportunities.append(opp_data)

            in_position = False
            buy_price = 0.0
            buy_time = None

            for idx, row in df.iterrows():
                current_close = float(row['Close'])
                current_high = float(row['High'])

                if not in_position and row['Buy_Signal']:
                    in_position = True
                    buy_price = current_close
                    buy_time = idx

                elif in_position:
                    sell_reason = None
                    sell_price = 0.0

                    if tp_pct > 0 and current_high >= buy_price * (1 + tp_decimal):
                        sell_price = buy_price * (1 + tp_decimal)
                        sell_reason = f"جني ربح (+{tp_pct}%)"
                    elif row['Sell_Signal']:
                        sell_price = current_close
                        sell_reason = f"إشارة RSI > {rsi_sell}"

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

trades_df, opps_df = run_scanner(
    TIMEFRAME,
    DATA_PERIOD,
    st.session_state.rsi_buy,
    st.session_state.rsi_sell,
    st.session_state.tp_pct,
    st.session_state.rsi_period,
    st.session_state.trade_amount
)

weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()

if not trades_df.empty:
    trades_df['تاريخ البيع_dt'] = pd.to_datetime(trades_df['تاريخ البيع'])
    now = pd.Timestamp.now(tz=trades_df['تاريخ البيع_dt'].dt.tz)
    
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_month]
    
    start_of_week = (now - pd.Timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_trades = trades_df[trades_df['تاريخ البيع_dt'] >= start_of_week]
    weekly_profit = weekly_trades['الربح ($)'].sum()

box_class = "profit-box-green" if weekly_profit >= 0 else "profit-box-red"
amount_class = "profit-amount-green" if weekly_profit >= 0 else "profit-amount-red"
sign = "+" if weekly_profit > 0 else ""

profit_html = f'<div class="{box_class}"><div class="profit-title">الربح الصافي للأسبوع الحالي 💰</div><div class="{amount_class}">{sign}{weekly_profit:.2f}$</div></div>'
st.markdown(profit_html, unsafe_allow_html=True)

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
        st.metric(f"إجمالي ربح الشهر الحالي (بحجم صفقة {st.session_state.trade_amount}$)", f"{total_month:.2f}$")
        
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
    st.markdown("#### 🛠️ تعديل قيم الاستراتيجية")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.rsi_buy = st.number_input("مستوى شراء RSI:", min_value=1, max_value=50, value=st.session_state.rsi_buy, step=1)
        st.session_state.tp_pct = st.number_input("نسبة جني الربح % (0 للإلغاء):", min_value=0.0, max_value=100.0, value=st.session_state.tp_pct, step=0.5)
    with col2:
        st.session_state.rsi_sell = st.number_input("مستوى بيع RSI:", min_value=20, max_value=95, value=st.session_state.rsi_sell, step=1)
        st.session_state.trade_amount = st.number_input("مبلغ الصفقة ($):", min_value=10.0, max_value=100000.0, value=st.session_state.trade_amount, step=10.0)
    st.session_state.rsi_period = st.number_input("فترة مؤشر RSI:", min_value=2, max_value=50, value=st.session_state.rsi_period, step=1)
    st.caption("التداول فوري (Spot) بدون وقف خسارة، ويتم تحديث النتائج تلقائياً عند تغيير أي رقم.")

tp_text = f" أو +{st.session_state.tp_pct}%" if st.session_state.tp_pct > 0 else ""
