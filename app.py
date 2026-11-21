import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Candlestick Patterns AI ($)", page_icon="🕯️", layout="wide", initial_sidebar_state="collapsed")

ASSETS_MAP = {
    "XLMUSDT": "XLM-USD", "ZECUSDT": "ZEC-USD", "XRPUSDT": "XRP-USD",
    "HBARUSDT": "HBAR-USD", "ADAUSDT": "ADA-USD", "LTCUSDT": "LTC-USD",
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "PAXGUSDT": "PAXG-USD",
    "XAUUSDT (الذهب)": "GC=F"
}

LIVE_STATUSES = ["جارية", "بانتظار الدخول"]
CACHE_VER = "v20_trend_selector"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_data(ticker, interval="1h"):
    try:
        # تحديد مدة البيانات تلقائياً لضمان كفاية الشموع لحساب EMA 100 على كل فريم
        if interval in ["5m", "15m", "30m"]:
            per = "30d"
        elif interval in ["1h", "4h"]:
            per = "90d"
        else:
            per = "1y"
        df = yf.download(ticker, interval=interval, period=per, progress=False, auto_adjust=False)
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


def detect_candle_pattern(rec, i):
    c0, c1, c2 = rec[i - 2], rec[i - 1], rec[i]
    past_low = min(x['low'] for x in rec[i - 8:i])
    past_high = max(x['high'] for x in rec[i - 8:i])
    b2 = abs(c2['close'] - c2['open'])
    r2 = max(c2['high'] - c2['low'], 1e-9)
    u_wick2 = c2['high'] - max(c2['open'], c2['close'])
    l_wick2 = min(c2['open'], c2['close']) - c2['low']
    b1 = abs(c1['close'] - c1['open'])

    if min(c2['low'], c1['low']) <= past_low * 1.004:
        if c0['close'] > c0['open'] and c1['close'] > c1['open'] and c2['close'] > c2['open'] and c1['close'] > c0['close'] and c2['close'] > c1['close'] and b2 >= r2 * 0.45:
            return "BUY", "الجنود الثلاثة البيض", 88.5
        if c1['close'] < c1['open'] and c2['close'] > c2['open'] and b1 > 0 and b2 >= b1 * 0.55 and (c1['open'] + c1['close']) / 2.0 < c2['close'] < c1['open']:
            return "BUY", "خط الاختراق", 84.0
        if u_wick2 >= b2 * 2.0 and l_wick2 <= b2 * 0.35 and r2 > 0:
            return "BUY", "المطرقة المقلوبة", 81.5

    if max(c2['high'], c1['high']) >= past_high * 0.996:
        if c0['close'] < c0['open'] and c1['close'] < c1['open'] and c2['close'] < c2['open'] and c1['close'] < c0['close'] and c2['close'] < c1['close'] and b2 >= r2 * 0.45:
            return "SELL", "الغربان السوداء الثلاثة", 88.5
        if c1['close'] > c1['open'] and c2['close'] < c2['open'] and b1 > 0 and b2 >= b1 * 0.55 and c1['open'] < c2['close'] < (c1['open'] + c1['close']) / 2.0:
            return "SELL", "الغطاء السحابي الداكن", 84.0
        if l_wick2 >= b2 * 2.0 and u_wick2 <= b2 * 0.35 and r2 > 0:
            return "SELL", "الرجل المشنوق", 81.5

    return None, None, 0.0


def eval_trade(ltf_rec, ts_arr, entry_time, direction, entry, sl, tp, risk_usd, reward_usd, be_r):
    start = int(np.searchsorted(ts_arr, pd.Timestamp(entry_time).to_datetime64(), side='right'))
    cur_sl, dist = sl, abs(entry - sl)
    for bar in ltf_rec[start:start + 320]:
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
@st.cache_data(ttl=300, show_spinner=False)
def run_patterns_cached(_ver, df_trend, df_tf, rr=1.90, sh=0, eh=23, cap=1000.0, rpct=5.0, be_r=0.85, sl_atr=2.30, market_mode="عقود آجلة (Futures)", leverage=10):
    if df_trend.empty or df_tf.empty or len(df_trend) < 105 or len(df_tf) < 60:
        return pd.DataFrame()

    # 1. حساب الاتجاه العام على الفريم المختار (1h / 4h / 1d) عبر EMA 100
    df_tr = df_trend.sort_values('timestamp').reset_index(drop=True).copy()
    df_tr['ema100_tr'] = df_tr['close'].ewm(span=100, adjust=False).mean()
    df_tr['trend_up'] = df_tr['close'] > df_tr['ema100_tr']

    # 2. تجهيز فريم الدخول (5m / 15m / 30m / 1h)
    df_tf = df_tf.sort_values('timestamp').reset_index(drop=True).copy()
    df_tf['atr'] = np.maximum(df_tf['high'] - df_tf['low'], np.maximum(abs(df_tf['high'] - df_tf['close'].shift(1)), abs(df_tf['low'] - df_tf['close'].shift(1)))).rolling(14).mean()
    delta = df_tf['close'].diff()
    df_tf['rsi'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (-delta.where(delta < 0, 0).rolling(14).mean() + 1e-9))))
    df_tf['vol_ma'] = df_tf['volume'].rolling(24).mean()

    # ربط كل شمعة في فريم الدخول بحالة الاتجاه العام
    df_tf = pd.merge_asof(df_tf, df_tr[['timestamp', 'trend_up']], on='timestamp', direction='backward')
    df_tf['trend_up'] = df_tf['trend_up'].fillna(True)

    eff_lev = 1 if "Spot" in market_mode else leverage
    allow_sell = ("Futures" in market_mode)
    tf_rec, ts_arr = df_tf.to_dict('records'), df_tf['timestamp'].values
    last_ts, last_close, signals = pd.Timestamp(ts_arr[-1]), tf_rec[-1]['close'], []

    for i in range(50, len(tf_rec) - 1):
        row = tf_rec[i]
        if not (sh <= row['timestamp'].hour <= eh):
            continue
        vol_ratio = row['volume'] / ((row['vol_ma'] if pd.notna(row['vol_ma']) else 1.0) + 1e-9)
        if vol_ratio < 0.85:
            continue
        direction, pattern_name, base_ai = detect_candle_pattern(tf_rec, i)
        if not direction:
            continue

        atr = float(row['atr']) if pd.notna(row['atr']) else (row['high'] - row['low'])
        rsi = float(row['rsi']) if pd.notna(row['rsi']) else 50.0
        ai = round(min(base_ai + min(vol_ratio * 3.0, 9.5), 99.2), 1)
        win_slice = tf_rec[i + 1:i + 10]
        live_ok = (len(tf_rec) - 1 - i) <= 6

        margin_usd = cap * (rpct / 100.0)
        pos_usd = margin_usd * eff_lev

        if direction == "BUY" and row['trend_up'] and 35 < rsi < 66:
            sl = row['low'] - (atr * sl_atr)
            ent_c = next((r for r in win_slice if r['close'] > row['high']), None)
            if ent_c:
                entry = ent_c['close']
                tp = entry + (entry - sl) * rr
                sl_pct = max((entry - sl) / entry, 1e-6)
                risk_usd = pos_usd * sl_pct
                reward_usd = risk_usd * rr
                st_res, pnl = eval_trade(tf_rec, ts_arr, ent_c['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd, be_r)
                if st_res == "منتهية" and (last_ts - ent_c['timestamp']) <= pd.Timedelta(hours=24):
                    st_res = "جارية"
                signals.append({'timestamp': ent_c['timestamp'], 'type': 'شراء (BUY)', 'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': pattern_name, 'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})
            elif live_ok and last_close > sl:
                tp = row['high'] + (row['high'] - sl) * rr
                signals.append({'timestamp': row['timestamp'], 'type': 'شراء (BUY)', 'entry': round(row['high'], 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': pattern_name, 'ai': ai, 'status': 'بانتظار الدخول', 'pnl': 0.0})

        elif allow_sell and direction == "SELL" and (not row['trend_up']) and 34 < rsi < 65:
            sl = row['high'] + (atr * sl_atr)
            ent_c = next((r for r in win_slice if r['close'] < row['low']), None)
            if ent_c:
                entry = ent_c['close']
                tp = entry - (sl - entry) * rr
                sl_pct = max((sl - entry) / entry, 1e-6)
                risk_usd = pos_usd * sl_pct
                reward_usd = risk_usd * rr
                st_res, pnl = eval_trade(tf_rec, ts_arr, ent_c['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd, be_r)
                if st_res == "منتهية" and (last_ts - ent_c['timestamp']) <= pd.Timedelta(hours=24):
                    st_res = "جارية"
                signals.append({'timestamp': ent_c['timestamp'], 'type': 'بيع (SELL)', 'entry': round(entry, 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': pattern_name, 'ai': ai, 'status': st_res, 'pnl': round(pnl, 2)})
            elif live_ok and last_close < sl:
                tp = row['low'] - (sl - row['low']) * rr
                signals.append({'timestamp': row['timestamp'], 'type': 'بيع (SELL)', 'entry': round(row['low'], 4), 'sl': round(sl, 4), 'tp': round(tp, 4), 'fvg': pattern_name, 'ai': ai, 'status': 'بانتظار الدخول', 'pnl': 0.0})

    df_res = pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type']) if signals else pd.DataFrame()
    if not df_res.empty:
        df_res['cur_price'] = round(last_close, 4)
    return df_res


st.markdown("<style>.stApp{background:#09090d;color:#fff}.box{background:#15151f;border-radius:15px;padding:16px;text-align:center;border:1px solid #2a2a3c;margin-bottom:10px;direction:rtl}.rec{background:#161622;border-right:5px solid #00e676;border-radius:12px;padding:15px;margin-bottom:12px;direction:rtl;text-align:right;border:1px solid #262638}.sell{border-right-color:#ff1744}.badge{display:inline-block;padding:3px 10px;border-radius:8px;font-size:12px;font-weight:bold;background:#252538;color:#00e5ff;margin-right:6px}div.stButton>button{background:linear-gradient(90deg,#7c4dff,#00b0ff);color:#fff;font-weight:bold;border-radius:12px;width:100%;padding:10px}</style>", unsafe_allow_html=True)

with st.sidebar:
    cap = st.number_input("رأس المال ($):", 100.0, 1000000.0, 1000.0, 100.0)
    rpct = st.number_input("نسبة الهامش لكل صفقة (%):", 0.5, 50.0, 5.0, 0.5)
    sh, eh = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لقوة النموذج %:", 75, 95, 82)
    max_age_hrs = st.slider("أقصى عمر للصفقة الحية (ساعات):", 6, 48, 24)
    max_cards = st.slider("عدد التوصيات المعروضة:", 3, 12, 6)

st.markdown("<h2 style='direction:rtl;text-align:right'>🕯️ نظام النماذج الانعكاسية للشموع (AI)</h2>", unsafe_allow_html=True)

# --- الصف الأول: نوع التداول + الرافعة المالية + فريم الاتجاه العام + فريم الدخول ---
r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
with r1_c1:
    market_mode = st.selectbox("⚖️ نوع التداول:", ["عقود آجلة (Futures)", "سبوت (Spot)"])
with r1_c2:
    if "Spot" in market_mode:
        leverage = 1
        st.number_input("⚡ الرافعة (Spot = 1x):", 1, 1, 1, disabled=True)
    else:
        leverage = st.number_input("⚡ الرافعة المالية:", min_value=1, max_value=100, value=10, step=1)
with r1_c3:
    trend_tf = st.selectbox("🧭 الاتجاه العام:", ["1h", "4h", "1d"], index=0)
with r1_c4:
    tf_choice = st.selectbox("⏱️ فريم الدخول:", ["5m", "15m", "30m", "1h"], index=1)

# --- الصف الثاني: الفترة + الأصل + ATR + R:R ---
r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
with r2_c1: view = st.selectbox("📅 الفترة:", ["شهري (30 يوم)", "أسبوعي (7 أيام)"])
with r2_c2: asset = st.selectbox("🪙 الأصل:", ["الكل"] + list(ASSETS_MAP.keys()))
with r2_c3: sl_atr = st.number_input("🛑 وقف الخسارة (ATR):", 0.20, 10.00, 2.30, 0.10)
with r2_c4: rr = st.number_input("🎯 العائد (R : R):", 0.50, 10.00, 1.90, 0.10)

if st.button("🔍 فحص وتحديث الصفقات بالإعدادات المختارة"):
    st.cache_data.clear()

now_utc = pd.Timestamp.utcnow().tz_localize(None)
cutoff = now_utc - pd.Timedelta(days=30 if "شهري" in view else 7)
targets = ASSETS_MAP if asset == "الكل" else {asset: ASSETS_MAP[asset]}
all_frames = []

with st.spinner(f"جاري التحليل (اتجاه عام {trend_tf} | دخول {tf_choice} | رافعة {leverage}x)..."):
    for name, ticker in targets.items():
        df_tr = fetch_data(ticker, trend_tf)
        df_tf = df_tr if tf_choice == trend_tf else fetch_data(ticker, tf_choice)
        res = run_patterns_cached(CACHE_VER, df_tr, df_tf, rr, sh, eh, cap, rpct, 0.85, sl_atr, market_mode, leverage)
        if not res.empty:
            res = res[res['ai'] >= min_ai].copy()
            if not res.empty:
                res['asset'] = name
                all_frames.append(res)

all_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
st.markdown("<h4 style='direction:rtl;text-align:right;color:#b0b0c8'>📊 مؤشرات جودة الاستراتيجية</h4>", unsafe_allow_html=True)

if not all_df.empty:
    closed_df = all_df[(all_df['timestamp'] >= cutoff) & (~all_df['status'].isin(LIVE_STATUSES + ["منتهية"]))]
    wins = len(closed_df[closed_df['status'] == 'رابحة'])
    losses = len(closed_df[closed_df['status'] == 'خاسرة'])
    be_cnt = len(closed_df[closed_df['status'].str.contains('مؤمّنة', na=False)])
    win_rate = round((wins / (wins + losses)) * 100, 1) if (wins + losses) > 0 else 0.0
    net_pnl = round(closed_df['pnl'].sum(), 2)
else:
    wins = losses = be_cnt = win_rate = net_pnl = 0

m1, m2, m3, m4 = st.columns(4)
pnl_color = "#00e676" if net_pnl >= 0 else "#ff1744"
with m1: st.markdown(f"<div class='box'><div style='color:#9e9eb8'>الربح الصافي ($)</div><h3 style='color:{pnl_color};margin:5px 0'>{net_pnl:+.2f}$</h3></div>", unsafe_allow_html=True)
with m2: st.markdown(f"<div class='box'><div style='color:#9e9eb8'>نسبة النجاح</div><h3 style='color:#00b0ff;margin:5px 0'>{win_rate}%</h3></div>", unsafe_allow_html=True)
with m3: st.markdown(f"<div class='box'><div style='color:#9e9eb8'>صفقات رابحة</div><h3 style='color:#00e676;margin:5px 0'>{wins}</h3></div>", unsafe_allow_html=True)
