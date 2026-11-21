import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Whale SMC AI ($)", page_icon="🐋", layout="wide", initial_sidebar_state="collapsed")

ASSETS_MAP = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD", "XRPUSDT": "XRP-USD", "DOGEUSDT": "DOGE-USD",
    "ADAUSDT": "ADA-USD", "AVAXUSDT": "AVAX-USD", "LINKUSDT": "LINK-USD",
    "XLMUSDT": "XLM-USD", "HBARUSDT": "HBAR-USD", "LTCUSDT": "LTC-USD",
    "ZECUSDT": "ZEC-USD", "PAXGUSDT": "PAXG-USD", "XAUUSDT (الذهب)": "GC=F"
}

LIVE_STATUSES = ["جارية", "بانتظار الدخول"]
CACHE_VER = "v7_daily"


@st.cache_data(ttl=300, show_spinner=False)
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
    for idx in range(2, min(len(records), 10)):
        c1, c3 = records[idx - 2], records[idx]
        if direction == "BUY" and c3['low'] > c1['high']:
            return True, (c3['low'] + c1['high']) / 2.0
        if direction == "SELL" and c3['high'] < c1['low']:
            return True, (c3['high'] + c1['low']) / 2.0
    return False, 0.0


def eval_trade(ltf_rec, ts_arr, entry_time, direction, entry, sl, tp, risk_usd, reward_usd, be_r):
    start = int(np.searchsorted(ts_arr, pd.Timestamp(entry_time).to_datetime64(), side='right'))
    cur_sl, dist = sl, abs(entry - sl)
    for bar in ltf_rec[start:start + 120]:  # حد أقصى 30 ساعة على فريم 15m لعدم تعليق الصفقات القديمة
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
    return "منتهية", 0.0


def make_signal(ts, typ, entry, sl, tp, fvg, ai, status, pnl):
    return {'timestamp': ts, 'type': typ, 'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4),
            'fvg': "FVG مؤكد" if fvg else "Order Block", 'ai': ai, 'status': status, 'pnl': round(pnl, 2)}


@st.cache_data(ttl=300, show_spinner=False)
def run_smc_cached(_ver, df_h, df_l, rr=2.0, sh=0, eh=23, cap=1000.0, rpct=1.0, be_r=0.85, sl_atr=0.45, req_fvg=False):
    if df_h.empty or df_l.empty or len(df_h) < 60:
        return pd.DataFrame()

    df_h = df_h.sort_values('timestamp').reset_index(drop=True).copy()
    df_l = df_l.sort_values('timestamp').reset_index(drop=True).copy()

    df_h['atr'] = np.maximum(
        df_h['high'] - df_h['low'],
        np.maximum(abs(df_h['high'] - df_h['close'].shift(1)), abs(df_h['low'] - df_h['close'].shift(1)))
    ).rolling(14).mean()
    df_h['ema50'] = df_h['close'].ewm(span=50, adjust=False).mean()
    delta = df_h['close'].diff()
    df_h['rsi'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() /
                                     (-delta.where(delta < 0, 0).rolling(14).mean() + 1e-9))))
    df_h['vol_ma'] = df_h['volume'].rolling(24).mean()

    risk_usd = cap * (rpct / 100.0)
    reward_usd = risk_usd * rr

    htf_rec = df_h.to_dict('records')
    ltf_rec = df_l.to_dict('records')
    ts_arr = df_l['timestamp'].values
    last_ts = pd.Timestamp(ts_arr[-1])
    last_close = ltf_rec[-1]['close']
    signals = []

    # إعدادات يومية متوازنة (توليد فرص يومية مع الحفاظ على دقة SMC)
    VOL_MIN = 0.50
    WICK_MIN = 0.15
    LOOKBACK = 6
    WIN_HOURS = 18

    for i in range(55, len(htf_rec) - 1):
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
        end_ts = row['timestamp'] + pd.Timedelta(hours=WIN_HOURS)
        b = int(np.searchsorted(ts_arr, end_ts.to_datetime64(), side='right'))
        ltf_win = ltf_rec[a:b]
        if len(ltf_win) < 2:
            continue
        live_ok = end_ts > last_ts
        # ---------- BUY (مع الاتجاه أو انعكاس مؤكد بـ FVG) ----------
        l_wick = min(row['open'], row['close']) - row['low']
        if (rsi < 75 and row['low'] < maj_low and row['close'] > maj_low and l_wick >= rng * WICK_MIN):
            sub_h = max(x['high'] for x in ltf_win[:2])
            choch = next((r for r in ltf_win if r['close'] > sub_h), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "BUY")
                trend_ok = (row['close'] > row['ema50']) or (fvg and l_wick >= rng * 0.25)
                if trend_ok and not (req_fvg and not fvg):
                    zone = fvg_lvl if fvg else ((sub_h + row['low']) / 2.0)
                    sl_lvl = row['low'] - (atr * sl_atr)
                    ai = round(min(max((min(vol_ratio, 3.0) / 3.0 * 35) + (min(l_wick / rng, 0.85) / 0.85 * 35)
                                       + (22 if fvg else 10) + (10 if row['close'] > row['ema50'] else 4), 68.0), 99.2), 1)
                    # ملامسة منطقة الدخول مباشرة (أمر معلق Limit)
                    touch_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp'] and r['low'] <= zone), None)
                    if touch_c and zone > sl_lvl:
                        tp = zone + (zone - sl_lvl) * rr
                        st_res, pnl = eval_trade(ltf_rec, ts_arr, touch_c['timestamp'], "BUY", zone, sl_lvl, tp, risk_usd, reward_usd, be_r)
                        # إذا لم تنته الصفقة بعد وما زالت ضمن نافذة اليوم، تُعتبر جارية
                        if st_res == "منتهية" and (last_ts - touch_c['timestamp']) <= pd.Timedelta(hours=24):
                            st_res = "جارية"
                        signals.append(make_signal(touch_c['timestamp'], 'شراء (BUY)', zone, sl_lvl, tp, fvg, ai, st_res, pnl))
                    elif live_ok and zone > sl_lvl and last_close > sl_lvl:
                        tp = zone + (zone - sl_lvl) * rr
                        signals.append(make_signal(choch['timestamp'], 'شراء (BUY)', zone, sl_lvl, tp, fvg, ai, "بانتظار الدخول", 0.0))

        # ---------- SELL (مع الاتجاه أو انعكاس مؤكد بـ FVG) ----------
        u_wick = row['high'] - max(row['open'], row['close'])
        if (rsi > 25 and row['high'] > maj_high and row['close'] < maj_high and u_wick >= rng * WICK_MIN):
            sub_l = min(x['low'] for x in ltf_win[:2])
            choch = next((r for r in ltf_win if r['close'] < sub_l), None)
            if choch:
                fvg, fvg_lvl = detect_fvg(ltf_win, "SELL")
                trend_ok = (row['close'] < row['ema50']) or (fvg and u_wick >= rng * 0.25)
                if trend_ok and not (req_fvg and not fvg):
                    zone = fvg_lvl if fvg else ((sub_l + row['high']) / 2.0)
                    sl_lvl = row['high'] + (atr * sl_atr)
                    ai = round(min(max((min(vol_ratio, 3.0) / 3.0 * 35) + (min(u_wick / rng, 0.85) / 0.85 * 35)
                                       + (22 if fvg else 10) + (10 if row['close'] < row['ema50'] else 4), 68.0), 99.2), 1)
                    touch_c = next((r for r in ltf_win if r['timestamp'] > choch['timestamp'] and r['high'] >= zone), None)
                    if touch_c and sl_lvl > zone:
                        tp = zone - (sl_lvl - zone) * rr
                        st_res, pnl = eval_trade(ltf_rec, ts_arr, touch_c['timestamp'], "SELL", zone, sl_lvl, tp, risk_usd, reward_usd, be_r)
                        if st_res == "منتهية" and (last_ts - touch_c['timestamp']) <= pd.Timedelta(hours=24):
                            st_res = "جارية"
                        signals.append(make_signal(touch_c['timestamp'], 'بيع (SELL)', zone, sl_lvl, tp, fvg, ai, st_res, pnl))
                    elif live_ok and zone < sl_lvl and last_close < sl_lvl:
                        tp = zone - (sl_lvl - zone) * rr
                        signals.append(make_signal(choch['timestamp'], 'بيع (SELL)', zone, sl_lvl, tp, fvg, ai, "بانتظار الدخول", 0.0))

    df_res = pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type']) if signals else pd.DataFrame()
    if not df_res.empty:
        df_res['cur_price'] = round(last_close, 4)
    return df_res


# --- تنسيق الواجهة ---
st.markdown("""
<style>
.stApp{background:#09090d;color:#fff}
.box{background:#15151f;border-radius:15px;padding:16px;text-align:center;border:1px solid #2a2a3c;margin-bottom:10px;direction:rtl}
.rec{background:#161622;border-right:5px solid #00e676;border-radius:12px;padding:15px;margin-bottom:12px;direction:rtl;text-align:right;border-top:1px solid #262638;border-bottom:1px solid #262638;border-left:1px solid #262638}
.sell{border-right-color:#ff1744}
.badge{display:inline-block;padding:3px 10px;border-radius:8px;font-size:12px;font-weight:bold;background:#252538;color:#00e5ff;margin-right:6px}
div.stButton>button{background:linear-gradient(90deg,#7c4dff,#00b0ff);color:#fff;font-weight:bold;border-radius:12px;width:100%;padding:10px}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ إعدادات الاستراتيجية اليومية")
    cap = st.number_input("رأس المال ($):", 100.0, 1000000.0, 1000.0, 100.0)
    rpct = st.number_input("المخاطرة (%):", 0.5, 10.0, 1.0, 0.5)
    rr = st.slider("العائد للمخاطرة (1:X):", 1.5, 5.0, 2.0, 0.5)
    htf = st.selectbox("فريم السيولة (HTF):", ["1h", "4h"], index=0)
    ltf = st.selectbox("فريم الدخول (LTF):", ["15m", "5m"], index=0)
    sh, eh = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لتقييم AI% (فلتر الجودة):", 68, 95, 70)
    max_age_hrs = st.slider("أقصى عمر للصفقة الحية (ساعات):", 6, 36, 24)
    max_cards = st.slider("عدد التوصيات اليومية المعروضة:", 3, 10, 5)
    req_fvg = st.checkbox("اشتراط وجود FVG مؤكد فقط", value=False)

st.markdown("<h2 style='direction:rtl;text-align:right'>🐋 نظام تتبع سيولة الحيتان اليومي (SMC + AI)</h2>", unsafe_allow_html=True)
c_f1, c_f2 = st.columns(2)
with c_f1:
    view = st.selectbox("📅 سجل تقييم الجودة:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with c_f2:
    asset = st.selectbox("🪙 الأصل المالي:", ["الكل"] + list(ASSETS_MAP.keys()))

if st.button("🔍 فحص وتحديث الصفقات اليومية الآن"):
    st.cache_data.clear()

now_utc = pd.Timestamp.utcnow().tz_localize(None)
cutoff = now_utc - pd.Timedelta(days=30 if "شهري" in view else 7)
targets = ASSETS_MAP if asset == "الكل" else {asset: ASSETS_MAP[asset]}

all_frames = []
with st.spinner("جاري مسح 15 سوقاً للبحث عن أفضل الصفقات اليومية..."):
    for name, ticker in targets.items():
        df_h = fetch_data(ticker, htf)
        df_l = fetch_data(ticker, ltf)
        res = run_smc_cached(CACHE_VER, df_h, df_l, rr=rr, sh=sh, eh=eh, cap=cap, rpct=rpct, req_fvg=req_fvg)
        if not res.empty:
            res = res[res['ai'] >= min_ai].copy()
            if not res.empty:
                res['asset'] = name
                all_frames.append(res)

all_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()

# --- 1. إحصائيات جودة الاستراتيجية ---
st.markdown("<h4 style='direction:rtl;text-align:right;color:#b0b0c8'>📊 مؤشرات جودة الاستراتيجية (للفترة المحددة)</h4>", unsafe_allow_html=True)
if not all_df.empty:
    period_df = all_df[all_df['timestamp'] >= cutoff]
    closed_df = period_df[~period_df['status'].isin(LIVE_STATUSES + ["منتهية"])]
    wins = len(closed_df[closed_df['status'] == 'رابحة'])
    losses = len(closed_df[closed_df['status'] == 'خاسرة'])
    be_cnt = len(closed_df[closed_df['status'].str.contains('مؤمّنة', na=False)])
    decided = wins + losses
    win_rate = round((wins / decided) * 100, 1) if decided > 0 else 0.0
    net_pnl = round(closed_df['pnl'].sum(), 2)
else:
    wins = losses = be_cnt = 0
    win_rate = net_pnl = 0.0

m1, m2, m3, m4 = st.columns(4)
pnl_color = "#00e676" if net_pnl >= 0 else "#ff1744"
with m1:
    st.markdown(f"<div class='box'><div style='color:#9e9eb8'>الربح الصافي ($)</div><h3 style='color:{pnl_color};margin:5px 0'>{net_pnl:+.2f}$</h3></div>", unsafe_allow_html=True)
with m2:
    st.markdown(f"<div class='box'><div style='color:#9e9eb8'>نسبة النجاح</div><h3 style='color:#00b0ff;margin:5px 0'>{win_rate}%</h3></div>", unsafe_allow_html=True)
with m3:
    st.markdown(f"<div class='box'><div style='color:#9e9eb8'>صفقات رابحة</div><h3 style='color:#00e676;margin:5px 0'>{wins}</h3></div>", unsafe_allow_html=True)
with m4:
    st.markdown(f"<div class='box'><div style='color:#9e9eb8'>صفقات خاسرة (مؤمّنة: {be_cnt})</div><h3 style='color:#ff1744;margin:5px 0'>{losses}</h3></div>", unsafe_allow_html=True)

# --- 2. عرض الصفقات اليومية الحية وبانتظار الدخول ---
st.markdown(f"<h4 style='direction:rtl;text-align:right;color:#00e5ff;margin-top:15px'>⚡ الصفقات اليومية الحية وبانتظار الدخول (أحدث {max_cards} فرص)</h4>", unsafe_allow_html=True)

if not all_df.empty:
    fresh_cutoff = now_utc - pd.Timedelta(hours=max_age_hrs)
    live_df = all_df[(all_df['status'].isin(LIVE_STATUSES)) & (all_df['timestamp'] >= fresh_cutoff)].copy()
else:
    live_df = pd.DataFrame()

if live_df.empty:
    st.markdown(f"<div class='box' style='color:#9e9eb8'>لا توجد صفقات نشطة خلال آخر {max_age_hrs} ساعة. جرّب اختيار فريم <b>5m</b> للدخول من القائمة الجانبية لزيادة الصفقات اليومية.</div>", unsafe_allow_html=True)
else:
    live_df = live_df.sort_values(by=['timestamp', 'ai'], ascending=[False, False]).head(max_cards)
    for _, r in live_df.iterrows():
        is_sell = "SELL" in r['type']
        card_cls = "rec sell" if is_sell else "rec"
        type_color = "#ff1744" if is_sell else "#00e676"
        status_bg = "#1b5e20" if r['status'] == "جارية" else "#e65100"
        st.markdown(f"""
        <div class='{card_cls}'>
            <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>
                <div>
                    <strong style='font-size:18px'>{r['asset']}</strong>
                    <span style='color:{type_color};font-weight:bold;margin-right:8px'>{r['type']}</span>
