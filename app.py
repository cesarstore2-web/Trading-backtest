import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Supertrend Multi-TP & EMA 200", page_icon="⚡", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.stApp { background: radial-gradient(circle at top, #1e1338 0%, #09090f 100%); color: #ffffff; direction: rtl; text-align: right; }
.stat-card { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 15px; margin-bottom: 12px; text-align: center; }
.card-green { border-color: rgba(16, 185, 129, 0.45); background: rgba(16, 185, 129, 0.07); }
.card-red { border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.07); }
.card-signal { border-color: rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.12); text-align: right; padding: 18px; line-height: 1.8; }
.card-title { font-size: 13px; color: #a1a1aa; margin-bottom: 4px; }
.card-value { font-size: 23px; font-weight: 800; }
.green-text { color: #10b981; }
.red-text { color: #ef4444; }
.purple-text { color: #a855f7; }
div.stButton > button { width: 100%; border-radius: 12px; background: linear-gradient(90deg, #7c3aed 0%, #9333ea 100%); color: white; font-weight: 700; border: none; padding: 14px; font-size: 16px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

ASSETS = {
    "العملات الرقمية": {"currency": "USDT", "is_cse": False, "items": {"XLMUSDT": "XLM-USD", "ZECUSDT": "ZEC-USD", "XRPUSDT": "XRP-USD", "HBARUSDT": "HBAR-USD", "ADAUSDT": "ADA-USD", "LTCUSDT": "LTC-USD", "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}},
    "الذهب": {"currency": "USDT", "is_cse": False, "items": {"XAUUSDT (الذهب)": "GC=F", "PAXGUSDT": "PAXG-USD"}},
    "بورصة الدار البيضاء": {"currency": "MAD", "is_cse": True, "items": {"ATW - التجاري وفا بنك": "ATW.CS", "BCP - البنك الشعبي": "BCP.CS", "AKT - أكديطال": "AKT.CS", "MNG - مناجم": "MNG.CS", "TGC - TGCC": "TGC.CS", "ADH - الضحى": "ADH.CS", "JET - جيت كونتراكترز": "JET.CS", "MSA - مرسى المغرب": "MSA.CS", "CMA - إسمنت المغرب": "CMA.CS", "LHM - لافارج هولسيم": "LHM.CS", "ATL - أطلنطا سند": "ATL.CS", "DHO - دلتا هولدينغ": "DHO.CS"}}
}

def calculate_atr(df, length=14):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(length).mean()

def apply_supertrend_ema200(df, st_len=10, st_fac=3.0, use_ema200=True):
    atr = calculate_atr(df, st_len)
    hl2 = (df['High'] + df['Low']) / 2
    upper = hl2 + (st_fac * atr)
    lower = hl2 - (st_fac * atr)
    uptrend = [True for _ in range(len(df))]
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > upper.iloc[i-1]:
            uptrend[i] = True
        elif df['Close'].iloc[i] < lower.iloc[i-1]:
            uptrend[i] = False
        else:
            uptrend[i] = uptrend[i-1]
            if uptrend[i] and lower.iloc[i] < lower.iloc[i-1]:
                lower.iloc[i] = lower.iloc[i-1]
            if not uptrend[i] and upper.iloc[i] > upper.iloc[i-1]:
                upper.iloc[i] = upper.iloc[i-1]
    df['st_up'] = uptrend
    df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    st_buy = df['st_up'] & (~df['st_up'].shift(1).fillna(False))
    st_sell = (~df['st_up']) & (df['st_up'].shift(1).fillna(True))
    
    if use_ema200:
        df['buy_sig'] = st_buy & (df['Close'] > df['ema200'])
        df['sell_sig'] = st_sell & (df['Close'] < df['ema200'])
    else:
        df['buy_sig'] = st_buy
        df['sell_sig'] = st_sell
    return df
def run_strategy(ticker, is_cse, timeframe, period_days, st_len, st_fac, use_ema200, atr_len, sl_mult, tp1_m, tp2_m, tp3_m, capital, leverage, is_spot, use_session):
    actual_days = min(period_days, 7) if timeframe in ["3m", "5m"] else period_days
    df = yf.download(ticker, period=f"{actual_days}d", interval=timeframe, progress=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')

    df = apply_supertrend_ema200(df, st_len, st_fac, use_ema200)
    df['atr'] = calculate_atr(df, atr_len)

    fee_rate = 0.002 if (is_spot or is_cse) else 0.001
    pos_size = capital * (1 if (is_spot or is_cse) else leverage)
    part_size = pos_size / 3.0  # تقسيم الصفقة إلى 3 أجزاء للأهداف الثلاثة

    trades_pnl = []
    in_trade, t_type, entry, sl, tp1, tp2, tp3, entry_time = False, None, 0, 0, 0, 0, 0, ""
    hit_tp1, hit_tp2, current_trade_pnl = False, False, 0.0

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = df.index[i]
        c_time = ts.strftime("%Y-%m-%d %H:%M")
        if pd.isna(row['atr']):
            continue

        if in_trade:
            if t_type == "BUY":
                # التحقق من ضرب وقف الخسارة
                if row['Low'] <= sl:
                    rem_parts = 3 - (1 if hit_tp1 else 0) - (1 if hit_tp2 else 0)
                    pnl_close = (part_size * rem_parts) * ((sl - entry) / entry) - ((part_size * rem_parts) * fee_rate)
                    trades_pnl.append(current_trade_pnl + pnl_close)
                    in_trade = False
                else:
                    if not hit_tp1 and row['High'] >= tp1:
                        hit_tp1 = True
                        current_trade_pnl += part_size * ((tp1 - entry) / entry) - (part_size * fee_rate)
                        sl = entry  # تأمين الصفقة بنقل الاستوب لنقطة الدخول
                    if not hit_tp2 and row['High'] >= tp2:
                        hit_tp2 = True
                        current_trade_pnl += part_size * ((tp2 - entry) / entry) - (part_size * fee_rate)
                    if row['High'] >= tp3:
                        current_trade_pnl += part_size * ((tp3 - entry) / entry) - (part_size * fee_rate)
                        trades_pnl.append(current_trade_pnl)
                        in_trade = False

            elif t_type == "SELL":
                if row['High'] >= sl:
                    rem_parts = 3 - (1 if hit_tp1 else 0) - (1 if hit_tp2 else 0)
                    pnl_close = (part_size * rem_parts) * ((entry - sl) / entry) - ((part_size * rem_parts) * fee_rate)
                    trades_pnl.append(current_trade_pnl + pnl_close)
                    in_trade = False
                else:
                    if not hit_tp1 and row['Low'] <= tp1:
                        hit_tp1 = True
                        current_trade_pnl += part_size * ((entry - tp1) / entry) - (part_size * fee_rate)
                        sl = entry  # تأمين الصفقة بنقل الاستوب لنقطة الدخول
                    if not hit_tp2 and row['Low'] <= tp2:
                        hit_tp2 = True
                        current_trade_pnl += part_size * ((entry - tp2) / entry) - (part_size * fee_rate)
                    if row['Low'] <= tp3:
                        current_trade_pnl += part_size * ((entry - tp3) / entry) - (part_size * fee_rate)
                        trades_pnl.append(current_trade_pnl)
                        in_trade = False

        in_session = True
        if is_cse:
            in_session = (ts.hour > 9 or (ts.hour == 9 and ts.minute >= 30)) and (ts.hour < 15 or (ts.hour == 15 and ts.minute <= 30))
        elif use_session:
            in_session = (ts.hour > 8 or (ts.hour == 8 and ts.minute >= 30)) and (ts.hour < 20)

        if not in_trade and in_session:
            atr_val = float(row['atr'])
            if row['buy_sig']:
                entry = float(row['Close'])
                sl = entry - (sl_mult * atr_val)
                tp1 = entry + (tp1_m * atr_val)
                tp2 = entry + (tp2_m * atr_val)
                tp3 = entry + (tp3_m * atr_val)
                t_type, entry_time, in_trade = "BUY", c_time, True
                hit_tp1, hit_tp2, current_trade_pnl = False, False, 0.0
            elif not (is_spot or is_cse) and row['sell_sig']:
                entry = float(row['Close'])
                sl = entry + (sl_mult * atr_val)
                tp1 = entry - (tp1_m * atr_val)
                tp2 = entry - (tp2_m * atr_val)
                tp3 = entry - (tp3_m * atr_val)
                t_type, entry_time, in_trade = "SELL", c_time, True
                hit_tp1, hit_tp2, current_trade_pnl = False, False, 0.0

    last_row = df.iloc[-1]
    sig = None
    if in_trade:
        sig = {
            "type": "شراء (BUY) 🟢" if t_type == "BUY" else "بيع (SELL) 🔴",
            "time": entry_time, "entry": round(entry, 4), "current": round(float(last_row['Close']), 4),
            "sl": round(sl, 4), "tp1": round(tp1, 4), "tp2": round(tp2, 4), "tp3": round(tp3, 4),
            "tp1_done": "✅" if hit_tp1 else "⏳", "tp2_done": "✅" if hit_tp2 else "⏳"
        }
    return trades_pnl, sig, round(float(last_row['Close']), 4), round(float(last_row['ema200']), 4)

st.markdown("<h2 style='text-align:center;'>⚡ Supertrend Multi-TP & EMA 200</h2>", unsafe_allow_html=True)

c_tf, c_pr = st.columns(2)
tf_label = c_tf.selectbox("⏱️ الإطار الزمني (الفريم)", ["3 دقائق (3m)", "5 دقائق (5m)", "15 دقيقة (15m)", "30 دقيقة (30m)", "1 ساعة (1h)"], index=3)
tf_map = {"3 دقائق (3m)": "3m", "5 دقائق (5m)": "5m", "15 دقيقة (15m)": "15m", "30 دقيقة (30m)": "30m", "1 ساعة (1h)": "1h"}
timeframe = tf_map[tf_label]

tf_choice = c_pr.selectbox("فترة الاختبار", ["يومي (5 أيام)", "أسبوعي (7 أيام)", "نصف شهري (14 يوم)", "شهري (30 يوم)", "أقصى مدة (60 يوم)"], index=3)
days_map = {"يومي (5 أيام)": 5, "أسبوعي (7 أيام)": 7, "نصف شهري (14 يوم)": 14, "شهري (30 يوم)": 30, "أقصى مدة (60 يوم)": 60}

col_c, col_a = st.columns(2)
cat_choice = col_c.selectbox("السوق", list(ASSETS.keys()))
asset_name = col_a.selectbox("الأصل المالي", list(ASSETS[cat_choice]["items"].keys()))
ticker, currency, is_cse = ASSETS[cat_choice]["items"][asset_name], ASSETS[cat_choice]["currency"], ASSETS[cat_choice]["is_cse"]

f1, f2 = st.columns(2)
use_ema200 = f1.checkbox("🛡️ تفعيل فلتر EMA 200 (منع التداول العرضي)", value=True)
use_session = f2.checkbox("🕒 توقيت المغرب (08:30 - 20:00)", value=True)

st.markdown("##### 💰 إدارة المحفظة ونوع التداول")
m1, m2, m3 = st.columns(3)
capital = m1.number_input(f"رأس المال ({currency})", value=100.0, min_value=10.0, step=50.0)
trade_mode = m2.selectbox("نوع التداول", ["سبوت (Spot)", "عقود آجلة (Futures)"]) if not is_cse else m2.selectbox("نوع التداول", ["أسهم (شراء فقط)"])
is_spot = True if ("سبوت" in trade_mode or is_cse) else False
leverage = m3.number_input("الرافعة المالية", value=1 if is_spot else 5, min_value=1, max_value=50, disabled=is_spot)

st.markdown("##### ⚙️ إعدادات Supertrend & ATR (TP1, TP2, TP3, SL)")
s1, s2, s3 = st.columns(3)
st_len = s1.number_input("Supertrend Len", value=10, min_value=1)
st_fac = s2.number_input("Supertrend Factor", value=3.0, min_value=0.5, step=0.5)
atr_len = s3.number_input("ATR Length", value=14, min_value=1)

t1, t2, t3, t4 = st.columns(4)
sl_mult = t1.number_input("SL (×ATR)", value=1.5, min_value=0.1, step=0.1)
tp1_m = t2.number_input("TP1 (×ATR)", value=1.0, min_value=0.1, step=0.5)
tp2_m = t3.number_input("TP2 (×ATR)", value=2.0, min_value=0.5, step=0.5)
tp3_m = t4.number_input("TP3 (×ATR)", value=3.0, min_value=0.5, step=0.5)

if st.button("🚀 تشغيل التقييم وحساب المستويات"):
    with st.spinner(f"جاري تحليل فريم {timeframe} وحساب الأهداف الثلاثة..."):
        res = run_strategy(ticker, is_cse, timeframe, days_map[tf_choice], st_len, st_fac, use_ema200, atr_len, sl_mult, tp1_m, tp2_m, tp3_m, capital, leverage, is_spot, use_session)
    if res is None:
        st.warning(f"⚠️ بيانات فريم {timeframe} غير متوفرة حالياً لهذا الرمز.")
    else:
        trades, sig, price, ema_val = res
        if sig:
            st.markdown(f"""
            <div class="stat-card card-signal">
                <div style="font-size:16px; font-weight:800; color:#d8b4fe;">⚡ صفقة نشطة: {sig['type']}</div>
                <div>🕒 <b>وقت الإشارة:</b> {sig['time']} | <b>الدخول (Entry):</b> {sig['entry']} | <b>السعر الحالي:</b> {sig['current']}</div>
                <div class="red-text">🛑 <b>وقف الخسارة (SL):</b> {sig['sl']}</div>
                <div class="green-text">🎯 <b>الهدف الأول (TP1):</b> {sig['tp1']} {sig['tp1_done']} &nbsp;|&nbsp; <b>الهدف الثاني (TP2):</b> {sig['tp2']} {sig['tp2_done']}</div>
                <div class="green-text">🏆 <b>الهدف الثالث (TP3):</b> {sig['tp3']}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            trend_pos = "فوق EMA 200 (شراء فقط 🟢)" if price > ema_val else "تحت EMA 200 (بيع فقط 🔴)"
            st.info(f"⏳ لا توجد صفقة نشطة حالياً — السعر: **{price}** | الوضع: **{trend_pos}**")

        wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
        win_rate = round((len(wins) / len(trades)) * 100, 1) if trades else 0
        tot_profit, tot_loss, net = round(sum(wins), 2), round(abs(sum(losses)), 2), round(sum(trades), 2)

        st.markdown(f'<div class="stat-card"><div class="card-title">نسبة النجاح (صافي بعد العمولات وتأمين الدخول)</div><div class="card-value purple-text">{win_rate}%</div></div>', unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        r1.markdown(f'<div class="stat-card"><div class="card-title">عدد الصفقات</div><div class="card-value">{len(trades)}</div></div>', unsafe_allow_html=True)
