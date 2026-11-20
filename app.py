import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="مُقيّم الاستراتيجيات الذكي (30m)", page_icon="⚡", layout="centered")

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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def apply_strategy_signals(df, strat_name):
    df['buy_sig'] = False
    df['sell_sig'] = False
    if "Bollinger" in strat_name:
        sma = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        upper = sma + (2.2 * std)
        lower = sma - (2.2 * std)
        rsi = calculate_rsi(df['Close'], 14)
        df['buy_sig'] = (df['Low'].shift(1) <= lower.shift(1)) & (rsi.shift(1) < 32) & (df['Close'] > lower)
        df['sell_sig'] = (df['High'].shift(1) >= upper.shift(1)) & (rsi.shift(1) > 68) & (df['Close'] < upper)
    elif "MACD" in strat_name:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        sig_line = macd.ewm(span=9, adjust=False).mean()
        ema200 = df['Close'].ewm(span=200, adjust=False).mean()
        df['buy_sig'] = (macd > sig_line) & (macd.shift(1) <= sig_line.shift(1)) & (macd < 0) & (df['Close'] > ema200)
        df['sell_sig'] = (macd < sig_line) & (macd.shift(1) >= sig_line.shift(1)) & (macd > 0) & (df['Close'] < ema200)
    else:
        atr = calculate_atr(df, 22)
        long_stop = df['High'].rolling(22).max() - (atr * 2.5)
        short_stop = df['Low'].rolling(22).min() + (atr * 2.5)
        dir_list = [1 for _ in range(len(df))]
        for i in range(1, len(df)):
            if df['Close'].iloc[i] > short_stop.iloc[i-1]:
                dir_list[i] = 1
            elif df['Close'].iloc[i] < long_stop.iloc[i-1]:
                dir_list[i] = -1
            else:
                dir_list[i] = dir_list[i-1]
        s_dir = pd.Series(dir_list, index=df.index)
        df['buy_sig'] = (s_dir == 1) & (s_dir.shift(1) == -1)
        df['sell_sig'] = (s_dir == -1) & (s_dir.shift(1) == 1)
    return df
def run_strategy(ticker, is_cse, period_days, strat_name, risk_atr_len, sl_mult, rr_ratio, capital, leverage, is_spot, use_session):
    df = yf.download(ticker, period=f"{period_days}d", interval="30m", progress=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')
    
    df = apply_strategy_signals(df, strat_name)
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
    return trades_pnl, sig, round(float(last_row['Close']), 4)

st.markdown("<h2 style='text-align:center;'>⚡ مُقيّم الاستراتيجيات (إطار 30 دقيقة)</h2>", unsafe_allow_html=True)

strat_choice = st.selectbox("🎯 اختر الاستراتيجية الذكية", [
    "Bollinger Sweep + RSI (اصطياد الارتداد والسيولة)",
    "MACD + EMA 200 (الزخم مع الاتجاه العام)",
    "Chandelier Exit (مخرج الثريا للاتجاهات)"
])

col_t, col_c = st.columns(2)
tf_choice = col_t.selectbox("فترة الاختبار", ["يومي (5 أيام)", "أسبوعي (14 يوم)", "شهري (30 يوم)", "أقصى مدة (60 يوم)"], index=3)
days_map = {"يومي (5 أيام)": 5, "أسبوعي (14 يوم)": 14, "شهري (30 يوم)": 30, "أقصى مدة (60 يوم)": 60}
cat_choice = col_c.selectbox("السوق", list(ASSETS.keys()))

asset_name = st.selectbox("اختر الأصل المالي", list(ASSETS[cat_choice]["items"].keys()))
ticker, currency, is_cse = ASSETS[cat_choice]["items"][asset_name], ASSETS[cat_choice]["currency"], ASSETS[cat_choice]["is_cse"]

use_session = st.checkbox("🕒 تفعيل فلتر التوقيت الذهبي (08:30 صباحاً - 20:00 مساءً بتوقيت المغرب)", value=True)

st.markdown("##### 💰 إدارة المحفظة ونوع التداول")
m1, m2, m3 = st.columns(3)
capital = m1.number_input(f"رأس المال ({currency})", value=100.0, min_value=10.0, step=50.0)
trade_mode = m2.selectbox("نوع التداول", ["سبوت (Spot)", "عقود آجلة (Futures)"]) if not is_cse else m2.selectbox("نوع التداول", ["أسهم (شراء فقط)"])
is_spot = True if ("سبوت" in trade_mode or is_cse) else False
leverage = m3.number_input("الرافعة المالية", value=1 if is_spot else 5, min_value=1, max_value=50, disabled=is_spot)

st.markdown("##### ⚙️ إعدادات وقف الخسارة والهدف (SL / TP)")
c3, c4, c5 = st.columns(3)
risk_atr = c3.number_input("ATR المخاطر", value=14, min_value=1)
sl_mult = c4.number_input("وقف الخسارة (SL)", value=2.0, min_value=0.1, step=0.5)
rr_ratio = c5.number_input("الهدف (1:X RR)", value=1.5, min_value=0.5, step=0.5)

if st.button("🚀 تشغيل التقييم (30 دقيقة)"):
    with st.spinner("جاري فحص شموع 30 دقيقة بتوقيت المغرب..."):
        res = run_strategy(ticker, is_cse, days_map[tf_choice], strat_choice, risk_atr, sl_mult, rr_ratio, capital, leverage, is_spot, use_session)
    if res is None:
        st.warning("⚠️ بيانات 30 دقيقة غير متوفرة حالياً لهذا الرمز.")
    else:
        trades, sig, price = res
        if sig:
            st.markdown(f'<div class="stat-card card-signal"><b>⚡ صفقة نشطة: {sig["type"]}</b><br>🕒 {sig["time"]} | الدخول: {sig["entry"]} | الحالي: {sig["current"]}<br><span class="green-text">🎯 الهدف: {sig["tp"]}</span> | <span class="red-text">🛑 ستوب لوس: {sig["sl"]}</span></div>', unsafe_allow_html=True)
        else:
            st.info(f"⏳ لا توجد صفقة نشطة حالياً — السعر الحالي: **{price}**")
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
