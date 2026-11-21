import streamlit as st
import requests
import pandas as pd
import numpy as np

st.set_page_config(page_title="Whale SMC AI ($)", page_icon="🐋", layout="wide", initial_sidebar_state="collapsed")

ASSETS_MAP = {
    "BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT", "XRPUSDT": "XRPUSDT",
    "XLMUSDT": "XLMUSDT", "ZECUSDT": "ZECUSDT", "HBARUSDT": "HBARUSDT",
    "ADAUSDT": "ADAUSDT", "LTCUSDT": "LTCUSDT", "PAXGUSDT": "PAXGUSDT",
    "XAUUSDT (الذهب)": "PAXGUSDT"
}

@st.cache_data(ttl=600)
def fetch_binance_vision(symbol, interval="1h", limit=1000):
    """جلب البيانات من خادم Binance المفتوح للبيانات العامة (سريع جداً وبدون حظر)"""
    try:
        url = f"https://binance.vision{symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=8)
        if res.status_code != 200:
            return pd.DataFrame()
        data = res.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'trades', 'tbbav', 'tbqav', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].dropna()
    except Exception:
        return pd.DataFrame()

def detect_fvg(records, direction):
    for idx in range(2, min(len(records), 8)):
        c1, c3 = records[idx - 2], records[idx]
        if direction == "BUY" and c3['low'] > c1['high']: return True, (c3['low'] + c1['high']) / 2.0
        if direction == "SELL" and c3['high'] < c1['low']: return True, (c3['high'] + c1['low']) / 2.0
    return False, 0.0

def eval_trade(ltf_rec, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    cur_sl, dist = sl, abs(entry - sl)
    for bar in [r for r in ltf_rec if r['timestamp'] > entry_time][:280]:
        if direction == "BUY":
            if bar['high'] >= entry + dist * 1.1: cur_sl = entry
            if bar['low'] <= cur_sl: return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['high'] >= tp: return "رابحة", reward_usd
        else:
            if bar['low'] <= entry - dist * 1.1: cur_sl = entry
            if bar['high'] >= cur_sl: return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['low'] <= tp: return "رابحة", reward_usd
    return "جارية", 0.0

def run_smc(df_h, df_l, rr=2.0, sh=0, eh=23, cap=1000.0, rpct=1.0):
    if df_h.empty or df_l.empty or len(df_h) < 105: return pd.DataFrame()
    df_h = df_h.copy()
    df_h['atr'] = np.maximum(df_h['high'] - df_h['low'], np.maximum(abs(df_h['high'] - df_h['close'].shift(1)), abs(df_h['low'] - df_h['close'].shift(1)))).rolling(14).mean()
    df_h['ema100'] = df_h['close'].ewm(span=100, adjust=False).mean()
    delta = df_h['close'].diff()
    df_h['rsi'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (-delta.where(delta < 0, 0).rolling(14).mean() + 1e-9))))
    df_h['vol_ma'] = df_h['volume'].rolling(30).mean()
    risk_usd, reward_usd = cap * (rpct / 100.0), cap * (rpct / 100.0) * rr
    htf_rec, ltf_rec, signals = df_h.to_dict('records'), df_l.to_dict('records'), []

    for i in range(100, len(htf_rec) - 2):
        row = htf_rec[i]
        if not (sh <= row['timestamp'].hour <= eh): continue
        vol_ratio = row['volume'] / ((row['vol_ma'] if pd.notna(row['vol_ma']) else 1.0) + 1e-9)
        if vol_ratio < 0.9: continue
        atr = float(row['atr']) if pd.notna(row['atr']) else (row['high'] - row['low'])
        rsi = float(row['rsi']) if pd.notna(row['rsi']) else 50.0
        rng = row['high'] - row['low']
        if rng == 0: continue
        past = htf_rec[i-12:i]
        maj_low, maj_high = min(x['low'] for x in past), max(x['high'] for x in past)
        ltf_win = [r for r in ltf_rec if row['timestamp'] < r['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=10)]
        if len(ltf_win) < 5: continue

        l_wick = min(row['open'], row['close']) - row['low']
        if row['close'] > row['ema100'] and rsi < 72 and row['low'] < maj_low and row['close'] > maj_low and l_wick >= rng * 0.28:
            sub_h = max(x['high'] for x in ltf_win[:3])
            choch = next((r for r in ltf_win if r['close'] > sub_h), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "BUY")
                zone = fvg_lvl if fvg else ((sub_h + row['low']) / 2.0)
                ent_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp'] and r['low'] <= zone and r['close'] > r['open']), None)
                if ent_c:
                    entry, sl = ent_c['close'], row['low'] - (atr * 0.35)
                    if entry > sl:
                        tp = entry + (entry - sl) * rr
                        ai = round(min(max((min(vol_ratio, 3.0)/3.0*35) + (min(l_wick/rng, 0.85)/0.85*35) + (22 if fvg else 10) + 10, 68.0), 99.2), 1)
                        st_res, pnl = eval_trade(ltf_rec, ent_c['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)
                        signals.append({'timestamp': ent_c['timestamp'], 'type': 'شراء (BUY)', 'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': "FVG مؤكد" if fvg else "Order Block", 'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})

        u_wick = row['high'] - max(row['open'], row['close'])
        if row['close'] < row['ema100'] and rsi > 28 and row['high'] > maj_high and row['close'] < maj_high and u_wick >= rng * 0.28:
            sub_l = min(x['low'] for x in ltf_win[:3])
            choch = next((r for r in ltf_win if r['close'] < sub_l), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "SELL")
                zone = fvg_lvl if fvg else ((sub_l + row['high']) / 2.0)
                ent_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp'] and r['high'] >= zone and r['close'] < r['open']), None)
                if ent_c:
                    entry, sl = ent_c['close'], row['high'] + (atr * 0.35)
                    if sl > entry:
                        tp = entry - (sl - entry) * rr
                        ai = round(min(max((min(vol_ratio, 3.0)/3.0*35) + (min(u_wick/rng, 0.85)/0.85*35) + (22 if fvg else 10) + 10, 68.0), 99.2), 1)
                        st_res, pnl = eval_trade(ltf_rec, ent_c['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)
                        signals.append({'timestamp': ent_c['timestamp'], 'type': 'بيع (SELL)', 'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': "FVG مؤكد" if fvg else "Order Block", 'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})

    return pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type']) if signals else pd.DataFrame()

st.markdown("<style>.stApp{background:#09090d;color:#fff}.box{background:#15151f;border-radius:15px;padding:16px;text-align:center;border:1px solid #2a2a3c;margin-bottom:10px;direction:rtl}.rec{background:#161622;border-right:5px solid #00e676;border-radius:12px;padding:14px;margin-bottom:10px;direction:rtl;text-align:right}.sell{border-right-color:#ff1744}div.stButton>button{background:linear-gradient(90deg,#7c4dff,#00b0ff);color:#fff;font-weight:bold;border-radius:12px;width:100%;padding:10px}</style>", unsafe_allow_html=True)

with st.sidebar:
    cap = st.number_input("رأس المال ($):", 100.0, 1000000.0, 1000.0, 100.0)
    rpct = st.number_input("المخاطرة (%):", 0.5, 10.0, 1.0, 0.5)
    rr = st.slider("العائد للمخاطرة (1:X):", 1.5, 5.0, 2.0, 0.5)
    htf = st.selectbox("فريم السيولة (HTF):", ["1h", "4h"])
    ltf = st.selectbox("فريم الدخول (LTF):", ["15m", "5m"])
    sh, eh = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI%:", 65, 95, 70)

st.markdown("<h2 style='direction:rtl;text-align:right'>🐋 نظام تتبع سيولة الحيتان (SMC + AI)</h2>", unsafe_allow_html=True)
c_f1, c_f2 = st.columns(2)
with c_f1: view = st.selectbox("📅 سجل الأداء:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with c_f2: asset = st.selectbox("🪙 الأصل المالي:", ["الكل"] + list(ASSETS_MAP.keys()))
st.button("🔍 فحص والبحث عن أعلى 3 توصيات")

cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=30 if "شهري" in view else 7)
targets = list(ASSETS_MAP.items()) if asset == "الكل" else [(asset, ASSETS_MAP[asset])]

with st.spinner("جاري فحص السيولة..."):
    res_list = []
    for name, tk in targets:
        df_h = fetch_binance_vision(tk, htf, 850)
        df_l = fetch_binance_vision(tk, ltf, 1000)
        df_res = run_smc(df_h, df_l, rr, sh, eh, cap, rpct)
        if not df_res.empty:
            df_res['symbol'] = name
            res_list.append(df_res)
    df_f = pd.concat(res_list, ignore_index=True) if res_list else pd.DataFrame()
    if not df_f.empty: df_f = df_f[(df_f['timestamp'] >= cutoff) & (df_f['ai'] >= min_ai)]

wins = len(df_f[df_f['status'] == 'رابحة']) if not df_f.empty else 0
losses = len(df_f[df_f['status'] == 'خاسرة']) if not df_f.empty else 0
bes = len(df_f[df_f['status'].str.contains('مؤمّنة')]) if not df_f.empty else 0
rate = round((wins / (wins + losses) * 100), 1) if (wins + losses) > 0 else 0.0
gp = round(df_f[df_f['status'] == 'رابحة']['pnl'].sum(), 2) if not df_f.empty else 0.0
gl = round(df_f[df_f['status'] == 'خاسرة']['pnl'].sum(), 2) if not df_f.empty else 0.0
net = round(gp + gl, 2)

c1, c2 = st.columns(2)
c1.markdown(f"<div class='box' style='border-top:4px solid #8c52ff'><div>🎯 نسبة النجاح</div><h1 style='color:#b388ff'>{rate}%</h1></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='box' style='border-top:4px solid #00b0ff'><div>📊 الصفقات (مؤمّنة: {bes})</div><h1 style='color:#40c4ff'>{wins+losses+bes}</h1></div>", unsafe_allow_html=True)
c3, c4 = st.columns(2)
