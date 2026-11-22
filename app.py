import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="نظام موجات إليوت - Spot", layout="centered")

# تنسيق CSS لمطابقة الصورة بدقة وتصغير البطاقات
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
</style>
""", unsafe_allow_html=True)

# إعدادات افتراضية في الخفاء
capital = 100.0
fib_entry = 0.618

# 1. شريط اختيار الفترة (مطابق لأعلى الصورة)
timeframe_choice = st.radio("", ["24 ساعة", "أسبوع", "شهر"], index=2, horizontal=True)
period_map = {"24 ساعة": "2d", "أسبوع": "7d", "شهر": "1mo"}
selected_period = period_map[timeframe_choice]

# 2. المدخلات الظاهرة (مطابقة للصورة تماماً)
atr_sl_mult = st.number_input("ATR SL:", min_value=0.1, value=4.00, step=0.10, format="%.2f")
rr_ratio = st.number_input("R : R:", min_value=0.5, value=3.70, step=0.10, format="%.2f")

symbols_dict = {
    "الكل": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
    "BTC-USD": ["BTC-USD"],
    "ETH-USD": ["ETH-USD"],
    "SOL-USD": ["SOL-USD"],
    "BNB-USD": ["BNB-USD"],
    "XRP-USD": ["XRP-USD"]
}
selected_coin = st.selectbox("العملة:", list(symbols_dict.keys()), index=0)

@st.cache_data(ttl=300)
def get_crypto_data(ticker, per):
    df = yf.download(ticker, period=per, interval="1h", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if not df.empty:
        # حساب مؤشر ATR (14 شمعة)
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean().bfill()
    return df
winning_trades, losing_trades = 0, 0
total_profit, total_loss = 0.0, 0.0
recommendations = []
trades_log = []

window_size = 24  # 24 شمعة لتحديد القاع wave_0 والقمة wave_1

for sym in symbols_dict[selected_coin]:
    df = get_crypto_data(sym, selected_period)
    if df.empty or len(df) < window_size:
        continue

    # فحص الصفقات التاريخية (Spot شراء فقط)
    for i in range(0, len(df) - window_size, 12):
        sub_df = df.iloc[i : i + window_size]
        mid = len(sub_df) // 2
        wave_0 = float(sub_df.iloc[:mid]['Low'].min())
        wave_1 = float(sub_df.iloc[mid:]['High'].max())

        if wave_1 > wave_0:
            diff = wave_1 - wave_0
            entry_2 = wave_1 - (diff * fib_entry)
            atr_val = float(sub_df['ATR'].iloc[-1])
            
            # وقف الخسارة باستخدام ATR SL مع احترام قاع إليوت
            sl_atr = entry_2 - (atr_val * atr_sl_mult)
            stop_loss_0 = max(wave_0, sl_atr) if sl_atr < entry_2 else wave_0
            
            # الهدف باستخدام نسبة R : R (مع مراعاة امتداد 1.618)
            risk = entry_2 - stop_loss_0
            if risk <= 0:
                continue
            target_5 = entry_2 + (risk * rr_ratio)

            future_df = df.iloc[i + window_size : i + (window_size * 2)]
            entered = False
            for date, row in future_df.iterrows():
                low_p, high_p = float(row['Low']), float(row['High'])
                if not entered and low_p <= entry_2:
                    entered = True
                    continue
                if entered:
                    if low_p <= stop_loss_0:
                        loss_usd = capital * (risk / entry_2)
                        losing_trades += 1
                        total_loss += loss_usd
                        trades_log.append({"العملة": sym, "الحالة": "خاسرة ❌", "الدخول": round(entry_2, 2), "الإغلاق": round(stop_loss_0, 2), "النتيجة": f"-${loss_usd:.2f}"})
                        break
                    elif high_p >= target_5:
                        profit_usd = capital * ((target_5 - entry_2) / entry_2)
                        winning_trades += 1
                        total_profit += profit_usd
                        trades_log.append({"العملة": sym, "الحالة": "رابحة ✅", "الدخول": round(entry_2, 2), "الإغلاق": round(target_5, 2), "النتيجة": f"+${profit_usd:.2f}"})
                        break

    # استخراج التوصية الحالية من آخر 24 شمعة
    rec_df = df.tail(window_size)
    mid_r = len(rec_df) // 2
    w0_c = float(rec_df.iloc[:mid_r]['Low'].min())
    w1_c = float(rec_df.iloc[mid_r:]['High'].max())
    curr_p = float(df['Close'].iloc[-1])
    curr_atr = float(df['ATR'].iloc[-1])

    if w1_c > w0_c:
        diff_c = w1_c - w0_c
        ent_c = w1_c - (diff_c * fib_entry)
        sl_c_raw = ent_c - (curr_atr * atr_sl_mult)
        sl_c = max(w0_c, sl_c_raw) if sl_c_raw < ent_c else w0_c
        risk_c = ent_c - sl_c
        if risk_c > 0 and curr_p > sl_c:
            tgt_c = ent_c + (risk_c * rr_ratio)
            recommendations.append((sym, curr_p, ent_c, tgt_c, sl_c))

total_trades = winning_trades + losing_trades
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

# 3. العنوان والبطاقات (مطابقة تماماً لترتيب وألوان الصورة)
st.markdown(f"<h3 style='text-align: right; margin-top: 15px;'>📊 نتائج {timeframe_choice} (1h)</h3>", unsafe_allow_html=True)

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

# 4. قسم التوصيات الحالية (Spot - شراء فقط)
st.markdown("### 🎯 التوصيات الحالية (Spot شراء)")
if recommendations:
    for sym, cp, ent, tgt, sl in recommendations:
        status = "✅ منطقة شراء" if cp <= ent else "⏳ انتظار التصحيح"
        st.markdown(f"""
        <div class="rec-box">
            <b>{sym}</b> | السعر: <code>{cp:.2f}</code> ({status})<br>
            <span style="color:#4caf50;">🟢 الدخول: <b>{ent:.2f}</b></span> &nbsp;|&nbsp;
            <span style="color:#2196f3;">🎯 الهدف: <b>{tgt:.2f}</b></span> &nbsp;|&nbsp;
            <span style="color:#ef5350;">🛑 الوقف: <b>{sl:.2f}</b></span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("لا توجد فرص شراء مكتملة الشروط حالياً.")

if trades_log:
    with st.expander("📋 سجل الصفقات"):
        st.dataframe(pd.DataFrame(trades_log), use_container_width=True)
