import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="نظام موجات إليوت + EMA 100", layout="centered")

# تنسيق CSS لمطابقة التصميم وتصغير البطاقات
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; direction: rtl; }
    div[role="radiogroup"] { justify-content: center; flex-direction: row-reverse; gap: 15px; }
    label, .stSelectbox label, .stNumberInput label { text-align: right !important; display: block; width: 100%; color: #fafafa !important; }
    
    .metric-card {
        background-color: #161920;
        border-radius: 10px;
        padding: 12px 15px;
        margin-bottom: 10px;
        text-align: center;
    }
    .card-blue   { border: 1.5px solid #1f77b4; }
    .card-purple { border: 1.5px solid #7c4dff; }
    .card-green  { border: 1.5px solid #2e7d32; }
    .card-red    { border: 1.5px solid #c62828; }
    
    .title-white  { color: #e0e0e0; font-size: 13px; margin-bottom: 5px; }
    .title-purple { color: #b388ff; font-size: 13px; margin-bottom: 5px; }
    .title-green  { color: #4caf50; font-size: 13px; margin-bottom: 5px; }
    .title-red    { color: #ef5350; font-size: 13px; margin-bottom: 5px; }
    
    .card-val { color: #ffffff; font-size: 24px; font-weight: bold; margin: 2px 0; }
    .card-sub { color: #8e8e93; font-size: 11px; }
    
    .rec-box {
        background-color: #161920;
        border: 1px solid #2d3139;
        border-radius: 10px;
        padding: 12px 15px;
        margin-bottom: 8px;
        text-align: right;
    }
    .tf-badge {
        background-color: #262b36;
        color: #64b5f6;
        padding: 2px 8px;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# رأس المال افتراضي في الخفاء
capital = 100.0

# 1. شريط اختيار الفترة والفريم
timeframe_choice = st.radio("", ["24 ساعة", "أسبوع", "شهر"], index=2, horizontal=True)
tf_config = {
    "24 ساعة": {"period": "5d",  "interval": "5m",  "window": 36, "step": 18, "display_bars": 288},
    "أسبوع":   {"period": "1mo", "interval": "15m", "window": 32, "step": 16, "display_bars": 672},
    "شهر":     {"period": "2mo", "interval": "30m", "window": 30, "step": 15, "display_bars": 1440}
}
selected_period = tf_config[timeframe_choice]["period"]
selected_interval = tf_config[timeframe_choice]["interval"]
window_size = tf_config[timeframe_choice]["window"]
step_size = tf_config[timeframe_choice]["step"]
display_bars = tf_config[timeframe_choice]["display_bars"]

# 2. نافذة الفيبوناتشي واختيار العملة
fib_entry = st.number_input("نسبة الفيبوناتشي (الدخول):", min_value=0.100, max_value=0.900, value=0.618, step=0.010, format="%.3f")

symbols_dict = {
    "الكل": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
    "BTC-USD": ["BTC-USD"],
    "ETH-USD": ["ETH-USD"],
    "SOL-USD": ["SOL-USD"],
    "BNB-USD": ["BNB-USD"],
    "XRP-USD": ["XRP-USD"]
}
selected_coin = st.selectbox("العملة:", list(symbols_dict.keys()), index=0)

@st.cache_data(ttl=180)
def get_crypto_data(ticker, per, interv):
    df = yf.download(ticker, period=per, interval=interv, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if not df.empty:
        # حساب المتوسط المتحرك الأسي EMA 100
        df['EMA100'] = df['Close'].ewm(span=100, adjust=False).mean()
    return df
winning_trades, losing_trades = 0, 0
total_profit, total_loss = 0.0, 0.0
trades_log = []

# 3. حساب النتائج التاريخية (Spot شراء فقط + فلتر EMA 100)
for sym in symbols_dict[selected_coin]:
    full_df = get_crypto_data(sym, selected_period, selected_interval)
    if full_df.empty or len(full_df) < 120:
        continue
    
    # أخذ الشموع الخاصة بالفترة المختارة بعد استقرار EMA 100
    df = full_df.tail(display_bars)

    for i in range(0, len(df) - window_size, step_size):
        sub_df = df.iloc[i : i + window_size]
        mid = len(sub_df) // 2
        
        wave_0 = float(sub_df.iloc[:mid]['Low'].min())
        wave_1 = float(sub_df.iloc[mid:]['High'].max())
        ema_val = float(sub_df['EMA100'].iloc[-1])

        # شرط الصعود وشرط وجود السعر فوق EMA 100
        if wave_1 > wave_0 and wave_1 > ema_val:
            diff = wave_1 - wave_0
            entry_2 = wave_1 - (diff * fib_entry)
            target_5 = wave_0 + (diff * 1.618)
            stop_loss_0 = wave_0

            # التأكد أن نقطة الدخول أعلى أو قريبة من EMA 100
            if entry_2 < ema_val:
                continue

            future_df = df.iloc[i + window_size : i + (window_size * 2)]
            touched_fib = False
            entered = False

            for date, row in future_df.iterrows():
                low_p, high_p = float(row['Low']), float(row['High'])
                open_p, close_p = float(row['Open']), float(row['Close'])
                row_ema = float(row['EMA100'])

                if not entered:
                    if low_p <= stop_loss_0:
                        break
                    if low_p <= entry_2:
                        touched_fib = True
                    # الدخول بعد ملامسة الفيبوناتشي وإغلاق شمعة صاعدة فوق EMA 100
                    if touched_fib and close_p > open_p and close_p >= entry_2 and close_p > row_ema:
                        entered = True
                        actual_entry = close_p
                        continue
                else:
                    if low_p <= stop_loss_0:
                        loss_usd = capital * ((actual_entry - stop_loss_0) / actual_entry)
                        losing_trades += 1
                        total_loss += loss_usd
                        trades_log.append({
                            "العملة": sym, "الفريم": selected_interval, "الحالة": "خاسرة ❌",
                            "الدخول": round(actual_entry, 2), "الإغلاق": round(stop_loss_0, 2),
                            "النتيجة": f"-${loss_usd:.2f}"
                        })
                        break
                    elif high_p >= target_5:
                        profit_usd = capital * ((target_5 - actual_entry) / actual_entry)
                        winning_trades += 1
                        total_profit += profit_usd
                        trades_log.append({
                            "العملة": sym, "الفريم": selected_interval, "الحالة": "رابحة ✅",
                            "الدخول": round(actual_entry, 2), "الإغلاق": round(target_5, 2),
                            "النتيجة": f"+${profit_usd:.2f}"
                        })
                        break

total_trades = winning_trades + losing_trades
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

# عرض العنوان والبطاقات
st.markdown(f"<h3 style='text-align: right; margin-top: 15px;'>📊 نتائج {timeframe_choice} ({selected_interval})</h3>", unsafe_allow_html=True)

st.markdown(f"<div class='metric-card card-blue'><div class='title-white'>🤝 الصفقات</div><div class='card-val'>{total_trades}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='metric-card card-purple'><div class='title-purple'>🎯 النجاح</div><div class='card-val'>{win_rate:.1f}%</div></div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"<div class='metric-card card-green'><div class='title-green'>📈 الصفقات الرابحة</div><div class='card-val'>{winning_trades}</div><div class='card-sub'>صفقات</div></div>", unsafe_allow_html=True)
with c2:
    st.markdown(f"<div class='metric-card card-red'><div class='title-red'>📉 الصفقات الخاسرة</div><div class='card-val'>{losing_trades}</div><div class='card-sub'>صفقات</div></div>", unsafe_allow_html=True)

c3, c4 = st.columns(2)
with c3:
    st.markdown(f"<div class='metric-card card-green'><div class='title-green'>💲 إجمالي الأرباح</div><div class='card-val'>+${total_profit:.2f}</div><div class='card-sub'>USD</div></div>", unsafe_allow_html=True)
with c4:
    st.markdown(f"<div class='metric-card card-red'><div class='title-red'>💸 إجمالي الخسائر</div><div class='card-val'>-${total_loss:.2f}</div><div class='card-sub'>USD</div></div>", unsafe_allow_html=True)

# 4. قسم التوصيات الحالية فقط على فريمات (5m, 15m, 30m) بشرط EMA 100
st.markdown("### 🎯 التوصيات الحالية (5m | 15m | 30m)")
rec_timeframes = [("5m", "5d", 36), ("15m", "1mo", 32), ("30m", "2mo", 30)]
recommendations = []

for sym in symbols_dict[selected_coin]:
    for tf_name, tf_per, tf_win in rec_timeframes:
        df_rec = get_crypto_data(sym, tf_per, tf_name)
        if df_rec.empty or len(df_rec) < 110:
            continue
        
        rec_slice = df_rec.tail(tf_win)
        mid_r = len(rec_slice) // 2
        w0_c = float(rec_slice.iloc[:mid_r]['Low'].min())
        w1_c = float(rec_slice.iloc[mid_r:]['High'].max())
        curr_p = float(df_rec['Close'].iloc[-1])
        curr_ema = float(df_rec['EMA100'].iloc[-1])

        if w1_c > w0_c and curr_p > curr_ema:
            diff_c = w1_c - w0_c
            ent_c = w1_c - (diff_c * fib_entry)
            tgt_c = w0_c + (diff_c * 1.618)
            sl_c = w0_c
            
            if curr_p > sl_c and ent_c >= curr_ema:
                recommendations.append((sym, tf_name, curr_p, ent_c, tgt_c, sl_c))

if recommendations:
    for sym, tf_n, cp, ent, tgt, sl in recommendations:
        status = "✅ منطقة شراء (فوق EMA100)" if cp <= ent else "⏳ انتظار التصحيح (فوق EMA100)"
        st.markdown(f"""
        <div class="rec-box">
            <b>{sym}</b> <span class="tf-badge">{tf_n}</span> | السعر: <code>{cp:.2f}</code> ({status})<br>
            <span style="color:#4caf50;">🟢 الدخول (entry_2): <b>{ent:.2f}</b></span> &nbsp;|&nbsp;
            <span style="color:#2196f3;">🎯 الهدف (target_5): <b>{tgt:.2f}</b></span> &nbsp;|&nbsp;
            <span style="color:#ef5350;">🛑 الوقف (wave_0): <b>{sl:.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("لا توجد فرص شراء فوق EMA 100 حالياً.")

if trades_log:
    with st.expander("📋 سجل الصفقات"):
        st.dataframe(pd.DataFrame(trades_log), use_container_width=True)
