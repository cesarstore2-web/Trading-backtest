import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="SPOT HALAL SNIPER | 1H BOUNCE", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px;background:rgba(0,255,102,0.12)}.pend{color:#00ccff;border:1px solid #00ccff;padding:3px 8px;border-radius:4px;background:rgba(0,204,255,0.12)}.wait{color:#888;border:1px solid #444;padding:3px 8px;border-radius:4px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}.pcard{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:12px;text-align:center;box-shadow:0 0 10px rgba(0,255,204,0.15)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>☪️ SPOT HALAL SNIPER • 1H BOLLINGER BOUNCE ☪️</h2><p style='margin:0;color:#aaa;font-size:12px'>تداول فوري (Spot) شراء فقط • اصطياد الارتداد من القيعان (Bollinger + RSI) • 100$ للصفقة</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات السبوت (Spot 1H)")
    bb_dev = st.slider("انحراف البولينجر باند (Bollinger Std):", 1.8, 2.6, 2.0, 0.1)
    rsi_buy = st.slider("حد شراء التشبع (RSI 1H <=):", 25, 42, 35)
    sl_mult = st.slider("وقف الخسارة (ATR x):", 1.5, 3.5, 2.2, 0.1)
    st.info("☪️ **نظام Spot 100%:**\n\nشراء من الحد السفلي للبولينجر وبيع الهدف عند خط المنتصف (SMA 20).")

c1, c2 = st.columns([2.5, 1.0])
mode = c1.selectbox("اختر العرض:", ["☪️ ALL COINS (توصيات السبوت الفورية والمستقبلية)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث البيانات", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

@st.cache_data(ttl=120, show_spinner=False)
def fetch_data_60d(tickers_list):
    raw = yf.download(tickers_list, period="60d", interval="1h", group_by="ticker", progress=False)
    out = {}
    for tk in tickers_list:
        try:
            df = raw[tk].dropna() if len(tickers_list) > 1 else raw.dropna()
            out[tk] = df
        except Exception:
            out[tk] = pd.DataFrame()
    return out

def prepare_spot_1h(df1h):
    df = df1h.copy()
    bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=bb_dev)
    df['BB_LOW'] = bb.bollinger_lband()
    df['BB_MID'] = bb.bollinger_mavg()
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    
    # شرط الشراء في السبوت:
    # كسر أو ملامسة الحد السفلي للبولينجر + تشبع RSI + إغلاق شمعة ارتداد خضراء
    df['Spot_Buy'] = (
        (df['Low'] <= df['BB_LOW']) &
        (df['RSI'] <= rsi_buy) &
        (df['Close'] > df['Open'])
    )
    return df.dropna()

def simulate_spot(df, hours_back):
    if len(df) < 30: return 0, 0, 0.0
    sub = df.iloc[-min(hours_back, len(df)-2):]
    wins, losses, net = 0, 0, 0.0
    in_pos, ep, slp, tpp = False, 0.0, 0.0, 0.0
    trade_cap = 100.0
    fee = 0.10 # عمولة السبوت 0.1%

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

        if bar['Spot_Buy']:
            in_pos = True
            ep = float(bar['Close'])
            atr = float(bar['ATR'])
            slp = ep - (sl_mult * atr)
            # الهدف هو خط منتصف البولينجر (SMA 20) أو 1.8x ATR أيهما أكبر
            tpp = max(float(bar['BB_MID']), ep + (1.8 * atr))

    return wins, losses, net

def process_coin(df1h):
    if df1h.empty or len(df1h) < 40: return None
    df = prepare_spot_1h(df1h)
    if len(df) < 20: return None

    last, curr = df.iloc[-2], df.iloc[-1]
    price = float(curr['Close'])
    atr = float(last['ATR'])
    bb_low = float(last['BB_LOW'])
    bb_mid = float(last['BB_MID'])
    rsi_v = float(last['RSI'])

    if bool(last['Spot_Buy']):
        status = "BUY SPOT NOW"
        entry = price
    elif price <= bb_low * 1.015:
        status = "BUY LIMIT (SOON)"
        entry = bb_low # أمر شراء معلق عند الحد السفلي للبولينجر
    else:
        status = "WAIT"
        entry = bb_low # أقرب دعم مستقبلي للشراء المعلق

    sl = entry - (sl_mult * atr)
    tp = max(bb_mid, entry + (1.8 * atr))

    w1, l1, n1 = simulate_spot(df, 24)
    w7, l7, n7 = simulate_spot(df, 168)
    w30, l30, n30 = simulate_spot(df, 720)

    return {
        "price": price, "rsi": rsi_v, "status": status,
        "entry": entry, "sl": sl, "tp": tp,
        "1d": (w1, l1, n1), "1w": (w7, l7, n7), "1m": (w30, l30, n30)
    }

tickers = list(pairs.values())
with st.spinner("☪️ جاري فحص فرص التداول الفوري (Spot 1H)..."):
    all_data = fetch_data_60d(tickers)

if mode == "☪️ ALL COINS (توصيات السبوت الفورية والمستقبلية)":
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

            if res['status'] == "BUY SPOT NOW":
                badge = "<span class='buy'>🟢 BUY SPOT</span>"
            elif res['status'] == "BUY LIMIT (SOON)":
                badge = "<span class='pend'>🔵 BUY LIMIT</span>"
            else:
                badge = "<span class='wait'>⏳ WAIT</span>"

            c_1m = "#00ff66" if n30 >= 0 else "#ff0055"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['price'])}</td><td>{res['rsi']:.1f}</td><td>{badge}</td><td style='color:#00ccff'>{fmt(res['entry'])}</td><td style='color:#ff0055'>{fmt(res['sl'])}</td><td style='color:#00ff66'>{fmt(res['tp'])}</td><td style='color:{c_1m}'>${n30:+.2f}</td></tr>"

    if rows:
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم (24H)', tw1, tl1, tn1)}{render_card('📅 أداء 1 أسبوع (7D)', tw7, tl7, tn7)}{render_card('📅 أداء 1 شهر (30D)', tw30, tl30, tn30)}</div>", unsafe_allow_html=True)
        st.markdown(f"<table><thead><tr><th>العملة</th><th>السعر</th><th>RSI 1H</th><th>الحالة</th><th>شراء (Buy Limit)</th><th>وقف (SL)</th><th>بيع (TP)</th><th>ربح 30D</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
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
        b_col = "#00ff66" if res['status']=="BUY SPOT NOW" else ("#00ccff" if res['status']=="BUY LIMIT (SOON)" else "#ffcc00")
        st.markdown(f"<div style='border:2px solid {b_col};border-radius:10px;padding:20px;text-align:center;background:#131926'><p style='margin:0;color:#aaa'>{mode} • SPOT 1H • RSI: {res['rsi']:.1f}</p><h1 style='font-size:48px;margin:8px 0;color:{b_col}'>{res['status']}</h1><p style='font-size:16px'><b>شراء مستقبلي (BUY LIMIT): <span style='color:#00ccff'>{fmt(res['entry'])}</span> &nbsp;|&nbsp; SL: <span style='color:#ff0055'>{fmt(res['sl'])}</span> &nbsp;|&nbsp; TP: <span style='color:#00ff66'>{fmt(res['tp'])}</span></b></p></div>", unsafe_allow_html=True)
