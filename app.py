import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="مُقيّم Viprasol & Symmetry", page_icon="⚡", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.stApp { background: radial-gradient(circle at top, #1e1338 0%, #09090f 100%); color: #ffffff; direction: rtl; text-align: right; }
.stat-card { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 15px; margin-bottom: 12px; text-align: center; }
.card-green { border-color: rgba(16, 185, 129, 0.45); background: rgba(16, 185, 129, 0.07); }
.card-red { border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.07); }
.card-signal { border-color: rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.12); text-align: right; padding: 18px; }
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

def apply_viprasol_and_symmetry(df, mode, sens=3.5, atr_fac=2.0, use_ema200=True, swing_len=14, sym_atr_len=20, ob_lvl=60, os_lvl=-60):
    # 1. حساب Viprasol Multi-Timeframe Trend Signal Engine (Sensitivity=3.5, ATR Factor=2)
    atr_v = calculate_atr(df, int(round(sens * 4)))
    hl2 = (df['High'] + df['Low']) / 2
    upper = hl2 + (atr_fac * atr_v)
    lower = hl2 - (atr_fac * atr_v)
    trend = [1 for _ in range(len(df))]
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > upper.iloc[i-1]:
            trend[i] = 1
        elif df['Close'].iloc[i] < lower.iloc[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
            if trend[i] == 1 and lower.iloc[i] < lower.iloc[i-1]:
                lower.iloc[i] = lower.iloc[i-1]
            if trend[i] == -1 and upper.iloc[i] > upper.iloc[i-1]:
                upper.iloc[i] = upper.iloc[i-1]
    s_trend = pd.Series(trend, index=df.index)
    vip_buy = (s_trend == 1) & (s_trend.shift(1) == -1)
    vip_sell = (s_trend == -1) & (s_trend.shift(1) == 1)

    if use_ema200:
        ema200 = df['Close'].ewm(span=200, adjust=False).mean()
        vip_buy = vip_buy & (df['Close'] > ema200)
        vip_sell = vip_sell & (df['Close'] < ema200)

    # 2. حساب Symmetry Reversal Oscillator (Swing=14, ATR=20, Adaptive EMA 1..15, OB=60, OS=-60)
    atr_s = calculate_atr(df, sym_atr_len)
    highest = df['High'].rolling(swing_len).max()
    lowest = df['Low'].rolling(swing_len).min()
    mid = (highest + lowest) / 2
    raw_osc = ((df['Close'] - mid) / (atr_s.replace(0, np.nan))) * 25
    # تنعيم تكيفي (Adaptive EMA بين 1 و 15)
    osc_fast = raw_osc.ewm(span=3, adjust=False).mean()
    osc_slow = raw_osc.ewm(span=15, adjust=False).mean()
    sym_osc = ((osc_fast + osc_slow) / 2).clip(-100, 100)

    sym_buy = (sym_osc > sym_osc.shift(1)) & (sym_osc < ob_lvl)
    sym_sell = (sym_osc < sym_osc.shift(1)) & (sym_osc > os_lvl)
    sym_rev_buy = (sym_osc > os_lvl) & (sym_osc.shift(1) <= os_lvl)
    sym_rev_sell = (sym_osc < ob_lvl) & (sym_osc.shift(1) >= ob_lvl)

    if "الدمج" in mode:
        df['buy_sig'] = (vip_buy & sym_buy) | (sym_rev_buy & (s_trend == 1))
        df['sell_sig'] = (vip_sell & sym_sell) | (sym_rev_sell & (s_trend == -1))
    elif "Viprasol" in mode:
        df['buy_sig'] = vip_buy
        df['sell_sig'] = vip_sell
    else: # Symmetry Reversal منفرداً
        df['buy_sig'] = sym_rev_buy
        df['sell_sig'] = sym_rev_sell

    df['current_dir'] = s_trend
    df['sym_val'] = sym_osc
    return df
def run_strategy(ticker, is_cse, timeframe, period_days, mode, sens, atr_fac, use_ema200, swing_len, sym_atr_len, ob_lvl, os_lvl, risk_atr_len, sl_mult, rr_ratio, capital, leverage, is_spot, use_session):
    # ضبط أقصى فترة متاحة للفريمات الصغيرة (3m و 5m حدها الأقصى 7 أيام في yfinance)
    actual_days = min(period_days, 7) if timeframe in ["3m", "5m"] else period_days
    df = yf.download(ticker, period=f"{actual_days}d", interval=timeframe, progress=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')

    df = apply_viprasol_and_symmetry(df, mode, sens, atr_fac, use_ema200, swing_len, sym_atr_len, ob_lvl, os_lvl)
    df['risk_atr'] = calculate_atr(df, risk_atr_len)

    fee_rate = 0.002 if (is_spot or is_cse) else 0.001
    pos_size = capital * (1 if (is_spot or is_cse) else leverage)
    trades_pnl = []
    in_trade, t_type, entry, sl, tp, entry_time = False, None, 0, 0, 0, ""

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = df.index[i]
        c_time = ts.strftime("%Y-%m-%d %H:%M")
        if pd.isna(row['risk_atr']):
            continue

        if in_trade:
            if t_type == "BUY" and (row['Low'] <= sl or row['High'] >= tp):
                exit_p = sl if row['Low'] <= sl else tp
                trades_pnl.append((pos_size * ((exit_p - entry) / entry)) - (pos_size * fee_rate))
                in_trade = False
            elif t_type == "SELL" and (row['High'] >= sl or row['Low'] <= tp):
                exit_p = sl if row['High'] >= sl else tp
                trades_pnl.append((pos_size * ((entry - exit_p) / entry)) - (pos_size * fee_rate))
                in_trade = False

        in_session = True
        if is_cse:
            in_session = (ts.hour > 9 or (ts.hour == 9 and ts.minute >= 30)) and (ts.hour < 15 or (ts.hour == 15 and ts.minute <= 30))
        elif use_session:
            in_session = (ts.hour > 8 or (ts.hour == 8 and ts.minute >= 30)) and (ts.hour < 20)

        if not in_trade and in_session:
            if row['buy_sig']:
                entry, dist = float(row['Close']), float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry - dist, entry + (dist * rr_ratio), "BUY", c_time, True
            elif not (is_spot or is_cse) and row['sell_sig']:
                entry, dist = float(row['Close']), float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry + dist, entry - (dist * rr_ratio), "SELL", c_time, True

    last_row = df.iloc[-1]
    sig = {"type": "شراء 🟢" if t_type == "BUY" else "بيع 🔴", "time": entry_time, "entry": round(entry, 4), "tp": round(tp, 4), "sl": round(sl, 4), "current": round(float(last_row['Close']), 4)} if in_trade else None
    sym_now = round(float(last_row['sym_val']), 1) if not pd.isna(last_row['sym_val']) else 0
    return trades_pnl, sig, round(float(last_row['Close']), 4), sym_now, actual_days

st.markdown("<h2 style='text-align:center;'>⚡ Viprasol & Symmetry Engine</h2>", unsafe_allow_html=True)

mode_choice = st.selectbox("🎯 اختر نظام الدخول", [
    "الدمج الذكي (Viprasol + Symmetry Reversal)",
    "Viprasol Trend Engine (منفرداً)",
    "Symmetry Reversal Oscillator (منفرداً)"
])

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

use_session = st.checkbox("🕒 فلتر التوقيت الذهبي (08:30 صباحاً - 20:00 مساءً بتوقيت المغرب)", value=True)

st.markdown("##### 💰 إدارة المحفظة ونوع التداول")
m1, m2, m3 = st.columns(3)
capital = m1.number_input(f"رأس المال ({currency})", value=100.0, min_value=10.0, step=50.0)
trade_mode = m2.selectbox("نوع التداول", ["سبوت (Spot)", "عقود آجلة (Futures)"]) if not is_cse else m2.selectbox("نوع التداول", ["أسهم (شراء فقط)"])
is_spot = True if ("سبوت" in trade_mode or is_cse) else False
leverage = m3.number_input("الرافعة المالية", value=1 if is_spot else 5, min_value=1, max_value=50, disabled=is_spot)

st.markdown("##### ⚙️ إعدادات Viprasol & Symmetry (من صورك)")
v1, v2, v3 = st.columns(3)
sens = v1.number_input("Sensitivity", value=3.5, min_value=0.5, step=0.5)
atr_fac = v2.number_input("ATR Factor", value=2.0, min_value=0.5, step=0.5)
use_ema200 = v3.checkbox("Main EMA 200", value=True)

s1, s2, s3, s4 = st.columns(4)
swing_len = s1.number_input("Swing Len", value=14, min_value=1)
sym_atr_len = s2.number_input("Sym ATR", value=20, min_value=1)
ob_lvl = s3.number_input("Overbought", value=60, min_value=10)
os_lvl = s4.number_input("Oversold", value=-60, max_value=-10)

st.markdown("##### 🛑 إدارة المخاطر (SL / TP)")
r1_in, r2_in, r3_in = st.columns(3)
risk_atr = r1_in.number_input("ATR المخاطر", value=14, min_value=1)
sl_mult = r2_in.number_input("وقف الخسارة (SL)", value=2.0, min_value=0.1, step=0.5)
rr_ratio = r3_in.number_input("الهدف (1:X RR)", value=2.0, min_value=0.5, step=0.5)

if st.button("🚀 تشغيل التقييم الآن"):
    with st.spinner(f"جاري فحص فريم {timeframe} بتوقيت المغرب..."):
        res = run_strategy(ticker, is_cse, timeframe, days_map[tf_choice], mode_choice, sens, atr_fac, use_ema200, swing_len, sym_atr_len, ob_lvl, os_lvl, risk_atr, sl_mult, rr_ratio, capital, leverage, is_spot, use_session)
    if res is None:
        st.warning(f"⚠️ بيانات فريم {timeframe} غير متوفرة حالياً لهذا الرمز.")
    else:
        trades, sig, price, sym_now, actual_days = res
        if timeframe in ["3m", "5m"] and days_map[tf_choice] > 7:
            st.caption(f"ℹ️ ملاحظة: المصدر المجاني يوفر آخر 7 أيام كحد أقصى لفريم {timeframe}.")
        if sig:
            st.markdown(f'<div class="stat-card card-signal"><b>⚡ صفقة نشطة: {sig["type"]}</b><br>🕒 {sig["time"]} | الدخول: {sig["entry"]} | الحالي: {sig["current"]}<br><span class="green-text">🎯 الهدف: {sig["tp"]}</span> | <span class="red-text">🛑 ستوب لوس: {sig["sl"]}</span></div>', unsafe_allow_html=True)
        else:
            st.info(f"⏳ لا توجد صفقة نشطة حالياً — السعر: **{price}** | قراءة مذبذب Symmetry: **{sym_now}**")
        wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
        win_rate = round((len(wins) / len(trades)) * 100, 1) if trades else 0
        tot_profit, tot_loss, net = round(sum(wins), 2), round(abs(sum(losses)), 2), round(sum(trades), 2)
        st.markdown(f'<div class="stat-card"><div class="card-title">نسبة النجاح (صافي بعد العمولات)</div><div class="card-value purple-text">{win_rate}%</div></div>', unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        r1.markdown(f'<div class="stat-card"><div class="card-title">عدد الصفقات</div><div class="card-value">{len(trades)}</div></div>', unsafe_allow_html=True)
        r2.markdown(f'<div class="stat-card card-green"><div class="card-title">الصفقات الرابحة</div><div class="card-value green-text">{len(wins)}</div></div>', unsafe_allow_html=True)
        r3, r4 = st.columns(2)
        r3.markdown(f'<div class="stat-card card-red"><div class="card-title">الصفقات الخاسرة</div><div class="card-value red-text">{len(losses)}</div></div>', unsafe_allow_html=True)
        r4.markdown(f'<div class="stat-card card-green"><div class="card-title">إجمالي الأرباح</div><div class="card-value green-text">+{tot_profit} {currency}</div></div>', unsafe_allow_html=True)
        r5, r6 = st.columns(2)
        r5.markdown(f'<div class="stat-card card-red"><div class="card-title">إجمالي الخسائر</div><div class="card-value red-text">-{tot_loss} {currency}</div></div>', unsafe_allow_html=True)
        r6.markdown(f'<div class="stat-card"><div class="card-title">صافي الربح (الرصيد: {round(capital+net, 2)})</div><div class="card-value {"green-text" if net>=0 else "red-text"}">{net} {currency}</div></div>', unsafe_allow_html=True)
