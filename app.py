import streamlit as st
import ccxt
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="ماسح AI الاحترافي: نظام الـ 9 عوامل", layout="wide")

MOROCCO_TZ = ZoneInfo("Africa/Casablanca")
now_ma = datetime.now(MOROCCO_TZ)

is_weekday = now_ma.weekday() < 5
market_open_time = now_ma.replace(hour=9, minute=30, second=0, microsecond=0)
market_close_time = now_ma.replace(hour=15, minute=30, second=0, microsecond=0)
is_casa_open = is_weekday and (market_open_time <= now_ma <= market_close_time)

# تنسيق البطاقات الداكنة المشابهة للتصميم المطلوب
st.markdown("""
<style>
.card-box {
    background-color: #161822;
    border: 1px solid #2a2d3d;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    margin-bottom: 10px;
}
.card-title { color: #9ca3af; font-size: 14px; margin-bottom: 6px; }
.card-val-white { color: #ffffff; font-size: 22px; font-weight: bold; }
.card-val-green { color: #10b981; font-size: 22px; font-weight: bold; }
.card-val-red { color: #ef4444; font-size: 22px; font-weight: bold; }
.card-val-gold { color: #f59e0b; font-size: 22px; font-weight: bold; }
.tp-card {
    background-color: #11221c;
    border: 1px solid #10b981;
    border-radius: 10px;
    padding: 12px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

st.title("🤖 ماسح الإشارات المؤكدة (نظام الـ 9 عوامل - 15M / 1H / 4H)")
st.info(
    f"🇲🇦 التوقيت الحالي في المغرب: **{now_ma.strftime('%Y-%m-%d %H:%M')}** | "
    f"بورصة الدار البيضاء: **{'🟢 مفتوحة' if is_casa_open else '🔴 مغلقة'}**"
)

CRYPTO_GOLD_ASSETS = [
    ("BTC/USDT", "البيتكوين (BTC)", "USDT"),
    ("ETH/USDT", "إيثيريوم (ETH)", "USDT"),
    ("SOL/USDT", "سولانا (SOL)", "USDT"),
    ("XRP/USDT", "ريبل (XRP)", "USDT"),
    ("ADA/USDT", "كاردانو (ADA)", "USDT"),
    ("LTC/USDT", "لايتكوين (LTC)", "USDT"),
    ("PAXG/USDT", "الذهب الرقمي (PAXG)", "USDT"),
    ("XAUT/USDT", "الذهب الفوري (XAUT)", "USDT")
]

CASABLANCA_STOCKS = [
    ("IAM", "اتصالات المغرب (IAM)", "MAD"),
    ("ATW", "التجاري وفا بنك (ATW)", "MAD"),
    ("MSA", "مرسى المغرب (MSA)", "MAD"),
    ("AKT", "أكديطال (AKT)", "MAD"),
    ("MNG", "مناجم (MNG)", "MAD"),
    ("BCP", "البنك الشعبي المركزي (BCP)", "MAD"),
    ("BOA", "بنك أفريقيا (BOA)", "MAD")
]

@st.cache_data(ttl=600)
def fetch_ohlcv_ccxt(symbol, timeframe='15m', limit=500):
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange = getattr(ccxt, ex_id)({'enableRateLimit': True})
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 210:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert(MOROCCO_TZ)
                return df
        except Exception:
            continue
    return None

@st.cache_data(ttl=1800)
def fetch_casablanca_stock(ticker, market_is_open):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    suffixes = ['.CS', '.PA'] if ticker == 'IAM' else ['.CS']
    for suf in suffixes:
        try:
            hist_url = f"https://yahoo.com{ticker}{suf}?interval=1d&range=2y"
            hr = requests.get(hist_url, headers=headers, timeout=8)
            if hr.status_code == 200:
                hjson = hr.json()
                res = hjson['chart']['result']
                quote = res['indicators']['quote']
                df = pd.DataFrame({
                    'timestamp': pd.to_datetime(res['timestamp'], unit='s', utc=True).dt.tz_convert(MOROCCO_TZ),
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'close': quote['close'],
                    'volume': quote['volume']
                }).dropna()
                if len(df) > 210:
                    if market_is_open and df['timestamp'].iloc[-1].date() == now_ma.date():
                        df = df.iloc[:-1]
                    return df
        except Exception:
            continue
    return None

def get_ema_trend(df):
    if df is None or len(df) < 205:
        return 0
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    ema200 = df['close'].ewm(span=200).mean().iloc[-1]
    close = df['close'].iloc[-1]
    if close > ema50 and ema50 > ema200:
        return 1
    elif close < ema50 and ema50 < ema200:
        return -1
    return 0

def add_indicators_15m(df):
    df = df.copy().reset_index(drop=True)
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_sig'] = df['macd'].ewm(span=9).mean()
    
    # ATR 14
    tr1 = df['high'] - df['low']
    tr2 = np.abs(df['high'] - df['close'].shift())
    tr3 = np.abs(df['low'] - df['close'].shift())
    df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    df['atr_ma'] = df['atr'].rolling(50).mean()
    
    # Volume MA
    df['vol_ma'] = df['volume'].rolling(20).mean()
    
    # الهيكل والمستويات (50 شمعة)
    df['high_50'] = df['high'].rolling(50).max().shift(1)
    df['low_50'] = df['low'].rolling(50).min().shift(1)
    df['high_20'] = df['high'].rolling(20).max().shift(1)
    df['low_20'] = df['low'].rolling(20).min().shift(1)
    return df
def evaluate_9_factors(df, idx, trend_4h, trend_1h, allow_short=True):
    row = df.iloc[idx]
    prev = df.iloc[idx - 1]
    prev2 = df.iloc[idx - 2]
    
    close = row['close']
    atr = row['atr']
    if np.isnan(atr) or atr <= 0:
        return None

    # 1. تحديد نظام السوق وتكييف الأوزان
    high_volatility = atr > (row['atr_ma'] * 1.25)
    is_trending = (trend_4h == trend_1h) and (trend_4h != 0)
    
    if is_trending:
        w = {'t4h': 16, 't1h': 16, 'bos': 15, 'pat': 14, 'mom': 10, 'vol': 10, 'liq': 8, 'brk': 6, 'sr': 5}
    else:
        w = {'t4h': 12, 't1h': 13, 'bos': 15, 'pat': 16, 'mom': 11, 'vol': 10, 'liq': 9, 'brk': 8, 'sr': 6}

    # 2. حساب العوامل الفنية على الشمعة
    # هيكل السوق BOS / CHOCH
    bos_dir = 1 if close > row['high_20'] else (-1 if close < row['low_20'] else 0)
    
    # النمط (ابتلاع شرائي/بيعي أو كسر خط اتجاه RSI)
    bull_engulf = (close > row['open']) and (prev['close'] < prev['open']) and (close > prev['open']) and (row['open'] <= prev['close'])
    bear_engulf = (close < row['open']) and (prev['close'] > prev['open']) and (close < prev['open']) and (row['open'] >= prev['close'])
    pat_dir = 1 if bull_engulf else (-1 if bear_engulf else 0)
    
    # الزخم (RSI + MACD + EMA20)
    mom_dir = 1 if (row['macd'] > row['macd_sig'] and row['rsi'] > 50 and close > row['ema_20']) else (
             -1 if (row['macd'] < row['macd_sig'] and row['rsi'] < 50 and close < row['ema_20']) else 0)
    
    # الحجم (Volume Spike)
    vol_strong = row['volume'] > (row['vol_ma'] * 1.15)
    
    # السيولة (Sweep + FVG)
    bull_sweep = (row['low'] < row['low_20']) and (close > row['low_20'])
    bear_sweep = (row['high'] > row['high_20']) and (close < row['high_20'])
    bull_fvg = row['low'] > prev2['high']
    bear_fvg = row['high'] < prev2['low']
    liq_dir = 1 if (bull_sweep or bull_fvg) else (-1 if (bear_sweep or bear_fvg) else 0)
    
    # كسر أو ارتداد من EMA50
    brk_dir = 1 if (prev['close'] <= prev['ema_50'] and close > row['ema_50']) else (
             -1 if (prev['close'] >= prev['ema_50'] and close < row['ema_50']) else 0)
    
    # دعم / مقاومة (قرب قاع أو قمة 50 شمعة)
    sr_dir = 1 if abs(close - row['low_50']) < (1.5 * atr) else (-1 if abs(row['high_50'] - close) < (1.5 * atr) else 0)

    # تقييم الاتجاهين (LONG = 1, SHORT = -1)
    best_dir = 0
    best_score = 0
    
    directions_to_check = [1, -1] if allow_short else [1]
    for d in directions_to_check:
        # شرط المحفز الواحد على الأقل: نمط مؤكد، أو BOS مع حجم، أو Pullback، أو Sweep
        has_trigger = (pat_dir == d) or (bos_dir == d and vol_strong) or (liq_dir == d) or (brk_dir == d)
        if not has_trigger:
            continue
            
        # شرط عدم تعارض أكثر من عامل رئيسي واحد من خمسة
        main_factors = [trend_4h, trend_1h, bos_dir, pat_dir, mom_dir]
        conflicts = sum(1 for f in main_factors if f == -d)
        if conflicts > 1:
            continue

        score = 0
        if trend_4h == d: score += w['t4h']
        if trend_1h == d: score += w['t1h']
        if bos_dir == d: score += w['bos']
        if pat_dir == d: score += w['pat']
        if mom_dir == d: score += w['mom']
        if vol_strong: score += w['vol']
        if liq_dir == d: score += w['liq']
        if brk_dir == d: score += w['brk']
        if sr_dir == d: score += w['sr']

        min_req = 75 if high_volatility else 70
        if score >= min_req and score > best_score:
            best_score = score
            best_dir = d

    if best_dir == 0:
        return None

    # حساب SL و TP1, TP2, TP3 وفق الهيكل السعري
    if best_dir == 1:
        swing_low = df.iloc[max(0, idx - 12) : idx + 1]['low'].min()
        raw_sl = swing_low - (0.3 * atr)
        risk = min(close - raw_sl, 4.0 * atr)
        if risk <= 0:
            return None
        sl = close - risk
        tp1 = close + (1.0 * risk)
        tp2 = max(row['high_50'], close + (1.6 * risk)) # R:R >= 1.5 عند TP2
        tp3 = close + (2.5 * risk)
    else:
        swing_high = df.iloc[max(0, idx - 12) : idx + 1]['high'].max()
        raw_sl = swing_high + (0.3 * atr)
        risk = min(raw_sl - close, 4.0 * atr)
        if risk <= 0:
            return None
        sl = close + risk
        tp1 = close - (1.0 * risk)
        tp2 = min(row['low_50'], close - (1.6 * risk)) # R:R >= 1.5 عند TP2
        tp3 = close - (2.5 * risk)

    return {
        "dir": best_dir,
        "score": min(100, int(best_score)),
        "entry": close,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk_pct": risk / close
    }

def backtest_and_scan_asset(df_15m, trend_4h, trend_1h, symbol, label, currency, is_stock=False):
    df = add_indicators_15m(df_15m)
    allow_short = not is_stock
    
    # المحاكاة التاريخية لآخر 30 يوماً مع احترام (صفقة واحدة نشطة + انتظار 5 شموع بعد الإغلاق)
    one_month_ago = now_ma - timedelta(days=30)
    trades_history = []
    cooldown_until = 0

    for i in range(205, len(df) - 1):
        if i < cooldown_until or df.loc[i, 'timestamp'] < one_month_ago:
            continue
            
        sig = evaluate_9_factors(df, i, trend_4h, trend_1h, allow_short=allow_short)
        if sig:
            # تتبع الصفقة حتى ضرب SL أو TP3 (وإذا لامست الشمعة SL و TP معاً يُحسب SL أولاً)
            sl, tp1, tp2, tp3 = sig['sl'], sig['tp1'], sig['tp2'], sig['tp3']
            entry = sig['entry']
            d = sig['dir']
            exit_price = entry
            won = False
            close_idx = len(df) - 1

            for j in range(i + 1, len(df)):
                f = df.iloc[j]
                if d == 1:
                    if f['low'] <= sl: # SL يُحسب أولاً
                        exit_price = sl
                        won = False
                        close_idx = j
                        break
                    elif f['high'] >= tp3:
                        exit_price = tp3
                        won = True
                        close_idx = j
                        break
                else:
                    if f['high'] >= sl: # SL يُحسب أولاً
                        exit_price = sl
                        won = False
                        close_idx = j
                        break
                    elif f['low'] <= tp3:
                        exit_price = tp3
                        won = True
                        close_idx = j
                        break

            # إذا لم تضرب TP3 أو SL بنهاية البيانات، نحسبها على آخر سعر متاح إن حققت TP1
            if close_idx == len(df) - 1:
                last_c = df.iloc[-1]['close']
                if (d == 1 and last_c >= tp1) or (d == -1 and last_c <= tp1):
                    exit_price = tp1
                    won = True
                else:
                    continue

            pct_ret = ((exit_price - entry) / entry) if d == 1 else ((entry - exit_price) / entry)
            trades_history.append({"won": won, "pct_ret": pct_ret})
            cooldown_until = close_idx + 5 # انتظار 5 شموع بعد الإغلاق

    # فحص آخر شمعة مكتملة للإشارة الحالية
    curr_sig = evaluate_9_factors(df, len(df) - 1, trend_4h, trend_1h, allow_short=allow_short)
    active_opp = None
    if curr_sig:
        decimals = 2 if curr_sig['entry'] >= 10 else (4 if curr_sig['entry'] >= 0.1 else 5)
        active_opp = {
            "symbol": symbol,
            "label": label,
            "currency": currency,
            "tf": "1D" if is_stock else "15M",
            "dir": "شراء (LONG)" if curr_sig['dir'] == 1 else "بيع (SHORT)",
            "is_long": curr_sig['dir'] == 1,
            "score": curr_sig['score'],
            "entry": round(curr_sig['entry'], decimals),
            "sl": round(curr_sig['sl'], decimals),
            "tp1": round(curr_sig['tp1'], decimals),
            "tp2": round(curr_sig['tp2'], decimals),
            "tp3": round(curr_sig['tp3'], decimals),
        }

    return {"history": trades_history, "active": active_opp}

# --- إعدادات المحافظ المالية ---
scope = st.radio(
    "اختر نطاق المسح:",
    ["الكل (كريبتو + ذهب بـ USDT & بورصة الدار البيضاء بـ MAD)", "العملات الرقمية والذهب فقط (USDT)", "بورصة الدار البيضاء فقط (MAD)"],
    horizontal=True
)

c_usdt, c_mad = st.columns(2)
with c_usdt:
    st.markdown("### 💵 محفظة الكريبتو والذهب (USDT)")
    mode_usdt = st.selectbox("نوع الحساب (USDT):", ["عقود آجلة (Futures - شراء وبيع)", "سبوت (Spot - شراء فقط)"])
    lev_usdt = 1 if "سبوت" in mode_usdt else st.slider("الرافعة المالية (USDT):", 2, 20, 5)
    cap_usdt = st.number_input("رأس المال (USDT):", min_value=100.0, value=1000.0, step=100.0)
    alloc_usdt = st.slider("حجم الصفقة (% من محفظة USDT):", 5, 50, 10)

with c_mad:
    st.markdown("### 🇲🇦 محفظة بورصة الدار البيضاء (MAD)")
    st.selectbox("نوع الحساب (MAD):", ["سبوت (Spot - شراء فقط بدون رافعة)"], disabled=True)
    cap_mad = st.number_input("رأس المال (MAD):", min_value=1000.0, value=10000.0, step=1000.0)
    alloc_mad = st.slider("حجم الصفقة (% من محفظة MAD):", 5, 50, 15)

if st.button("تشغيل الماسح واستخراج أقوى صفقة واحدة + سجل الأداء 🚀", type="primary"):
    usdt_hist, mad_hist = [], []
    all_candidates = []

    tasks = []
    if "الرقمية" in scope or "الكل" in scope:
        for s, l, c in CRYPTO_GOLD_ASSETS:
            tasks.append((s, l, c, False))
    if "الدار البيضاء" in scope or "الكل" in scope:
        for s, l, c in CASABLANCA_STOCKS:
            tasks.append((s, l, c, True))

    prog = st.progress(0)
    status = st.empty()

    for idx, (sym, lbl, cur, is_stock) in enumerate(tasks):
        status.text(f"⏳ تحليل العوامل الـ 9 لـ {lbl}...")
        if is_stock:
            df_d = fetch_casablanca_stock(sym, is_casa_open)
            if df_d is not None:
                t_w = get_ema_trend(df_d.iloc[::5])
                t_d = get_ema_trend(df_d)
