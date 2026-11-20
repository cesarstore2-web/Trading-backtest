import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="مُقيّم الاستراتيجيات", page_icon="⚡", layout="centered")

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

def calculate_atr(df, length):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(length).mean()

def calculate_supertrend(df, atr_len=10, factor=1.0):
    atr = calculate_atr(df, atr_len)
    hl2 = (df['High'] + df['Low']) / 2
    upper, lower = hl2 + (factor * atr), hl2 - (factor * atr)
    uptrend = [True] * len(df)
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > upper.iloc[i-1]: uptrend[i] = True
        elif df['Close'].iloc[i] < lower.iloc[i-1]: uptrend[i] = False
        else:
            uptrend[i] = uptrend[i-1]
            if uptrend[i] and lower.iloc[i] < lower.iloc[i-1]: lower.iloc[i] = lower.iloc[i-1]
            if not uptrend[i] and upper.iloc[i] > upper.iloc[i-1]: upper.iloc[i] = upper.iloc[i-1]
    df['st_up'] = uptrend
    return df
def run_strategy(ticker, is_cse, period_days, st_len, st_fac, risk_atr_len, sl_mult, rr_ratio, capital, leverage, is_spot):
    df = yf.download(ticker, period=f"{period_days}d", interval="15m", progress=False)
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if df.index.tz is None: df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')
    if is_cse: df = df.between_time('09:30', '15:30')
    df = calculate_supertrend(df, st_len, st_fac)
    df['risk_atr'] = calculate_atr(df, risk_atr_len)
    fee_rate = 0.002 if (is_spot or is_cse) else 0.001
    pos_size = capital * (1 if (is_spot or is_cse) else leverage)
    trades_pnl, equity, trade_log = [], [capital], []
    in_trade, t_type, entry, sl, tp, entry_time = False, None, 0, 0, 0, ""
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        c_time = df.index[i].strftime("%Y-%m-%d %H:%M")
        if pd.isna(row['risk_atr']): continue
        if in_trade:
            if t_type == "BUY" and (row['Low'] <= sl or row['High'] >= tp):
                exit_p = sl if row['Low'] <= sl else tp
                pnl = (pos_size * ((exit_p - entry) / entry)) - (pos_size * fee_rate)
                trades_pnl.append(pnl); equity.append(equity[-1] + pnl)
                trade_log.append({"النوع": "شراء 🟢", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "ربح ✅" if pnl > 0 else "خسارة ❌", "النتيجة": round(pnl, 2)})
                in_trade = False
            elif t_type == "SELL" and (row['High'] >= sl or row['Low'] <= tp):
                exit_p = sl if row['High'] >= sl else tp
                pnl = (pos_size * ((entry - exit_p) / entry)) - (pos_size * fee_rate)
                trades_pnl.append(pnl); equity.append(equity[-1] + pnl)
                trade_log.append({"النوع": "بيع 🔴", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "ربح ✅" if pnl > 0 else "خسارة ❌", "النتيجة": round(pnl, 2)})
                in_trade = False
        if not in_trade:
            if row['st_up'] and not prev['st_up']:
                entry, dist = float(row['Close']), float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry - dist, entry + (dist * rr_ratio), "BUY", c_time, True
            elif not (is_spot or is_cse) and not row['st_up'] and prev['st_up']:
                entry, dist = float(row['Close']), float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry + dist, entry - (dist * rr_ratio), "SELL", c_time, True
    last_row = df.iloc[-1]
    sig = {"type": "شراء 🟢" if t_type == "BUY" else "بيع 🔴", "time": entry_time, "entry": round(entry, 4), "tp": round(tp, 4), "sl": round(sl, 4), "current": round(float(last_row['Close']), 4)} if in_trade else None
    return trades_pnl, equity, trade_log, sig, ("صاعد 🟢" if last_row['st_up'] else "هابط 🔴"), round(float(last_row['Close']), 4)

st.markdown("<h2 style='text-align:center;'>⚡ مُقيّم الاستراتيجيات والصفقات</h2>", unsafe_allow_html=True)
col_t, col_c = st.columns(2)
tf_choice = col_t.selectbox("فترة الاختبار", ["يومي (5 أيام)", "أسبوعي (14 يوم)", "شهري (30 يوم)", "أقصى مدة (60 يوم)"], index=2)
days_map = {"يومي (5 أيام)": 5, "أسبوعي (14 يوم)": 14, "شهري (30 يوم)": 30, "أقصى مدة (60 يوم)": 60}
cat_choice = col_c.selectbox("السوق", list(ASSETS.keys()))
asset_name = st.selectbox("اختر الأصل المالي", list(ASSETS[cat_choice]["items"].keys()))
ticker, currency, is_cse = ASSETS[cat_choice]["items"][asset_name], ASSETS[cat_choice]["currency"], ASSETS[cat_choice]["is_cse"]

st.markdown("##### 💰 إدارة المحفظة ونوع التداول")
m1, m2, m3 = st.columns(3)
capital = m1.number_input(f"رأس المال ({currency})", value=100.0, min_value=10.0, step=50.0)
trade_mode = m2.selectbox("نوع التداول", ["سبوت (Spot)", "عقود آجلة (Futures)"]) if not is_cse else m2.selectbox("نوع التداول", ["أسهم (شراء فقط)"])
is_spot = True if ("سبوت" in trade_mode or is_cse) else False
leverage = m3.number_input("الرافعة المالية", value=1 if is_spot else 5, min_value=1, max_value=50, disabled=is_spot)

st.markdown("##### ⚙️ إعدادات المؤشر وإدارة المخاطر (SL / TP)")
c1, c2 = st.columns(2)
st_len = c1.number_input("ATR Length (Supertrend)", value=10, min_value=1)
st_fac = c2.number_input("Factor (Supertrend)", value=1.0, min_value=0.1, step=0.5)
c3, c4, c5 = st.columns(3)
risk_atr = c3.number_input("ATR Length (Risk)", value=14, min_value=1)
sl_mult = c4.number_input("وقف الخسارة (ATR SL)", value=2.0, min_value=0.1, step=0.5)
rr_ratio = c5.number_input("الهدف (1:X RR)", value=2.0, min_value=0.5, step=0.5)

if st.button("🚀 تشغيل التقييم واستخراج الصفقات"):
    with st.spinner("جاري التحليل..."):
        res = run_strategy(ticker, is_cse, days_map[tf_choice], st_len, st_fac, risk_atr, sl_mult, rr_ratio, capital, leverage, is_spot)
    if res is None:
        st.warning("⚠️ بيانات 15 دقيقة غير متوفرة حالياً لهذا الرمز.")
    else:
        trades, equity, trade_log, sig, trend, price = res
        if sig:
            st.markdown(f'<div class="stat-card card-signal"><b>⚡ صفقة نشطة: {sig["type"]}</b><br>🕒 {sig["time"]} | الدخول: {sig["entry"]} | الحالي: {sig["current"]}<br><span class="green-text">🎯 الهدف: {sig["tp"]}</span> | <span class="red-text">🛑 ستوب لوس: {sig["sl"]}</span></div>', unsafe_allow_html=True)
        else:
            st.info(f"⏳ لا توجد صفقة نشطة حالياً — الاتجاه: **{trend}** | السعر: **{price}**")
        wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
        win_rate = round((len(wins) / len(trades)) * 100, 1) if trades else 0
        net = round(sum(trades), 2)
        st.markdown(f'<div class="stat-card"><div class="card-title">نسبة النجاح (صافي بعد العمولات)</div><div class="card-value purple-text">{win_rate}%</div></div>', unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        r1.markdown(f'<div class="stat-card"><div class="card-title">عدد الصفقات</div><div class="card-value">{len(trades)}</div></div>', unsafe_allow_html=True)
        r2.markdown(f'<div class="stat-card card-green"><div class="card-title">الرابحة</div><div class="card-value green-text">{len(wins)}</div></div>', unsafe_allow_html=True)
        r3, r4 = st.columns(2)
        r3.markdown(f'<div class="stat-card card-red"><div class="card-title">الخاسرة</div><div class="card-value red-text">{len(losses)}</div></div>', unsafe_allow_html=True)
        r4.markdown(f'<div class="stat-card"><div class="card-title">صافي الربح (الرصيد: {round(capital+net, 2)})</div><div class="card-value {"green-text" if net>=0 else "red-text"}">{net} {currency}</div></div>', unsafe_allow_html=True)
        fig = go.Figure(go.Scatter(y=equity, mode='lines', line=dict(color='#a855f7', width=3), fill='tozeroy', fillcolor='rgba(168, 85, 247, 0.15)'))
        fig.update_layout(title="منحنى نمو رأس المال", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'), height=220, margin=dict(l=10, r=10, t=35, b=10))
        st.plotly_chart(fig, use_container_width=True)
        if trade_log:
            st.markdown("### 📋 سجل الصفقات")
            st.dataframe(pd.DataFrame(trade_log)[::-1], use_container_width=True, hide_index=True)
