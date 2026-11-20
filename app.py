import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Supertrend Multi-TP", page_icon="⚡", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.stApp { background: #09090f; color: #ffffff; direction: rtl; text-align: right; }
.stat-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 14px; padding: 14px; margin-bottom: 10px; text-align: center; }
.card-green { border-color: #10b981; background: rgba(16,185,129,0.1); }
.card-red { border-color: #ef4444; background: rgba(239,68,68,0.1); }
.card-signal { border-color: #a855f7; background: rgba(168,85,247,0.12); text-align: right; padding: 15px; }
.card-title { font-size: 13px; color: #a1a1aa; }
.card-value { font-size: 22px; font-weight: 800; }
.green-text { color: #10b981; } .red-text { color: #ef4444; } .purple-text { color: #a855f7; }
</style>
""", unsafe_allow_html=True)

ASSETS = {
    "العملات الرقمية": {"currency": "USDT", "is_cse": False, "items": {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "XRPUSDT": "XRP-USD", "ADAUSDT": "ADA-USD", "XLMUSDT": "XLM-USD"}},
    "الذهب": {"currency": "USDT", "is_cse": False, "items": {"الذهب (XAU)": "GC=F", "PAXGUSDT": "PAXG-USD"}},
    "بورصة الدار البيضاء": {"currency": "MAD", "is_cse": True, "items": {"ATW - التجاري وفا": "ATW.CS", "BCP - الشعبي": "BCP.CS", "AKT - أكديطال": "AKT.CS", "MNG - مناجم": "MNG.CS", "TGC - TGCC": "TGC.CS", "ADH - الضحى": "ADH.CS", "MSA - مرسى المغرب": "MSA.CS"}}
}

def calc_atr(df, length=14):
    tr = pd.concat([df['High']-df['Low'], np.abs(df['High']-df['Close'].shift()), np.abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def run_strategy(ticker, is_cse, timeframe, period_days, capital, is_spot):
    df = yf.download(ticker, period=f"{period_days}d", interval=timeframe, progress=False)
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df.index = (df.index.tz_localize('UTC') if df.index.tz is None else df.index).tz_convert('Africa/Casablanca')

    atr = calc_atr(df, 10)
    hl2 = (df['High'] + df['Low']) / 2
    upper, lower = hl2 + 3.0 * atr, hl2 - 3.0 * atr
    uptrend = [True] * len(df)
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > upper.iloc[i-1]: uptrend[i] = True
        elif df['Close'].iloc[i] < lower.iloc[i-1]: uptrend[i] = False
        else:
            uptrend[i] = uptrend[i-1]
            if uptrend[i] and lower.iloc[i] < lower.iloc[i-1]: lower.iloc[i] = lower.iloc[i-1]
            if not uptrend[i] and upper.iloc[i] > upper.iloc[i-1]: upper.iloc[i] = upper.iloc[i-1]

    df['st_up'] = uptrend
    df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['buy_sig'] = df['st_up'] & (~df['st_up'].shift(1).fillna(False)) & (df['Close'] > df['ema200'])
    df['sell_sig'] = (~df['st_up']) & (df['st_up'].shift(1).fillna(True)) & (df['Close'] < df['ema200'])
    df['atr'] = calc_atr(df, 14)

    fee = 0.002 if (is_spot or is_cse) else 0.001
    part = capital / 3.0
    pnl_list, history = [], []
    in_trade, t_type, entry, sl, tp1, tp2, tp3, e_time = False, None, 0, 0, 0, 0, 0, ""
    h1, h2, cur_pnl = False, False, 0.0

    for i in range(1, len(df)):
        r, c_time = df.iloc[i], df.index[i].strftime("%Y-%m-%d %H:%M")
        if pd.isna(r['atr']): continue

        if in_trade:
            if t_type == "BUY":
                if r['Low'] <= sl:
                    rem = 3 - int(h1) - int(h2)
                    tot = cur_pnl + (part * rem) * ((sl - entry) / entry - fee)
                    pnl_list.append(tot)
                    history.append({"النوع": "شراء 🟢", "الدخول": e_time, "الخروج": c_time, "سعر الدخول": round(entry, 3), "سعر الخروج": round(sl, 3), "الربح": round(tot, 2)})
                    in_trade = False
                else:
                    if not h1 and r['High'] >= tp1: h1, cur_pnl, sl = True, cur_pnl + part*((tp1-entry)/entry - fee), entry
                    if not h2 and r['High'] >= tp2: h2, cur_pnl = True, cur_pnl + part*((tp2-entry)/entry - fee)
                    if r['High'] >= tp3:
                        tot = cur_pnl + part*((tp3-entry)/entry - fee)
                        pnl_list.append(tot)
                        history.append({"النوع": "شراء 🟢", "الدخول": e_time, "الخروج": c_time, "سعر الدخول": round(entry, 3), "سعر الخروج": round(tp3, 3), "الربح": round(tot, 2)})
                        in_trade = False
            elif t_type == "SELL":
                if r['High'] >= sl:
                    rem = 3 - int(h1) - int(h2)
                    tot = cur_pnl + (part * rem) * ((entry - sl) / entry - fee)
                    pnl_list.append(tot)
                    history.append({"النوع": "بيع 🔴", "الدخول": e_time, "الخروج": c_time, "سعر الدخول": round(entry, 3), "سعر الخروج": round(sl, 3), "الربح": round(tot, 2)})
                    in_trade = False
                else:
                    if not h1 and r['Low'] <= tp1: h1, cur_pnl, sl = True, cur_pnl + part*((entry-tp1)/entry - fee), entry
                    if not h2 and r['Low'] <= tp2: h2, cur_pnl = True, cur_pnl + part*((entry-tp2)/entry - fee)
                    if r['Low'] <= tp3:
                        tot = cur_pnl + part*((entry-tp3)/entry - fee)
                        pnl_list.append(tot)
                        history.append({"النوع": "بيع 🔴", "الدخول": e_time, "الخروج": c_time, "سعر الدخول": round(entry, 3), "سعر الخروج": round(tp3, 3), "الربح": round(tot, 2)})
                        in_trade = False

        if not in_trade:
            a = float(r['atr'])
            if r['buy_sig']:
                entry, sl, tp1, tp2, tp3 = float(r['Close']), float(r['Close'])-1.5*a, float(r['Close'])+a, float(r['Close'])+2*a, float(r['Close'])+3*a
                t_type, e_time, in_trade, h1, h2, cur_pnl = "BUY", c_time, True, False, False, 0.0
            elif not (is_spot or is_cse) and r['sell_sig']:
                entry, sl, tp1, tp2, tp3 = float(r['Close']), float(r['Close'])+1.5*a, float(r['Close'])-a, float(r['Close'])-2*a, float(r['Close'])-3*a
                t_type, e_time, in_trade, h1, h2, cur_pnl = "SELL", c_time, True, False, False, 0.0

    wins = len([p for p in pnl_list if p > 0])
    return {"wins": wins, "losses": len(pnl_list)-wins, "net": sum(pnl_list), "in_trade": in_trade, "t_type": t_type, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "history": history}

st.title("⚡ Supertrend & EMA 200")
c1, c2 = st.columns(2)
cat = c1.selectbox("السوق", list(ASSETS.keys()))
asset = c1.selectbox("الأصل", list(ASSETS[cat]["items"].keys()))
periods = {"7 أيام": 7, "14 يوماً": 14, "30 يوماً (شهر)": 30, "90 يوماً": 90, "سنة": 365}
p_label = c2.selectbox("الفترة", list(periods.keys()), index=2)
p_days = periods[p_label]
tfs = ["15m", "30m", "1h", "4h", "1d"] if p_days <= 60 else ["1h", "4h", "1d"]
tf = c2.selectbox("الفريم", tfs, index=min(2, len(tfs)-1))
cap = st.number_input(f"رأس المال ({ASSETS[cat]['currency']})", value=1000.0)
spot = st.checkbox("شراء فقط (Spot)", value=True)

res = run_strategy(ASSETS[cat]["items"][asset], ASSETS[cat]["is_cse"], tf, p_days, cap, spot)
if not res:
    st.error("بيانات غير كافية، جرب فريم أكبر (مثل 1h أو 1d).")
else:
    curr = ASSETS[cat]["currency"]
    cls = "card-green" if res["net"] >= 0 else "card-red"
    t_cls = "green-text" if res["net"] >= 0 else "red-text"
    st.markdown(f'<div class="stat-card {cls}"><div class="card-title">الربح الصافي ({p_label})</div><div class="card-value {t_cls}">{res["net"]:.2f} {curr}</div></div>', unsafe_allow_html=True)
    r1, r2 = st.columns(2)
    r1.markdown(f'<div class="stat-card card-green"><div class="card-title">الصفقات الناجحة</div><div class="card-value green-text">{res["wins"]}</div></div>', unsafe_allow_html=True)
    r2.markdown(f'<div class="stat-card card-red"><div class="card-title">الصفقات الخاسرة</div><div class="card-value red-text">{res["losses"]}</div></div>', unsafe_allow_html=True)
    if res["in_trade"]:
        st.markdown(f'<div class="stat-card card-signal"><b>🔔 صفقة مفتوحة ({res["t_type"]})</b> | دخول: {res["entry"]:.3f} | وقف: {res["sl"]:.3f} | أهداف: {res["tp1"]:.3f} / {res["tp2"]:.3f} / {res["tp3"]:.3f}</div>', unsafe_allow_html=True)
    if res["history"]:
        st.dataframe(pd.DataFrame(res["history"]).iloc[::-1], use_container_width=True, hide_index=True)
