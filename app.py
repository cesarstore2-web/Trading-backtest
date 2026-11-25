import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="CRYPTO SCALPING AI", layout="centered")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:15px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px}.sell{color:#ff0055;border:1px solid #ff0055;padding:3px 8px;border-radius:4px}.wait{color:#ffcc00;border:1px solid #ffcc00;padding:3px 8px;border-radius:4px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:15px 0}.card{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:10px;text-align:center}.box-buy{border:2px solid #00ff66;border-radius:10px;padding:20px;text-align:center;background:rgba(0,255,102,0.08)}.box-sell{border:2px solid #ff0055;border-radius:10px;padding:20px;text-align:center;background:rgba(255,0,85,0.08)}.box-wait{border:2px solid #ffcc00;border-radius:10px;padding:20px;text-align:center;background:rgba(255,204,0,0.08)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>⚡ CRYPTO SCALPING AI ⚡</h2><p style='margin:0;color:#aaa;font-size:12px'>1m / 3m / 5m / 15m • LIVE RADAR & 24H STATS</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

c1, c2, c3 = st.columns([2, 1.1, 1.4])
mode = c1.selectbox("PAIR", ["🌐 ALL COINS"] + list(pairs.keys()), label_visibility="collapsed")
tf = c2.selectbox("TF", ["1m", "3m", "5m", "15m"], index=1, label_visibility="collapsed")
c3.button("🔄 SCAN", use_container_width=True, type="primary")

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

def get_data(ticker, interval):
    if interval == "3m":
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df.dropna().resample('3min').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
    df = yf.download(ticker, period="1d" if interval=="1m" else "5d", interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df.dropna()

def analyze(df, interval):
    df['E9'] = ta.trend.ema_indicator(df['Close'], 9)
    df['E21'] = ta.trend.ema_indicator(df['Close'], 21)
    df['E50'] = ta.trend.ema_indicator(df['Close'], 50)
    df['RSI'] = ta.momentum.rsi(df['Close'], 7)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], 14)
    df = df.dropna()
    if len(df) < 20: return None

    last, curr = df.iloc[-2], df.iloc[-1]
    p, atr = curr['Close'], last['ATR']
    conds = [
        ("1. EMA 9/21 CROSS", last['E9'] > last['E21']),
        ("2. EMA 50 TREND", p > last['E50']),
        ("3. RSI 7 MOMENTUM", last['RSI'] > 50),
        ("4. CANDLE BODY", last['Close'] > last['Open']),
        ("5. VOLATILITY ATR", last['ATR'] >= df['ATR'].tail(15).mean()*0.9),
        ("6. RSI FILTER", 25 < last['RSI'] < 75)
    ]
    bull = sum(x[1] for x in conds)
    dec = "BUY" if bull >= 4 else ("SELL" if (6-bull) >= 4 else "WAIT")
    conf = int((max(bull, 6-bull)/6)*100) if dec != "WAIT" else 50
    sl = p - 1.2*atr if dec=="BUY" else (p + 1.2*atr if dec=="SELL" else 0)
    tp = p + 2.0*atr if dec=="BUY" else (p - 2.0*atr if dec=="SELL" else 0)

    # Backtest 24H
    cmap = {"1m":1440, "3m":480, "5m":288, "15m":96}
    lb = min(cmap.get(interval, 480), len(df)-20)
    w, l, net, pos, side, ep, slp, tpp = 0, 0, 0.0, False, "", 0, 0, 0
    for i in range(len(df)-lb, len(df)-1):
        r = df.iloc[i]
        if pos:
            if side=="BUY" and (r['Low']<=slp or r['High']>=tpp):
                win = r['High']>=tpp and r['Low']>slp
                w += int(win); l += int(not win)
                net += (100*((tpp-ep)/ep) if win else -100*((ep-slp)/ep)) - 0.2
                pos = False
            elif side=="SELL" and (r['High']>=slp or r['Low']<=tpp):
                win = r['Low']<=tpp and r['High']<slp
                w += int(win); l += int(not win)
                net += (100*((ep-tpp)/ep) if win else -100*((slp-ep)/ep)) - 0.2
                pos = False
            continue
        b = sum([r['E9']>r['E21'], r['Close']>r['E50'], r['RSI']>50, r['Close']>r['Open'], r['ATR']>=df['ATR'].iloc[i-15:i].mean()*0.9, 25<r['RSI']<75])
        if b>=4 or (6-b)>=4:
            pos, side, ep = True, ("BUY" if b>=4 else "SELL"), r['Close']
            slp = ep - 1.2*r['ATR'] if side=="BUY" else ep + 1.2*r['ATR']
            tpp = ep + 2.0*r['ATR'] if side=="BUY" else ep - 2.0*r['ATR']

    return {"p":p, "dec":dec, "conf":conf, "sl":sl, "tp":tp, "conds":conds, "w":w, "l":l, "net":net}

if mode == "🌐 ALL COINS":
    bar = st.progress(0)
    rows, tw, tl, tnet = "", 0, 0, 0.0
    for idx, (name, tk) in enumerate(pairs.items()):
        res = analyze(get_data(tk, tf), tf)
        if res:
            tw += res['w']; tl += res['l']; tnet += res['net']
            cls = "buy" if res['dec']=="BUY" else ("sell" if res['dec']=="SELL" else "wait")
            sl_s = fmt(res['sl']) if res['dec']!="WAIT" else "-"
            tp_s = fmt(res['tp']) if res['dec']!="WAIT" else "-"
            ncol = "#00ff66" if res['net']>=0 else "#ff0055"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['p'])}</td><td><span class='{cls}'>{res['dec']} {res['conf']}%</span></td><td style='color:#ff0055'>{sl_s}</td><td style='color:#00ff66'>{tp_s}</td><td style='color:{ncol}'>${res['net']:+.2f}</td></tr>"
        bar.progress((idx+1)/len(pairs))
    bar.empty()
    wr = (tw/(tw+tl)*100) if (tw+tl)>0 else 0
    nc = "#00ff66" if tnet>=0 else "#ff0055"
    st.markdown(f"<div class='grid'><div class='card'><small>WINS 24H</small><br><b style='color:#00ff66;font-size:18px'>{tw} 🟢</b></div><div class='card'><small>LOSS 24H</small><br><b style='color:#ff0055;font-size:18px'>{tl} 🔴</b></div><div class='card'><small>WIN RATE</small><br><b style='color:#00ffcc;font-size:18px'>{wr:.1f}%</b></div><div class='card'><small>NET PNL</small><br><b style='color:{nc};font-size:18px'>${tnet:+.2f}</b></div></div>", unsafe_allow_html=True)
    st.markdown(f"<table><thead><tr><th>PAIR</th><th>PRICE</th><th>SIGNAL</th><th>SL</th><th>TP</th><th>24H</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
else:
    res = analyze(get_data(pairs[mode], tf), tf)
    if res:
        bcls = "box-buy" if res['dec']=="BUY" else ("box-sell" if res['dec']=="SELL" else "box-wait")
        tcol = "#00ff66" if res['dec']=="BUY" else ("#ff0055" if res['dec']=="SELL" else "#ffcc00")
        tgs = f"<p style='margin-top:10px'><b>ENTRY: {fmt(res['p'])} | SL: <span style='color:#ff0055'>{fmt(res['sl'])}</span> | TP: <span style='color:#00ff66'>{fmt(res['tp'])}</span></b></p>" if res['dec']!="WAIT" else f"<p>PRICE: {fmt(res['p'])}</p>"
        st.markdown(f"<div class='{bcls}'><p style='margin:0;color:#aaa'>{mode} • {tf.upper()}</p><h1 style='font-size:55px;margin:5px 0;color:{tcol}'>{res['dec']}</h1><p>CONF: {res['conf']}%</p>{tgs}</div>", unsafe_allow_html=True)
        wr = (res['w']/(res['w']+res['l'])*100) if (res['w']+res['l'])>0 else 0
        nc = "#00ff66" if res['net']>=0 else "#ff0055"
        st.markdown(f"<div class='grid'><div class='card'><small>WINS</small><br><b style='color:#00ff66'>{res['w']}</b></div><div class='card'><small>LOSS</small><br><b style='color:#ff0055'>{res['l']}</b></div><div class='card'><small>WIN%</small><br><b style='color:#00ffcc'>{wr:.1f}%</b></div><div class='card'><small>NET</small><br><b style='color:{nc}'>${res['net']:+.2f}</b></div></div>", unsafe_allow_html=True)
        for n, s in res['conds']:
            bg = "<span class='buy'>PASS</span>" if s else "<span class='sell'>FAIL</span>"
            st.markdown(f"<div style='display:flex;justify-content:space-between;background:#131926;padding:8px 12px;margin-bottom:5px;border-radius:5px'><span>{n}</span>{bg}</div>", unsafe_allow_html=True)
