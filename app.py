import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="محلل موجات إليوت - Spot", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #131316; color: #ffffff; direction: rtl; }
    .metric-card {
        background-color: #1c1c21;
        border-radius: 10px;
        padding: 12px 15px;
        margin-bottom: 10px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .card-purple { border: 1.5px solid #7c4dff; }
    .card-green  { border: 1.5px solid #2e7d32; }
    .card-red    { border: 1.5px solid #c62828; }
    .card-title-purple { color: #9e7bff; font-size: 13px; margin-bottom: 4px; }
    .card-title-green  { color: #4caf50; font-size: 13px; margin-bottom: 4px; }
    .card-title-red    { color: #ef5350; font-size: 13px; margin-bottom: 4px; }
    .card-value { color: #ffffff; font-size: 22px; font-weight: bold; margin: 2px 0; }
    .card-sub   { color: #8e8e93; font-size: 11px; }
    .rec-box {
        background-color: #1c1c21;
        border: 1px solid #33333d;
        border-radius: 10px;
        padding: 15px;
        margin-top: 15px;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align: center; color: #fff;'>📊 نظام موجات إليوت (Spot - شراء فقط)</h3>", unsafe_allow_html=True)

col_in1, col_in2, col_in3 = st.columns(3)
with col_in1:
    symbol = st.text_input("الرمز (Symbol)", value="BTC-USD")
with col_in2:
    period = st.selectbox("الفترة التاريخية", ["1mo", "3mo", "6mo", "1y"], index=1)
with col_in3:
    capital = st.number_input("رأس المال للصفقة ($)", min_value=10.0, value=100.0, step=10.0)

@st.cache_data(ttl=300)
def load_data(ticker, per):
    df = yf.download(ticker, period=per, interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

df = load_data(symbol, period)

if df.empty or len(df) < 20:
    st.error("تعذر جلب بيانات كافية لهذا الرمز.")
    st.stop()
window_size = 30
winning_trades, losing_trades = 0, 0
total_profit, total_loss = 0.0, 0.0
trades_log = []

for i in range(0, len(df) - window_size, window_size):
    sub_df = df.iloc[i : i + window_size]
    mid = len(sub_df) // 2
    wave_0 = float(sub_df.iloc[:mid]['Low'].min())
    wave_1 = float(sub_df.iloc[mid:]['High'].max())
    
    if wave_1 > wave_0:
        diff = wave_1 - wave_0
        entry_2 = wave_1 - (diff * 0.618)
        target_5 = wave_0 + (diff * 1.618)
        stop_loss_0 = wave_0
        
        future_df = df.iloc[i + window_size : i + (window_size * 2)]
        entered = False
        for date, row in future_df.iterrows():
            low_p, high_p = float(row['Low']), float(row['High'])
            if not entered and low_p <= entry_2:
                entered = True
                continue
            if entered:
                if low_p <= stop_loss_0:
                    loss_usd = capital * ((entry_2 - stop_loss_0) / entry_2)
                    losing_trades += 1
                    total_loss += loss_usd
                    trades_log.append({"التاريخ": date.strftime('%Y-%m-%d'), "الحالة": "خاسرة ❌", "الدخول": round(entry_2, 2), "الإغلاق": round(stop_loss_0, 2), "النتيجة ($)": f"-${loss_usd:.2f}"})
                    break
                elif high_p >= target_5:
                    profit_usd = capital * ((target_5 - entry_2) / entry_2)
                    winning_trades += 1
                    total_profit += profit_usd
                    trades_log.append({"التاريخ": date.strftime('%Y-%m-%d'), "الحالة": "رابحة ✅", "الدخول": round(entry_2, 2), "الإغلاق": round(target_5, 2), "النتيجة ($)": f"+${profit_usd:.2f}"})
                    break

total_trades = winning_trades + losing_trades
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

st.markdown(f"<div class='metric-card card-purple'><div class='card-value'>{win_rate:.1f}%</div><div class='card-title-purple'>معدل الأداء</div></div>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title-green'>📈 الصفقات الرابحة</div><div class='card-value'>{winning_trades}</div><div class='card-sub'>صفقات</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title-red'>📉 الصفقات الخاسرة</div><div class='card-value'>{losing_trades}</div><div class='card-sub'>صفقات</div></div>", unsafe_allow_html=True)

col3, col4 = st.columns(2)
with col3:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title-green'>💲 إجمالي الأرباح</div><div class='card-value'>+${total_profit:.2f}</div><div class='card-sub'>USD</div></div>", unsafe_allow_html=True)
with col4:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title-red'>💸 إجمالي الخسائر</div><div class='card-value'>-${total_loss:.2f}</div><div class='card-sub'>USD</div></div>", unsafe_allow_html=True)

recent_df = df.tail(window_size)
mid_r = len(recent_df) // 2
w0_curr = float(recent_df.iloc[:mid_r]['Low'].min())
w1_curr = float(recent_df.iloc[mid_r:]['High'].max())
current_price = float(df['Close'].iloc[-1])

st.markdown("### 🎯 التوصية الحالية (Spot - شراء)")
if w1_curr > w0_curr:
    diff_c = w1_curr - w0_curr
    entry_c = w1_curr - (diff_c * 0.618)
    target_c = w0_curr + (diff_c * 1.618)
    sl_c = w0_curr
    status_msg = "⏳ بانتظار هبوط السعر لمنطقة الدخول" if current_price > entry_c else "✅ السعر في منطقة الشراء!"
    if current_price <= sl_c:
        status_msg = "⚠️ تم كسر القاع، النموذج ملغي"

    st.markdown(f"""
    <div class="rec-box">
        <p><b>الحالة:</b> {status_msg} (السعر الحالي: <code>{current_price:.2f}</code>)</p>
        <ul>
            <li>🟢 <b>الدخول (0.618):</b> <code>{entry_c:.2f}</code></li>
            <li>🎯 <b>الهدف (1.618):</b> <code>{target_c:.2f}</code></li>
            <li>🛑 <b>وقف الخسارة (wave_0):</b> <code>{sl_c:.2f}</code></li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("الاتجاه الحالي هابط، لا توجد توصية شراء حالياً.")

if trades_log:
    with st.expander("📋 سجل الصفقات التاريخية"):
        st.dataframe(pd.DataFrame(trades_log), use_container_width=True)
