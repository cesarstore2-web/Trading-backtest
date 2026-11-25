import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="COINGLASS LIQUIDATION & CVD SNIPER", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px;background:rgba(0,255,102,0.12)}.pend{color:#00ccff;border:1px solid #00ccff;padding:3px 8px;border-radius:4px;background:rgba(0,204,255,0.12)}.wait{color:#888;border:1px solid #444;padding:3px 8px;border-radius:4px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}.pcard{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:12px;text-align:center;box-shadow:0 0 10px rgba(0,255,204,0.15)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>⚡ COINGLASS DATA: LIQUIDATION & CVD SNIPER (5M) ⚡</h2><p style='margin:0;color:#aaa;font-size:12px'>اصطياد ذيول التصفية (Liquidation Wicks) + تدفق السيولة (CVD / MFI) • شراء فقط 100$</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات السيولة والتصفية")
    vol_mult = st.slider("مضاعف انفجار السيولة (Volume Spike):", 1.5, 4.0, 2.2, 0.1)
    wick_ratio = st.slider("نسبة ذيل التصفية السفلي (% من الشمعة):", 30, 70, 45, 5)
    sl_mult = st.slider("وقف الخسارة (ATR x):", 1.2, 3.0, 1.8, 0.1)
    tp_mult = st.slider("جني الأرباح (ATR x):", 2.0, 5.0, 3.2, 0.1)
    st.info("💡 **فكرة CoinGlass:**\n\nالدخول بعد ضرب ستوبات المشترين (ذيل سفلي طويل + فوليوم عالي) وبدء امتصاص السيولة.")

c1, c2 = st.columns([2.5, 1.0])
mode = c1.selectbox("اختر العرض:", ["⚡ ALL COINS (رادار التصفية والسيولة)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث البيانات", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

@st.cache_data(ttl=60, show_spinner=False)
def fetch_data_30d(tickers_list):
    raw = yf.download(tickers_list, period="30d", interval="5m", group_by="ticker", progress=False)
    out = {}
    for tk in tickers_list:
        try:
            df = raw[tk].dropna() if len(tickers_list) > 1 else raw.dropna()
            out[tk] = df
        except Exception:
            out[tk] = pd.DataFrame()
    return out

def compute_signals(df5):
    df = df5.copy()
    # حساب مؤشرات السيولة والتصفية (MFI يمثل تدفق الأموال الحقيقي، و Volume Spike يمثل التصفية)
    df['MFI'] = ta.volume.money_flow_index(df['High'], df['Low'], df['Close'], df['Volume'], window=14)
    df['VOL_MA'] = df['Volume'].rolling(20).mean()
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    df['EMA21'] = ta.trend.ema_indicator(df['Close'], window=21)
    
    # حساب طول الذيل السفلي (علامة ضرب الستوبات وتصفية اللونج)
    candle_range = (df['High'] - df['Low']).replace(0, 1e-9)
    lower_wick = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['Wick_Pct'] = (lower_wick / candle_range) * 100
    
    # شرط 1: شمعة تصفية وامتصاص (ذيل سفلي طويل + فوليوم ضخم + إغلاق إيجابي أو فوق منتصف الشمعة)
    liq_sweep = (df['Wick_Pct'] >= wick_ratio) & (df['Volume'] >= df['VOL_MA'] * vol_mult) & (df['Close'] >= df['Low'] + 0.5 * candle_range)
    
    # شرط 2: انفجار سيولة شرائية (CVD / MFI Surge) مع اختراق متوسط 21
    cvd_surge = (df['MFI'] > 55) & (df['MFI'] > df['MFI'].shift(1) + 5) & (df['Close'] > df['Open']) & (df['Close'] > df['EMA21']) & (df['Volume'] >= df['VOL_MA'] * 1.5)
    
    df['Buy_Signal'] = liq_sweep | cvd_surge
    return df.dropna()

def simulate_period(df, candles_back):
    if len(df) < 50: return 0, 0, 0.0
    sub = df.iloc[-min(candles_back, len(df)-2):]
    wins, losses, net = 0, 0, 0.0
    in_pos, ep, slp, tpp = False, 0.0, 0.0, 0.0
    trade_cap = 100.0
    fee = 0.10 # عمولة 0.1%

    for i in range(1, len(sub)):
        bar = sub.iloc[i]
        if in_pos:
            if bar['Low'] <= slp:
                losses += 1
                net -= trade_cap * ((ep - slp) / ep) + fee
                in_pos = False
            elif bar['High'] >= tpp:
                wins += 1
                net += trade_cap * ((tpp - ep) / ep) - fee
                in_pos = False
            continue

        if bar['Buy_Signal']:
            in_pos = True
            ep = float(bar['Close'])
            atr = float(bar['ATR'])
            slp = ep - (sl_mult * atr)
            tpp = ep + (tp_mult * atr)

    return wins, losses, net

def process_coin(df5):
    if df5.empty or len(df5) < 100: return None
    df = compute_signals(df5)
    if len(df) < 30: return None

    last, curr = df.iloc[-2], df.iloc[-1]
    price = float(curr['Close'])
    atr = float(last['ATR'])
    mfi_val = float(last['MFI'])
    vol_ratio = float(last['Volume'] / max(last['VOL_MA'], 1e-9))

    if bool(last['Buy_Signal']):
        status = "BUY NOW"
        entry = price
    elif vol_ratio >= 1.3 and mfi_val > 45:
        status = "FUTURE BUY"
        # نقطة دخول مستقبلية عند تأكيد الاختراق أو إعادة اختبار القاع
        entry = price + (0.3 * atr) if last['Close'] > last['Open'] else price - (0.5 * atr)
    else:
        status = "WAIT"
        entry = float(last['Low'])

    sl = entry - (sl_mult * atr)
    tp = entry + (tp_mult * atr)

    w1, l1, n1 = simulate_period(df, 288)
    w7, l7, n7 = simulate_period(df, 2016)
    w30, l30, n30 = simulate_period(df, 8640)

    return {
        "price": price, "mfi": mfi_val, "vol_x": vol_ratio, "status": status,
        "entry": entry, "sl": sl, "tp": tp,
        "1d": (w1, l1, n1), "1w": (w7, l7, n7), "1m": (w30, l30, n30)
    }

tickers = list(pairs.values())
with st.spinner("⚡ جاري فحص تدفق السيولة وذيول التصفية (CoinGlass Logic)..."):
    all_data = fetch_data_30d(tickers)

if mode == "⚡ ALL COINS (رادار التصفية والسيولة)":
    rows = ""
    tw1, tl1, tn1 = 0, 0, 0.0
    tw7, tl7, tn7 = 0, 0, 0.0
    tw30, tl30, tn30 = 0, 0, 0.0

    for name, tk in pairs.items():
        res = process_coin(all_data.get(tk, pd.DataFrame()))
        if res:
            w1, l1, n1 = res['1d']; tw1 += w1; tl1 += l1; tn1 += n1
            w7, l7, n7 = res['1w']; tw7 += w7; tl7 += l7; tn7 += n7
            w30, l30, n30 = res['1m']; tw30 += w30; tl30 += l30; tn30 += n30

            if res['status'] == "BUY NOW":
                badge = "<span class='buy'>🟢 BUY NOW</span>"
            elif res['status'] == "FUTURE BUY":
                badge = "<span class='pend'>🔵 FUTURE BUY</span>"
            else:
                badge = "<span class='wait'>⏳ WAIT</span>"

            c_1m = "#00ff66" if n30 >= 0 else "#ff0055"
            v_col = "#00ff66" if res['vol_x'] >= 1.8 else "#aaa"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['price'])}</td><td>{res['mfi']:.1f}</td><td style='color:{v_col}'>{res['vol_x']:.1f}x</td><td>{badge}</td><td style='color:#00ccff'>{fmt(res['entry'])}</td><td style='color:#ff0055'>{fmt(res['sl'])}</td><td style='color:#00ff66'>{fmt(res['tp'])}</td><td style='color:{c_1m}'>${n30:+.2f}</td></tr>"

    if rows:
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم (24H)', tw1, tl1, tn1)}{render_card('📅 أداء 1 أسبوع (7D)', tw7, tl7, tn7)}{render_card('📅 أداء 1 شهر (30D)', tw30, tl30, tn30)}</div>", unsafe_allow_html=True)
        st.markdown(f"<table><thead><tr><th>العملة</th><th>السعر</th><th>MFI (CVD)</th><th>السيولة</th><th>الحالة</th><th>دخول (Entry)</th><th>وقف (SL)</th><th>هدف (TP)</th><th>ربح 30D</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    else:
        st.warning("تعذر جلب البيانات حالياً، اضغط تحديث البيانات.")
else:
    res = process_coin(all_data.get(pairs[mode], pd.DataFrame()))
    if res:
        w1, l1, n1 = res['1d']; w7, l7, n7 = res['1w']; w30, l30, n30 = res['1m']
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم', w1, l1, n1)}{render_card('📅 أداء 1 أسبوع', w7, l7, n7)}{render_card('📅 أداء 1 شهر', w30, l30, n30)}</div>", unsafe_allow_html=True)
        b_col = "#00ff66" if res['status']=="BUY NOW" else ("#00ccff" if res['status']=="FUTURE BUY" else "#ffcc00")
