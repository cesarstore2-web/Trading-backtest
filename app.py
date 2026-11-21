import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Whale SMC AI ($)", page_icon="🐋", layout="wide", initial_sidebar_state="collapsed")

ASSETS_MAP = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "XRPUSDT": "XRP-USD",
    "XLMUSDT": "XLM-USD", "ZECUSDT": "ZEC-USD", "HBARUSDT": "HBAR-USD",
    "ADAUSDT": "ADA-USD", "LTCUSDT": "LTC-USD", "PAXGUSDT": "PAXG-USD",
    "XAUUSDT (الذهب)": "GC=F"
}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_data(ticker, interval="1h"):
    try:
        df = yf.download(ticker, interval=interval, period="60d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={'Datetime': 'timestamp', 'Date': 'timestamp', 'Open': 'open', 'High': 'high',
                           'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.dropna().sort_values('timestamp').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def detect_fvg(records, direction):
    for idx in range(2, min(len(records), 8)):
        c1, c3 = records[idx - 2], records[idx]
        if direction == "BUY" and c3['low'] > c1['high']:
            return True, (c3['low'] + c1['high']) / 2.0
        if direction == "SELL" and c3['high'] < c1['low']:
            return True, (c3['high'] + c1['low']) / 2.0
    return False, 0.0


def eval_trade(ltf_rec, ts_arr, entry_time, direction, entry, sl, tp, risk_usd, reward_usd, be_r):
    start = int(np.searchsorted(ts_arr, pd.Timestamp(entry_time).to_datetime64(), side='right'))
    cur_sl, dist = sl, abs(entry - sl)
    for bar in ltf_rec[start:start + 280]:
        if direction == "BUY":
            if bar['high'] >= entry + dist * be_r:
                cur_sl = entry
            if bar['low'] <= cur_sl:
                return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['high'] >= tp:
                return "رابحة", reward_usd
        else:
            if bar['low'] <= entry - dist * be_r:
                cur_sl = entry
            if bar['high'] >= cur_sl:
                return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['low'] <= tp:
                return "رابحة", reward_usd
    return "جارية", 0.0


def run_smc(df_h, df_l, rr=2.0, sh=0, eh=23, cap=1000.0, rpct=1.0, be_r=0.8, sl_atr=0.5, req_fvg=False):
    if df_h.empty or df_l.empty or len(df_h) < 105:
        return pd.DataFrame()

    df_h = df_h.sort_values('timestamp').reset_index(drop=True).copy()
    df_l = df_l.sort_values('timestamp').reset_index(drop=True).copy()

    df_h['atr'] = np.maximum(
        df_h['high'] - df_h['low'],
        np.maximum(abs(df_h['high'] - df_h['close'].shift(1)), abs(df_h['low'] - df_h['close'].shift(1)))
    ).rolling(14).mean()
    df_h['ema100'] = df_h['close'].ewm(span=100, adjust=False).mean()
    delta = df_h['close'].diff()
    df_h['rsi'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() /
                                     (-delta.where(delta < 0, 0).rolling(14).mean() + 1e-9))))
    df_h['vol_ma'] = df_h['volume'].rolling(30).mean()

    risk_usd = cap * (rpct / 100.0)
    reward_usd = risk_usd * rr

    htf_rec = df_h.to_dict('records')
    ltf_rec = df_l.to_dict('records')
    ts_arr = df_l['timestamp'].values
    signals = []

    VOL_MIN = 0.7
    WICK_MIN = 0.20
    LOOKBACK = 10
    WIN_HOURS = 16

    for i in range(100, len(htf_rec) - 2):
        row = htf_rec[i]
        if not (sh <= row['timestamp'].hour <= eh):
            continue
        vol_ma = row['vol_ma'] if pd.notna(row['vol_ma']) else 1.0
        vol_ratio = row['volume'] / (vol_ma + 1e-9)
        if vol_ratio < VOL_MIN:
            continue
        atr = float(row['atr']) if pd.notna(row['atr']) else (row['high'] - row['low'])
        rsi = float(row['rsi']) if pd.notna(row['rsi']) else 50.0
        rng = row['high'] - row['low']
        if rng == 0:
            continue

        past = htf_rec[i - LOOKBACK:i]
        maj_low = min(x['low'] for x in past)
        maj_high = max(x['high'] for x in past)

        a = int(np.searchsorted(ts_arr, row['timestamp'].to_datetime64(), side='right'))
        b = int(np.searchsorted(ts_arr, (row['timestamp'] + pd.Timedelta(hours=WIN_HOURS)).to_datetime64(), side='right'))
        ltf_win = ltf_rec[a:b]
        if len(ltf_win) < 5:
            continue

        # ---------- BUY ----------
        l_wick = min(row['open'], row['close']) - row['low']
        if (row['close'] > row['ema100'] and rsi < 72 and row['low'] < maj_low
                and row['close'] > maj_low and l_wick >= rng * WICK_MIN):
            sub_h = max(x['high'] for x in ltf_win[:3])
            choch = next((r for r in ltf_win if r['close'] > sub_h), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "BUY")
                if req_fvg and not fvg:
                    pass
                else:
                    zone = fvg_lvl if fvg else ((sub_h + row['low']) / 2.0)
                    ent_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp']
                                  and r['low'] <= zone and r['close'] > r['open']), None)
                    if ent_c:
                        entry, sl = ent_c['close'], row['low'] - (atr * sl_atr)
                        if entry > sl:
                            tp = entry + (entry - sl) * rr
                            ai = round(min(max((min(vol_ratio, 3.0) / 3.0 * 35) + (min(l_wick / rng, 0.85) / 0.85 * 35)
                                               + (22 if fvg else 10) + 10, 68.0), 99.2), 1)
                            st_res, pnl = eval_trade(ltf_rec, ts_arr, ent_c['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd, be_r)
                            signals.append({'timestamp': ent_c['timestamp'], 'type': 'شراء (BUY)',
                                            'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4),
                                            'fvg': "FVG مؤكد" if fvg else "Order Block",
                                            'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})

        # ---------- SELL ----------
        u_wick = row['high'] - max(row['open'], row['close'])
        if (row['close'] < row['ema100'] and rsi > 28 and row['high'] > maj_high
                and row['close'] < maj_high and u_wick >= rng * WICK_MIN):
            sub_l = min(x['low'] for x in ltf_win[:3])
            choch = next((r for r in ltf_win if r['close'] < sub_l), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "SELL")
                if req_fvg and not fvg:
                    pass
                else:
                    zone = fvg_lvl if fvg else ((sub_l + row['high']) / 2.0)
                    ent_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp']
                                  and r['high'] >= zone and r['close'] < r['open']), None)
                    if ent_c:
                        entry, sl = ent_c['close'], row['high'] + (atr * sl_atr)
                        if sl > entry:
                            tp = entry - (sl - entry) * rr
                            ai = round(min(max((min(vol_ratio, 3.0) / 3.0 * 35) + (min(u_wick / rng, 0.85) / 0.85 * 35)
                                               + (22 if fvg else 10) + 10, 68.0), 99.2), 1)
                            st_res, pnl = eval_trade(ltf_rec, ts_arr, ent_c['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd, be_r)
                            signals.append({'timestamp': ent_c['timestamp'], 'type': 'بيع (SELL)',
                                            'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4),
                                            'fvg': "FVG مؤكد" if fvg else "Order Block",
                                            'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})

    if not signals:
        return pd.DataFrame()
    return pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type'])


@st.cache_data(ttl=600, show_spinner=False)
def scan_asset(name, tk, htf, ltf, rr, sh, eh, cap, rpct, be_r, sl_atr, req_fvg):
    df = run_smc(fetch_data(tk, htf), fetch_data(tk, ltf), rr, sh, eh, cap, rpct, be_r, sl_atr, req_fvg)
    if not df.empty:
        df['symbol'] = name
    return df


st.markdown(
    "<style>.stApp{background:#09090d;color:#fff}"
    ".box{background:#15151f;border-radius:15px;padding:16px;text-align:center;border:1px solid #2a2a3c;margin-bottom:10px;direction:rtl}"
    ".rec{background:#161622;border-right:5px solid #00e676;border-radius:12px;padding:14px;margin-bottom:10px;direction:rtl;text-align:right}"
    ".sell{border-right-color:#ff1744}"
    "div.stButton>button{background:linear-gradient(90deg,#7c4dff,#00b0ff);color:#fff;font-weight:bold;border-radius:12px;width:100%;padding:10px}"
    "</style>",
    unsafe_allow_html=True)

with st.sidebar:
    cap = st.number_input("رأس المال ($):", 100.0, 1000000.0, 1000.0, 100.0)
    rpct = st.number_input("المخاطرة (%):", 0.5, 10.0, 1.0, 0.5)
    rr = st.slider("العائد للمخاطرة (1:X):", 1.5, 5.0, 2.0, 0.5)
    htf = st.selectbox("فريم السيولة (HTF):", ["1h", "4h"])
    ltf = st.selectbox("فريم الدخول (LTF):", ["15m", "5m"])
    sh, eh = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI%:", 65, 95, 70)
    st.markdown("---")
    be_r = st.slider("نقطة التأمين (R):", 0.4, 1.5, 0.8, 0.1)
    sl_atr = st.slider("هامش الستوب (ATR):", 0.2, 1.0, 0.5, 0.05)
    req_fvg = st.checkbox("قبول الصفقات ذات FVG فقط", value=False)

st.markdown("<h2 style='direction:rtl;text-align:right'>🐋 نظام تتبع سيولة الحيتان (SMC + AI)</h2>", unsafe_allow_html=True)
c_f1, c_f2 = st.columns(2)
with c_f1:
    view = st.selectbox("📅 سجل الأداء:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with c_f2:
    asset = st.selectbox("🪙 الأصل المالي:", ["الكل"] + list(ASSETS_MAP.keys()))
st.button("🔍 فحص والبحث عن أعلى 3 توصيات")

cutoff = pd.Timestamp.now() - pd.Timedelta(days=30 if "شهري" in view else 7)

items = list(ASSETS_MAP.items()) if asset == "الكل" else [(asset, ASSETS_MAP[asset])]
res_list = []
progress = st.progress(0.0, text="جاري فحص السيولة...")
for n, (name, tk) in enumerate(items):
    try:
        d = scan_asset(name, tk, htf, ltf, rr, sh, eh, cap, rpct, be_r, sl_atr, req_fvg)
        if d is not None and not d.empty:
            res_list.append(d)
    except Exception as e:
        st.error(f"{name}: {e}")
    progress.progress((n + 1) / len(items), text=f"تم فحص {name}")
progress.empty()

df_f = pd.concat(res_list, ignore_index=True) if res_list else pd.DataFrame()
if not df_f.empty:
    df_f = df_f[(df_f['timestamp'] >= cutoff) & (df_f['ai'] >= min_ai)].reset_index(drop=True)

has = not df_f.empty
wins = len(df_f[df_f['status'] == 'رابحة']) if has else 0
losses = len(df_f[df_f['status'] == 'خاسرة']) if has else 0
bes = len(df_f[df_f['status'].str.contains('مؤمّنة')]) if has else 0
rate = round((wins / (wins + losses) * 100), 1) if (wins + losses) > 0 else 0.0
gp = round(df_f[df_f['status'] == 'رابحة']['pnl'].sum(), 2) if has else 0.0
gl = round(df_f[df_f['status'] == 'خاسرة']['pnl'].sum(), 2) if has else 0.0
net = round(gp + gl, 2)

c1, c2 = st.columns(2)
c1.markdown(f"<div class='box' style='border-top:4px solid #8c52ff'><div>🎯 نسبة النجاح</div><h1 style='color:#b388ff'>{rate}%</h1></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='box' style='border-top:4px solid #00b0ff'><div>📊 الصفقات (مؤمّنة: {bes})</div><h1 style='color:#40c4ff'>{wins + losses + bes}</h1></div>", unsafe_allow_html=True)
c3, c4 = st.columns(2)
c3.markdown(f"<div class='box' style='border-top:4px solid #00e676'><div>✅ الناجحة (<span dir='ltr'>+${gp}</span>)</div><h1 style='color:#00e676'>{wins}</h1></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='box' style='border-top:4px solid #ff1744'><div>❌ الخاسرة (<span dir='ltr'>-${abs(gl)}</span>)</div><h1 style='color:#ff5252'>{losses}</h1></div>", unsafe_allow_html=True)

net_color = "#00e676" if net >= 0 else "#ff5252"
st.markdown(f"<div class='box' style='border-top:4px solid {net_color}'><div>💰 صافي الربح</div><h1 style='color:{net_color}'><span dir='ltr'>{net}$</span></h1></div>", unsafe_allow_html=True)

st.markdown("<h3 style='direction:rtl;text-align:right'>🏆 أعلى 3 توصيات</h3>", unsafe_allow_html=True)
if not has:
    st.info("لا توجد صفقات بهذه الإعدادات. جرّب تخفيض الحد الأدنى لتقييم AI أو توسيع ساعات العمل.")
else:
    top3 = df_f.sort_values(['ai', 'timestamp'], ascending=[False, False]).head(3)
    for _, r in top3.iterrows():
        cls = "rec" if "BUY" in r['type'] else "rec sell"
        st.markdown(
            f"<div class='{cls}'>"
            f"<b>{r['symbol']} — {r['type']}</b> &nbsp; 🤖 {r['ai']}%<br>"
            f"الدخول: {r['entry']} &nbsp;|&nbsp; SL: {r['sl']} &nbsp;|&nbsp; TP: {r['tp']}<br>"
            f"{r['fvg']} &nbsp;|&nbsp; الحالة: {r['status']} (<span dir='ltr'>{r['pnl']}$</span>)<br>"
            f"<small>{r['timestamp']}</small>"
            f"</div>", unsafe_allow_html=True)

    with st.expander("📋 كل الصفقات"):
        show = df_f.sort_values('timestamp', ascending=False)[
            ['timestamp', 'symbol', 'type', 'entry', 'sl', 'tp', 'fvg', 'ai', 'status', 'pnl']]
        st.dataframe(show, use_container_width=True, hide_index=True)