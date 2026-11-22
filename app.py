import import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
st.set_page_config(page_title="Tricks HeLaL — Backtest", layout="centered")
st.markdown("""<style>
.stApp { background-color: #0d0d12; color: #fff; direction: rtl; font-family: Tahoma; }
div[role='radiogroup'] { display: flex; justify-content: space-around; background: #1c1c24; padding: 6px; border-radius: 12px; }
div[role='radiogroup'] label { color: #fff !important; }
.card { border-radius: 14px; padding: 15px; text-align: center; background: #16161e; margin-bottom: 12px; border: 1.5px solid #2b6cb0; }
.c-purp { border-color: #805ad5; } .c-grn { border-color: #38a169; } .c-red { border-color: #e53e3e; }
.sig-b { background: #1a1a24; border-right: 4px solid #03ff85; padding: 12px; border-radius: 10px; margin-bottom: 10px; }
.sig-s { background: #1a1a24; border-right: 4px solid #fc0808; padding: 12px; border-radius: 10px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)
SYMBOLS = ["XLM", "ZEC", "XRP", "HBAR", "ADA", "LTC", "BTC", "ETH", "PAXG"]
PERIODS = {"24 ساعة": ("5m", "5d", 24), "أسبوع": ("15m", "1mo", 168), "شهر": ("1h", "3mo", 720)}
sel_p = st.radio("المدة:", list(PERIODS.keys()), horizontal=True, label_visibility="collapsed")
tf, yf_p, hrs = PERIODS[sel_p]
c1, c2, c3 = st.columns(3)
atr_m = c1.number_input("ATR SL:", 0.1, 10.0, 1.5, 0.1)
rr_val = c2.number_input("R : R :", 0.5, 15.0, 2.0, 0.1)
sel_coin = c3.selectbox("العملة:", ["الكل"] + SYMBOLS)
@st.cache_data(ttl=180)
def load_yf(syms, interval, period):
    out = {}
    for c in syms:
        try:
            df = yf.download(f"{c}-USD", period=period, interval=interval, progress=False, auto_adjust=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.reset_index()
                t_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
                df['dt'] = pd.to_datetime(df[t_col], utc=True)
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                out[c] = df.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
        except Exception:
            pass
    return out
def analyze(data, atr_mult, rr, hours):
    sigs, trades = [], []
    depth, backstep, dev, min_bars = 30, 30, 5, 8
    cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=hours)
    for coin, df in data.items():
        if len(df) < depth + backstep + 15: continue
        pc = df['Close'].shift(1)
        tr = pd.concat([df['High']-df['Low'], (df['High']-pc).abs(), (df['Low']-pc).abs()], axis=1).max(axis=1)
        atrs = tr.rolling(14).mean().bfill().values
        H, L, C, T = df['High'].values, df['Low'].values, df['Close'].values, df['dt']
        tick = 0.01 if C[-1] >= 100 else (0.0001 if C[-1] >= 1 else 0.00001)
        last_p, last_d, last_b, conf = None, 0, None, []
        for i in range(depth + backstep, len(df)):
            p = i - backstep
            is_ph = H[p] >= np.max(H[p-depth:p]) and H[p] > np.max(H[p+1:p+backstep+1])
            is_pl = L[p] <= np.min(L[p-depth:p]) and L[p] < np.min(L[p+1:p+backstep+1])
            if is_ph or is_pl:
                sell = is_ph and (not is_pl or H[p] >= L[p])
                px = H[p] if sell else L[p]
                if (last_p is None or abs(px - last_p) >= dev * tick) and (last_b is None or i - last_b >= min_bars):
                    if (sell and last_d != 1) or (not sell and last_d != -1):
                        last_d, last_p, last_b = (1 if sell else -1), px, i
                        conf.append((i, "SELL" if sell else "BUY"))
        busy = -1
        for idx, side in conf:
            if idx <= busy: continue
            ep, sd = C[idx], atrs[idx] * atr_mult
            sl, tp = (ep - sd, ep + sd * rr) if side == "BUY" else (ep + sd, ep - sd * rr)
            for j in range(idx + 1, len(df)):
                hit_sl = L[j] <= sl if side == "BUY" else H[j] >= sl
                hit_tp = H[j] >= tp if side == "BUY" else L[j] <= tp
                if hit_sl or hit_tp:
                    if T.iloc[j] >= cutoff:
                        pnl = 1000.0 * (((sl - ep) if hit_sl else (tp - ep)) / ep) * (1 if side == "BUY" else -1)
                        trades.append({"coin": coin, "win": not hit_sl, "pnl": pnl})
                    busy = j
                    break
        if conf:
            idx, side = conf[-1]
            ep, sd = C[idx], atrs[idx] * atr_mult
            sl, tp = (ep - sd, ep + sd * rr) if side == "BUY" else (ep + sd, ep - sd * rr)
            dec = 2 if C[-1] > 10 else 4
            sigs.append({"coin": coin, "buy": side == "BUY", "p": round(C[-1], dec), "e": round(ep, dec), "tp": round(tp, dec), "sl": round(sl, dec), "ago": len(df)-1-idx})
    return pd.DataFrame(sigs), pd.DataFrame(trades)
with st.spinner("جاري التحليل..."):
    raw_data = load_yf(SYMBOLS, tf, yf_p)
    df_s, df_t = analyze(raw_data, atr_m, rr_val, hrs)
if sel_coin != "الكل":
    df_s = df_s[df_s["coin"] == sel_coin] if not df_s.empty else df_s
    df_t = df_t[df_t["coin"] == sel_coin] if not df_t.empty else df_t
tot = len(df_t)
wins = int(df_t["win"].sum()) if tot else 0
loss = tot - wins
rate = round(wins / tot * 100, 1) if tot else 0.0
prof = round(df_t[df_t["pnl"] > 0]["pnl"].sum(), 2) if tot else 0.0
los_usd = round(abs(df_t[df_t["pnl"] < 0]["pnl"].sum()), 2) if tot else 0.0
net = round(prof - los_usd, 2)
st.markdown(f"### 📊 نتائج {sel_p} ({tf})")
a1, a2 = st.columns(2)
a1.markdown(f"<div class='card'><div>🤝 الصفقات</div><h2>{tot}</h2></div>", unsafe_allow_html=True)
a2.markdown(f"<div class='card c-purp'><div>🎯 النجاح</div><h2>{rate}%</h2></div>", unsafe_allow_html=True)
a3, a4 = st.columns(2)
a3.markdown(f"<div class='card c-grn'><div>📈 رابحة</div><h2>{wins}</h2></div>", unsafe_allow_html=True)
a4.markdown(f"<div class='card c-red'><div>📉 خاسرة</div><h2>{loss}</h2></div>", unsafe_allow_html=True)
a5, a6 = st.columns(2)
a5.markdown(f"<div class='card c-grn'><div>💲 الأرباح</div><h2>+${prof:,.2f}</h2></div>", unsafe_allow_html=True)
a6.markdown(f"<div class='card c-red'><div>💲 الخسائر</div><h2>-${los_usd:,.2f}</h2></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-purp'><div>✨ صافي الربح</div><h2 style='color:{'#48bb78' if net>=0 else '#f56565'}'>${net:,.2f}</h2></div>", unsafe_allow_html=True)
st.markdown("### 🤖 أحدث الإشارات")
for _, r in (df_s.sort_values("ago") if not df_s.empty else df_s).iterrows():
    cls = "sig-b" if r["buy"] else "sig-s"
    tag = "شراء" if r["buy"] else "بيع"
    st.markdown(f"<div class='{cls}'><b>🪙 {r['coin']} (${r['p']}) — {tag} (منذ {r['ago']} شمعة)</b><br>🔵 دخول: ${r['e']} | 🟢 هدف: ${r['tp']} | 🔴 وقف: ${r['sl']}</div>", unsafe_allow_html=True)
# END as st
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
