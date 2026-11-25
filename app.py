import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="COINGLASS RSI HEATMAP | 5M SCALPER", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px;background:rgba(0,255,102,0.12)}.sell{color:#ff0055;border:1px solid #ff0055;padding:3px 8px;border-radius:4px;background:rgba(255,0,85,0.12)}.wait{color:#ffcc00;border:1px solid #ffcc00;padding:3px 8px;border-radius:4px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:15px 0}.pcard{background:#131926;border:1px solid #00ffcc;border-radius:10px;padding:14px;text-align:center;box-shadow:0 0 12px rgba(0,255,204,0.15)}.ptitle{color:#00ffcc;font-size:14px;font-weight:bold;border-bottom:1px dashed #233044;padding-bottom:6px;margin-bottom:10px}.pstats{display:flex;justify-content:space-around;font-size:13px}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>🔥 COINGLASS RSI HEATMAP (5M) | 1D • 7D • 30D STATS 🔥</h2><p style='margin:0;color:#aaa;font-size:12px'>Wilder RSI 14 • اقتناص الخروج من مناطق التشبع (Overbought >70 / Oversold <30)</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات CoinGlass RSI")
    os_lvl = st.slider("منطقة Oversold (شراء عند الصعود فوق):", 20, 38, 30)
    ob_lvl = st.slider("منطقة Overbought (بيع عند الهبوط تحت):", 62, 80, 70)
    use_state_change = st.checkbox("تأكيد الخروج من المنطقة (State Change)", value=True)
    sl_mult = st.slider("وقف الخسارة (مضاعف ATR):", 1.0, 3.0, 1.5, 0.1)
    tp_mult = st.slider("جني الأرباح (مضاعف ATR):", 1.5, 4.0, 2.5, 0.1)
    trade_size = st.number_input("حجم كل صفقة ($):", value=100.0, step=10.0)

c1, c2 = st.columns([2.5, 1.0])
mode = c1.selectbox("اختر العرض:", ["🔥 ALL COINS HEATMAP (مسح شامل)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث البيانات", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

def heat_css(r):
    if r >= 70: return "background:#ff0055;color:#fff;"
    elif r >= 60: return "background:rgba(255,0,85,0.35);color:#ff0055;"
    elif r <= 30: return "background:#00ff66;color:#000;"
    elif r <= 40: return "background:rgba(0,255,102,0.35);color:#00ff66;"
    return "background:#1e2638;color:#a0aec0;"

def zone_name(r):
    if r >= 70: return "OVERBOUGHT"
    elif r >= 60: return "STRONG"
    elif r <= 30: return "OVERSOLD"
    elif r <= 40: return "WEAK"
    return "NEUTRAL"

# حساب Wilder Smoothing RSI 14 المطابق لـ CoinGlass
def calc_wilder_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=120, show_spinner=False)
def fetch_35d_5m(tickers_list):
    # جلب 35 يوماً على فريم 5 دقائق لتغطية 1 يوم، 1 أسبوع، و 1 شهر كامل
    raw = yf.download(tickers_list, period="35d", interval="5m", group_by="ticker", progress=False)
    out = {}
    for tk in tickers_list:
        try:
            df = raw[tk].dropna() if len(tickers_list) > 1 else raw.dropna()
            if len(df) > 50:
                df['RSI'] = calc_wilder_rsi(df['Close'], 14)
                tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
                df['ATR'] = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                out[tk] = df.dropna()
            else:
                out[tk] = pd.DataFrame()
        except Exception:
            out[tk] = pd.DataFrame()
    return out

def simulate_period(df, candles_count):
    sub = df.tail(candles_count + 2)
    if len(sub) < 10: return 0, 0, 0.0
    wins, losses, net = 0, 0, 0.0
    in_pos, side, ep, slp, tpp = False, "", 0.0, 0.0, 0.0

    for i in range(1, len(sub)):
        bar = sub.iloc[i]
        prev = sub.iloc[i-1]
        if in_pos:
            if side == "BUY":
                if bar['Low'] <= slp:
                    losses += 1; net -= trade_size * ((ep - slp) / ep) + (trade_size * 0.001); in_pos = False
                elif bar['High'] >= tpp:
                    wins += 1; net += trade_size * ((tpp - ep) / ep) - (trade_size * 0.001); in_pos = False
            elif side == "SELL":
                if bar['High'] >= slp:
                    losses += 1; net -= trade_size * ((slp - ep) / ep) + (trade_size * 0.001); in_pos = False
                elif bar['Low'] <= tpp:
                    wins += 1; net += trade_size * ((ep - tpp) / ep) - (trade_size * 0.001); in_pos = False
            continue

        r_cur, r_prv = float(bar['RSI']), float(prev['RSI'])
        if use_state_change:
            buy_sig = (r_prv <= os_lvl) and (r_cur > os_lvl)
            sell_sig = (r_prv >= ob_lvl) and (r_cur < ob_lvl)
        else:
            buy_sig = r_cur <= os_lvl
            sell_sig = r_cur >= ob_lvl

        if buy_sig or sell_sig:
            in_pos = True
            side = "BUY" if buy_sig else "SELL"
            ep = float(bar['Close'])
            atr_v = float(bar['ATR'])
            slp = ep - (sl_mult * atr_v) if side == "BUY" else ep + (sl_mult * atr_v)
            tpp = ep + (tp_mult * atr_v) if side == "BUY" else ep - (tp_mult * atr_v)

    return wins, losses, net

def analyze_coin(df):
    if df.empty or len(df) < 30: return None
    last, prev, curr = df.iloc[-2], df.iloc[-3], df.iloc[-1]
    r_cur, r_prv = float(last['RSI']), float(prev['RSI'])
    price, atr = float(curr['Close']), float(last['ATR'])

    if use_state_change:
        b_sig = (r_prv <= os_lvl) and (r_cur > os_lvl)
        s_sig = (r_prv >= ob_lvl) and (r_cur < ob_lvl)
    else:
        b_sig = r_cur <= os_lvl
        s_sig = r_cur >= ob_lvl

    sig = "BUY" if b_sig else ("SELL" if s_sig else "WAIT")
    sl = price - (sl_mult * atr) if sig == "BUY" else (price + (sl_mult * atr) if sig == "SELL" else 0.0)
    tp = price + (tp_mult * atr) if sig == "BUY" else (price - (tp_mult * atr) if sig == "SELL" else 0.0)

    # حساب الفترات الثلاث: 1 يوم (288 شمعة)، 1 أسبوع (2016 شمعة)، 1 شهر (8640 شمعة)
    s_1d = simulate_period(df, 288)
    s_7d = simulate_period(df, 2016)
    s_30d = simulate_period(df, 8640)

    return {"price": price, "rsi": r_cur, "sig": sig, "sl": sl, "tp": tp, "1d": s_1d, "7d": s_7d, "30d": s_30d}

def render_period_cards(d1, d7, d30):
    def card_html(title, stats):
        w, l, net = stats
        wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
        nc = "#00ff66" if net >= 0 else "#ff0055"
        return f"<div class='pcard'><div class='ptitle'>{title}</div><div class='pstats'><span><small style='color:#aaa'>WIN</small><br><b style='color:#00ff66'>{w} 🟢</b></span><span><small style='color:#aaa'>LOSS</small><br><b style='color:#ff0055'>{l} 🔴</b></span><span><small style='color:#aaa'>RATE</small><br><b style='color:#00ffcc'>{wr:.1f}%</b></span><span><small style='color:#aaa'>NET PNL</small><br><b style='color:{nc}'>${net:+.2f}</b></span></div></div>"
    st.markdown(f"<div class='grid3'>{card_html('📅 1 DAY (24H)', d1)}{card_html('📆 1 WEEK (7D)', d7)}{card_html('🗓️ 1 MONTH (30D)', d30)}</div>", unsafe_allow_html=True)

tickers = list(pairs.values())
with st.spinner("🔥 جاري تحميل بيانات 30 يوماً لفريم 5 دقائق من yfinance..."):
    data_map = fetch_35d_5m(tickers)

if mode == "🔥 ALL COINS HEATMAP (مسح شامل)":
    rows = ""
    t1d, t7d, t30d = [0, 0, 0.0], [0, 0, 0.0], [0, 0, 0.0]
    for name, tk in pairs.items():
        res = analyze_coin(data_map.get(tk, pd.DataFrame()))
        if res:
            for idx in range(3):
                t1d[idx] += res['1d'][idx]
                t7d[idx] += res['7d'][idx]
                t30d[idx] += res['30d'][idx]
            s_cls = "buy" if res['sig']=="BUY" else ("sell" if res['sig']=="SELL" else "wait")
            sl_s = fmt(res['sl']) if res['sig']!="WAIT" else "-"
            tp_s = fmt(res['tp']) if res['sig']!="WAIT" else "-"
            c30 = "#00ff66" if res['30d'][2] >= 0 else "#ff0055"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['price'])}</td><td style='{heat_css(res['rsi'])}'>{res['rsi']:.1f} ({zone_name(res['rsi'])})</td><td><span class='{s_cls}'>{res['sig']}</span></td><td style='color:#ff0055'>{sl_s}</td><td style='color:#00ff66'>{tp_s}</td><td>{res['1d'][0]}W/{res['1d'][1]}L</td><td>{res['7d'][0]}W/{res['7d'][1]}L</td><td style='color:{c30}'>${res['30d'][2]:+.2f}</td></tr>"
    if rows:
        render_period_cards(t1d, t7d, t30d)
        st.markdown(f"<table><thead><tr><th>PAIR</th><th>PRICE</th><th>5M RSI ZONE</th><th>SIGNAL</th><th>SL</th><th>TP</th><th>1D W/L</th><th>7D W/L</th><th>30D NET</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    else:
        st.warning("تعذر جلب البيانات حالياً، اضغط تحديث البيانات.")
else:
    res = analyze_coin(data_map.get(pairs[mode], pd.DataFrame()))
    if res:
        render_period_cards(res['1d'], res['7d'], res['30d'])
