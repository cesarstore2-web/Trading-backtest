import streamlit as st
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="نظام النماذج الانعكاسية AI", layout="wide")

CACHE_VER = "v2.1"

ASSETS_MAP = {
    "بيتكوين (BTC)": "BTCUSDT",
    "إيثيريوم (ETH)": "ETHUSDT",
    "سولانا (SOL)": "SOLUSDT",
    "ريبل (XRP)": "XRPUSDT",
    "بينانس (BNB)": "BNBUSDT",
    "كاردانو (ADA)": "ADAUSDT",
    "دوجكوين (DOGE)": "DOGEUSDT",
    "أفالانش (AVAX)": "AVAXUSDT"
}

TIMEFRAMES_MAP = {
    "5 دقائق (5m)": "5m",
    "15 دقيقة (15m)": "15m",
    "30 دقيقة (30m)": "30m",
    "1 ساعة (1h)": "1h"
}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_data(symbol, interval, limit=1000):
    url = "https://binance.com"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if not isinstance(data, list):
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    except Exception:
        return pd.DataFrame()

def detect_candle_pattern(records, i):
    if i < 2:
        return None, None, 0.0
    c = records[i]
    p = records[i - 1]

    c_body = abs(c['close'] - c['open'])
    c_range = c['high'] - c['low']
    if c_range == 0:
        return None, None, 0.0

    upper_wick = c['high'] - max(c['open'], c['close'])
    lower_wick = min(c['open'], c['close']) - c['low']
    p_body = abs(p['close'] - p['open'])

    # 1. الابتلاع الشرائي (Bullish Engulfing)
    if p['close'] < p['open'] and c['close'] > c['open']:
        if c['close'] >= p['open'] and c['open'] <= p['close'] and c_body > p_body * 1.1:
            return "BUY", "ابتلاع شرائي (Bullish Engulfing)", 83.5

    # 2. الابتلاع البيعي (Bearish Engulfing)
    if p['close'] > p['open'] and c['close'] < c['open']:
        if c['close'] <= p['open'] and c['open'] >= p['close'] and c_body > p_body * 1.1:
            return "SELL", "ابتلاع بيعي (Bearish Engulfing)", 83.5

    # 3. المطرقة / بين بار شرائي (Bullish Pin Bar / Hammer)
    if lower_wick >= c_body * 2.2 and upper_wick <= c_body * 0.6 and c['close'] >= c['open']:
        return "BUY", "بين بار شرائي (Hammer)", 81.5

    # 4. الشهاب / بين بار بيعي (Bearish Pin Bar / Shooting Star)
    if upper_wick >= c_body * 2.2 and lower_wick <= c_body * 0.6 and c['close'] <= c['open']:
        return "SELL", "بين بار بيعي (Shooting Star)", 81.5

    return None, None, 0.0

def eval_trade(records, ts_arr, entry_ts, direction, entry, sl, tp, risk_usd, reward_usd, be_r):
    start_idx = int(np.searchsorted(ts_arr, np.datetime64(entry_ts))) + 1
    curr_sl = sl
    be_moved = False
    risk_dist = abs(entry - sl)

    for j in range(start_idx, len(records)):
        bar = records[j]
        if direction == "BUY":
            if bar['low'] <= curr_sl:
                return "منتهية", (0.0 if be_moved else -risk_usd)
            if bar['high'] >= tp:
                return "منتهية", reward_usd
            if not be_moved and bar['high'] >= entry + (risk_dist * be_r):
                curr_sl = entry
                be_moved = True
        else:
            if bar['high'] >= curr_sl:
                return "منتهية", (0.0 if be_moved else -risk_usd)
            if bar['low'] <= tp:
                return "منتهية", reward_usd
            if not be_moved and bar['low'] <= entry - (risk_dist * be_r):
                curr_sl = entry
                be_moved = True

    return "جارية", 0.0

@st.cache_data(ttl=300, show_spinner=False)
def run_patterns_cached(_ver, df_4h, df_entry, rr=1.90, sh=0, eh=23, cap=1000.0, rpct=5.0, be_r=0.85, sl_atr=2.30, market_mode="عقود آجلة (Futures)", leverage=10):
    if df_4h.empty or df_entry.empty or len(df_4h) < 105 or len(df_entry) < 60:
        return pd.DataFrame()

    # 1. الاتجاه العام مثبت في الخفاء على فريم 4 ساعات (EMA 100) مع إزاحة شمعة لمنع تسرب المستقبل
    df_tr = df_4h.sort_values('timestamp').reset_index(drop=True).copy()
    df_tr['ema100_4h'] = df_tr['close'].ewm(span=100, adjust=False).mean()
    df_tr['trend_up'] = (df_tr['close'] > df_tr['ema100_4h']).shift(1)

    # 2. فريم الدخول المختار من النافذة
    df_tf = df_entry.sort_values('timestamp').reset_index(drop=True).copy()
    df_tf['atr'] = np.maximum(
        df_tf['high'] - df_tf['low'],
        np.maximum(abs(df_tf['high'] - df_tf['close'].shift(1)), abs(df_tf['low'] - df_tf['close'].shift(1)))
    ).rolling(14).mean()
    
    delta = df_tf['close'].diff()
    df_tf['rsi'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).rolling(14).mean() / (-delta.where(delta < 0, 0).rolling(14).mean() + 1e-9))))
    df_tf['vol_ma'] = df_tf['volume'].rolling(24).mean()

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
                risk_usd = min(pos_usd * sl_pct, margin_usd) # حماية من تجاوز الهامش
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
                risk_usd = min(pos_usd * sl_pct, margin_usd) # حماية من تجاوز الهامش
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

# --- تنسيق CSS ---
st.markdown("""
<style>
.stApp{background:#09090d;color:#fff}
.box{background:#15151f;border-radius:15px;padding:16px;text-align:center;border:1px solid #2a2a3c;margin-bottom:10px;direction:rtl}
.rec{background:#161622;border-right:5px solid #00e676;border-radius:12px;padding:15px;margin-bottom:12px;direction:rtl;text-align:right;border:1px solid #262638}
.sell{border-right-color:#ff1744}
.badge{display:inline-block;padding:3px 10px;border-radius:8px;font-size:12px;font-weight:bold;background:#252538;color:#00e5ff;margin-right:6px}
div.stButton>button{background:linear-gradient(90deg,#7c4dff,#00b0ff);color:#fff;font-weight:bold;border-radius:12px;width:100%;padding:10px}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    cap = st.number_input("رأس المال ($):", 100.0, 1000000.0, 1000.0, 100.0)
    rpct = st.number_input("نسبة الهامش لكل صفقة (%):", 0.5, 50.0, 5.0, 0.5)
    sh, eh = st.slider("ساعات العمل (UTC):", 0, 23, (0, 23))
    min_ai = st.slider("الحد الأدنى لقوة النموذج %:", 75, 95, 82)
    max_age_hrs = st.slider("أقصى عمر للصفقة الحية (ساعات):", 6, 48, 24)
    max_cards = st.slider("عدد التوصيات المعروضة:", 3, 12, 6)

