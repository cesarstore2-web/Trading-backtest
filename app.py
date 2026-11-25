import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="PRICE ACTION PRO | MTF ENGULFING", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px}.sell{color:#ff0055;border:1px solid #ff0055;padding:3px 8px;border-radius:4px}.wait{color:#ffcc00;border:1px solid #ffcc00;padding:3px 8px;border-radius:4px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:15px 0}.card{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:10px;text-align:center}.box-buy{border:2px solid #00ff66;border-radius:10px;padding:20px;text-align:center;background:rgba(0,255,102,0.08)}.box-sell{border:2px solid #ff0055;border-radius:10px;padding:20px;text-align:center;background:rgba(255,0,85,0.08)}.box-wait{border:2px solid #ffcc00;border-radius:10px;padding:20px;text-align:center;background:rgba(255,204,0,0.08)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>⚡ PRICE ACTION SNIPER | MTF ENGULFING ⚡</h2><p style='margin:0;color:#aaa;font-size:12px'>إغلاق الفريم الكبير (H1/H4) + ابتلاع الفريم الصغير + إدارة مخاطر متكاملة</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات الإكسبيرت (Inputs)")
    htf = st.selectbox("الفريم الكبير (تحديد الاتجاه):", ["1h", "4h"], index=0)
    ltf = st.selectbox("الفريم الصغير (نقطة الدخول):", ["1m", "5m", "15m"], index=1)
    mm_type = st.radio("نوع الإدارة:", ["Fixed Amount ($)", "Risk % of Balance"])
    balance = st.number_input("رصيد الحساب ($):", value=1000.0, step=100.0)
    fixed_amt = st.number_input("حجم الصفقة الثابت ($):", value=100.0, step=10.0)
    risk_pct = st.slider("نسبة المخاطرة (%):", 0.5, 5.0, 1.0, 0.5)
    sl_mode = st.radio("نظام حساب الوقف والهدف:", ["Dynamic (قمة/قاع الشمعة 1:2)", "Fixed % / Pips"])
    fixed_sl_pct = st.number_input("SL ثابت (% من السعر):", value=0.4, step=0.1)
    fixed_tp_pct = st.number_input("TP ثابت (% من السعر):", value=0.8, step=0.1)
    use_be = st.checkbox("تفعيل Break Even (عند 1:1)", value=True)
    use_trail = st.checkbox("تفعيل Trailing Stop", value=False)
    max_spread_pct = st.number_input("أقصى سبريد مسموح (%):", value=0.15, step=0.05)
    use_time = st.checkbox("تفعيل فلتر الوقت", value=False)
    start_hr = st.slider("ساعة البداية:", 0, 23, 8)
    end_hr = st.slider("ساعة النهاية:", 0, 23, 22)

c1, c2 = st.columns([2, 1])
mode = c1.selectbox("اختر العملة أو المسح الشامل:", ["🌐 ALL COINS (مسح شامل)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث الآن", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

@st.cache_data(ttl=60, show_spinner=False)
def get_data(ticker, interval):
    try:
        if interval == "4h":
            df = yf.download(ticker, period="30d", interval="1h", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            return df.dropna().resample('4h').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        period = "1d" if interval == "1m" else ("7d" if interval in ["5m", "15m"] else "30d")
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

def check_signal(c_prev, c_sig, htf_dir, cur_hour):
    if use_time:
        if start_hr <= end_hr and not (start_hr <= cur_hour <= end_hr): return "WAIT"
        if start_hr > end_hr and not (cur_hour >= start_hr or cur_hour <= end_hr): return "WAIT"
    if htf_dir == "BULL":
        if c_prev['Close'] < c_prev['Open'] and c_sig['Close'] > c_sig['Open']:
            if (c_sig['Close'] >= c_prev['Open'] and c_sig['Open'] <= c_prev['Close']) or (c_sig['Close'] > c_prev['High']):
                return "BUY"
    elif htf_dir == "BEAR":
        if c_prev['Close'] > c_prev['Open'] and c_sig['Close'] < c_sig['Open']:
            if (c_sig['Close'] <= c_prev['Open'] and c_sig['Open'] >= c_prev['Close']) or (c_sig['Close'] < c_prev['Low']):
                return "SELL"
    return "WAIT"

def calc_levels(side, entry, c_prev, c_sig):
    margin = entry * 0.0005
    if sl_mode.startswith("Dynamic"):
        if side == "BUY":
            sl = min(c_sig['Low'], c_prev['Low']) - margin
            tp = entry + 2.0 * max(entry - sl, entry * 0.001)
        else:
            sl = max(c_sig['High'], c_prev['High']) + margin
            tp = entry - 2.0 * max(sl - entry, entry * 0.001)
    else:
        sl = entry * (1 - fixed_sl_pct/100.0) if side=="BUY" else entry * (1 + fixed_sl_pct/100.0)
        tp = entry * (1 + fixed_tp_pct/100.0) if side=="BUY" else entry * (1 - fixed_tp_pct/100.0)
    return sl, tp

def run_engine(ticker):
    df_h = get_data(ticker, htf)
    df_l = get_data(ticker, ltf)
    if df_h.empty or df_l.empty or len(df_h) < 5 or len(df_l) < 30: return None

    last_h = df_h.iloc[-2]
    htf_dir = "BULL" if last_h['Close'] > last_h['Open'] else ("BEAR" if last_h['Close'] < last_h['Open'] else "NEUTRAL")

    c_prev, c_sig, c_open = df_l.iloc[-3], df_l.iloc[-2], df_l.iloc[-1]
    entry_live = float(c_open['Open'])
    cur_hr = c_open.name.hour if hasattr(c_open.name, 'hour') else 12
    est_spread = ((float(c_open['High']) - float(c_open['Low'])) / entry_live) * 10
    sig_live = check_signal(c_prev, c_sig, htf_dir, cur_hr) if est_spread <= max_spread_pct else "WAIT"
    sl_live, tp_live = calc_levels(sig_live, entry_live, c_prev, c_sig) if sig_live != "WAIT" else (0.0, 0.0)

    cmap = {"1m": 1440, "5m": 288, "15m": 96}
    lb = min(cmap.get(ltf, 288), len(df_l) - 5)
    wins, losses, be_trades, cur_bal = 0, 0, 0, balance
    in_pos, side, ep, slp, tpp, init_risk, be_done, pos_size = False, "", 0.0, 0.0, 0.0, 0.0, False, 0.0

    for i in range(len(df_l) - lb, len(df_l) - 1):
        bar = df_l.iloc[i]
        past_h = df_h[df_h.index <= bar.name]
        if len(past_h) < 2: continue
        h_c = past_h.iloc[-2]
        h_dir = "BULL" if h_c['Close'] > h_c['Open'] else "BEAR"

        if in_pos:
            if side == "BUY":
                if bar['Low'] <= slp:
                    pnl = -pos_size * ((ep - slp) / ep)
                    if abs(slp - ep) < 1e-8: be_trades += 1
                    elif pnl < 0: losses += 1
                    else: wins += 1
                    cur_bal += pnl; in_pos = False; continue
                if bar['High'] >= tpp:
                    cur_bal += pos_size * ((tpp - ep) / ep); wins += 1; in_pos = False; continue
                if use_be and not be_done and bar['High'] >= ep + init_risk: slp = ep; be_done = True
                if use_trail and bar['High'] - init_risk > slp: slp = bar['High'] - init_risk
            elif side == "SELL":
                if bar['High'] >= slp:
                    pnl = -pos_size * ((slp - ep) / ep)
                    if abs(slp - ep) < 1e-8: be_trades += 1
                    elif pnl < 0: losses += 1
                    else: wins += 1
                    cur_bal += pnl; in_pos = False; continue
                if bar['Low'] <= tpp:
                    cur_bal += pos_size * ((ep - tpp) / ep); wins += 1; in_pos = False; continue
                if use_be and not be_done and bar['Low'] <= ep - init_risk: slp = ep; be_done = True
                if use_trail and bar['Low'] + init_risk < slp: slp = bar['Low'] + init_risk
            continue

        p_c, s_c = df_l.iloc[i-2], df_l.iloc[i-1]
        b_hr = bar.name.hour if hasattr(bar.name, 'hour') else 12
        sig = check_signal(p_c, s_c, h_dir, b_hr)
        if sig in ["BUY", "SELL"]:
            in_pos, side, ep = True, sig, float(bar['Open'])
            slp, tpp = calc_levels(side, ep, p_c, s_c)
            init_risk, be_done = abs(ep - slp), False
            pos_size = fixed_amt if mm_type == "Fixed Amount ($)" else (cur_bal * (risk_pct / 100.0)) / max(init_risk / ep, 0.001)

    return {"price": float(c_open['Close']), "htf_dir": htf_dir, "sig": sig_live, "entry": entry_live, "sl": sl_live, "tp": tp_live, "w": wins, "l": losses, "be": be_trades, "net": cur_bal - balance}

if mode == "🌐 ALL COINS (مسح شامل)":
    status_txt = st.empty()
    bar = st.progress(0)
    rows, tw, tl, tbe, tnet = "", 0, 0, 0, 0.0
    for idx, (name, tk) in enumerate(pairs.items()):
        status_txt.text(f"⏳ جاري فحص {name} ({idx+1}/{len(pairs)})...")
        res = run_engine(tk)
        if res:
            tw += res['w']; tl += res['l']; tbe += res['be']; tnet += res['net']
            h_badge = f"<span class='buy'>BULL ({htf.upper()})</span>" if res['htf_dir']=="BULL" else f"<span class='sell'>BEAR ({htf.upper()})</span>"
            s_cls = "buy" if res['sig']=="BUY" else ("sell" if res['sig']=="SELL" else "wait")
            sl_s = fmt(res['sl']) if res['sig']!="WAIT" else "-"
            tp_s = fmt(res['tp']) if res['sig']!="WAIT" else "-"
            ncol = "#00ff66" if res['net']>=0 else "#ff0055"
