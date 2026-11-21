import streamlit as st
import ccxt
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from lightgbm import LGBMClassifier

# إعداد صفحة التطبيق
st.set_page_config(page_title="ماسح AI: استراتيجية كسر ترند RSI", layout="wide")

# ضبط التوقيت المغربي الرسمي (Africa/Casablanca)
MOROCCO_TZ = ZoneInfo("Africa/Casablanca")
now_ma = datetime.now(MOROCCO_TZ)

# التحقق من حالة جلسة بورصة الدار البيضاء
is_weekday = now_ma.weekday() < 5
market_open_time = now_ma.replace(hour=9, minute=30, second=0, microsecond=0)
market_close_time = now_ma.replace(hour=15, minute=30, second=0, microsecond=0)
is_casa_open = is_weekday and (market_open_time <= now_ma <= market_close_time)

st.title("🤖 ماسح الذكاء الاصطناعي: استراتيجية كسر ترند RSI")
st.caption("استراتيجية: RSI Trendline Breakout (في مناطق التشبع) + فلترة وتأكيد عبر نموذج LightGBM")

st.info(
    f"🇲🇦 التوقيت الحالي في المغرب: **{now_ma.strftime('%Y-%m-%d %H:%M')}** | "
    f"بورصة الدار البيضاء: **{'🟢 مفتوحة (تحليل على آخر إغلاق مكتمل)' if is_casa_open else '🔴 مغلقة (تحليل على الإغلاق الرسمي)'}**"
)

# 1. قائمة العملات الرقمية والذهب (فريم يومي 1D)
CRYPTO_GOLD_ASSETS = [
    ("BTC/USDT", "عملة رقمية", "USDT"),
    ("ETH/USDT", "عملة رقمية", "USDT"),
    ("SOL/USDT", "عملة رقمية", "USDT"),
    ("XLM/USDT", "عملة رقمية", "USDT"),
    ("ZEC/USDT", "عملة رقمية", "USDT"),
    ("XRP/USDT", "عملة رقمية", "USDT"),
    ("HBAR/USDT", "عملة رقمية", "USDT"),
    ("ADA/USDT", "عملة رقمية", "USDT"),
    ("LTC/USDT", "عملة رقمية", "USDT"),
    ("PAXG/USDT", "ذهب رقمي (PAXG)", "USDT"),
    ("XAUT/USDT", "ذهب (Tether Gold)", "USDT")
]

# 2. قائمة أبرز أسهم بورصة الدار البيضاء (فريم يومي 1D - بالدرهم المغربي)
CASABLANCA_STOCKS = [
    ("IAM", "اتصالات المغرب (IAM)", "MAD"),
    ("ATW", "التجاري وفا بنك (ATW)", "MAD"),
    ("MSA", "مرسى المغرب (MSA)", "MAD"),
    ("AKT", "أكديطال (AKT)", "MAD"),
    ("MNG", "مناجم (MNG)", "MAD"),
    ("BCP", "البنك الشعبي المركزي (BCP)", "MAD"),
    ("BOA", "بنك أفريقيا (BOA)", "MAD"),
    ("TQM", "طاقة المغرب (TQM)", "MAD"),
    ("LHM", "لافارج هولسيم (LHM)", "MAD"),
    ("CSR", "كوسومار (CSR)", "MAD")
]

@st.cache_data(ttl=1800)
def fetch_crypto_gold(symbol, timeframe='1d', limit=730):
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange = getattr(ccxt, ex_id)({'enableRateLimit': True})
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 200:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert(MOROCCO_TZ)
                return df, exchange.name
        except Exception:
            continue
    return None, None

@st.cache_data(ttl=1800)
def fetch_casablanca_stock(ticker, market_is_open):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    suffixes = ['.CS', '.PA'] if ticker == 'IAM' else ['.CS']
    for suf in suffixes:
        try:
            hist_url = f"https://yahoo.com{ticker}{suf}?interval=1d&range=3y"
            hr = requests.get(hist_url, headers=headers, timeout=8)
            if hr.status_code == 200:
                hjson = hr.json()
                res = hjson['chart']['result'][0]
                quote = res['indicators']['quote'][0]
                df = pd.DataFrame({
                    'timestamp': pd.to_datetime(res['timestamp'], unit='s', utc=True).dt.tz_convert(MOROCCO_TZ),
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'close': quote['close'],
                    'volume': quote['volume']
                }).dropna()
                if len(df) > 200:
                    last_candle_date = df['timestamp'].iloc[-1].date()
                    if market_is_open and last_candle_date == now_ma.date():
                        df = df.iloc[:-1]
                    return df, "Bourse de Casablanca"
        except Exception:
            continue
    return None, None

def detect_rsi_trendline_strategy(df):
    df = df.copy().reset_index(drop=True)
    
    # حساب RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # مؤشرات مساعدة للذكاء الاصطناعي
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
    df['dist_ema50'] = (df['close'] - df['ema_50']) / df['ema_50']
    df['rsi_slope'] = df['rsi'].diff(3)
    df['vol_ratio'] = df['volume'] / (df['volume'].rolling(20).mean() + 1e-9)
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    df['volatility'] = df['atr'] / df['close']

    # تحديد القمم والقيعان المحلية (Swing Highs / Lows)
    df['swing_low'] = df['low'][(df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))]
    df['swing_high'] = df['high'][(df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))]

    signals = np.zeros(len(df))
    stop_losses = np.full(len(df), np.nan)
    take_profits = np.full(len(df), np.nan)
    targets = np.full(len(df), np.nan)

    lookback = 20

    for i in range(lookback + 15, len(df)):
        window = df.iloc[i - lookback : i]
        curr_close = df.loc[i, 'close']
        prev_close = df.loc[i - 1, 'close']
        curr_rsi = df.loc[i, 'rsi']
        prev_rsi = df.loc[i - 1, 'rsi']
        atr = df.loc[i, 'atr']

        # 1. فرصة البيع (SHORT POSITION) - كسر ترند صاعد في التشبع الشرائي
        s_lows = window.dropna(subset=['swing_low'])
        if len(s_lows) >= 2:
            p1, p2 = s_lows.iloc[-2], s_lows.iloc[-1]
            if p2['low'] > p1['low'] and p2['rsi'] > p1['rsi']:
                slope_p = (p2['low'] - p1['low']) / (p2.name - p1.name)
                trend_p_curr = p2['low'] + slope_p * (i - p2.name)
                trend_p_prev = p2['low'] + slope_p * ((i - 1) - p2.name)
                
                slope_r = (p2['rsi'] - p1['rsi']) / (p2.name - p1.name)
                trend_r_curr = p2['rsi'] + slope_r * (i - p2.name)
                trend_r_prev = p2['rsi'] + slope_r * ((i - 1) - p2.name)

                was_overbought = window['rsi'].max() >= 65
                rsi_broke = (prev_rsi >= trend_r_prev) and (curr_rsi < trend_r_curr)
                price_broke = (prev_close >= trend_p_prev) and (curr_close < trend_p_curr)

                if was_overbought and rsi_broke and price_broke:
                    recent_high = df.iloc[i - 10 : i + 1]['high'].max()
                    sl = recent_high + (0.2 * atr)
                    risk = sl - curr_close
                    if risk > 0:
                        tp = curr_close - (2.0 * risk)
                        signals[i] = -1
                        stop_losses[i] = sl
                        take_profits[i] = tp
        # 2. فرصة الشراء (LONG POSITION) - كسر ترند هابط في التشبع البيعي
        if signals[i] == 0:
            s_highs = window.dropna(subset=['swing_high'])
            if len(s_highs) >= 2:
                p1, p2 = s_highs.iloc[-2], s_highs.iloc[-1]
                if p2['high'] < p1['high'] and p2['rsi'] < p1['rsi']:
                    slope_p = (p2['high'] - p1['high']) / (p2.name - p1.name)
                    trend_p_curr = p2['high'] + slope_p * (i - p2.name)
                    trend_p_prev = p2['high'] + slope_p * ((i - 1) - p2.name)

                    slope_r = (p2['rsi'] - p1['rsi']) / (p2.name - p1.name)
                    trend_r_curr = p2['rsi'] + slope_r * (i - p2.name)
                    trend_r_prev = p2['rsi'] + slope_r * ((i - 1) - p2.name)

                    was_oversold = window['rsi'].min() <= 35
                    rsi_broke = (prev_rsi <= trend_r_prev) and (curr_rsi > trend_r_curr)
                    price_broke = (prev_close <= trend_p_prev) and (curr_close > trend_p_curr)

                    if was_oversold and rsi_broke and price_broke:
                        recent_low = df.iloc[i - 10 : i + 1]['low'].min()
                        sl = recent_low - (0.2 * atr)
                        risk = curr_close - sl
                        if risk > 0:
                            tp = curr_close + (2.0 * risk)
                            signals[i] = 1
                            stop_losses[i] = sl
                            take_profits[i] = tp

        # 3. تقييم نتيجة الإشارات التاريخية لتدريب الذكاء الاصطناعي
        if signals[i] != 0 and i < len(df) - 1:
            future = df.iloc[i + 1 : min(i + 15, len(df))]
            sl, tp = stop_losses[i], take_profits[i]
            outcome = np.nan
            for _, f_row in future.iterrows():
                if signals[i] == -1:
                    if f_row['high'] >= sl:
                        outcome = 0
                        break
                    if f_row['low'] <= tp:
                        outcome = 1
                        break
                elif signals[i] == 1:
                    if f_row['low'] <= sl:
                        outcome = 0
                        break
                    if f_row['high'] >= tp:
                        outcome = 1
                        break
            targets[i] = outcome

    df['signal'] = signals
    df['stop_loss'] = stop_losses
    df['take_profit'] = take_profits
    df['target'] = targets
    return df

def analyze_with_ai(df, symbol, label, currency, is_stock=False):
    df = detect_rsi_trendline_strategy(df)
    features = ['signal', 'rsi', 'rsi_slope', 'dist_ema20', 'dist_ema50', 'vol_ratio', 'volatility']
    
    hist_signals = df.iloc[:-1].dropna(subset=['target'] + features)
    if len(hist_signals) < 12:
        return None

    split_idx = max(8, int(len(hist_signals) * 0.7))
    train_df = hist_signals.iloc[:split_idx]
    test_df = hist_signals.iloc[split_idx:]

    model = LGBMClassifier(n_estimators=80, learning_rate=0.05, max_depth=3, random_state=42, verbose=-1)
    model.fit(train_df[features], train_df['target'].astype(int))

    wins, losses = 0, 0
    if len(test_df) > 0:
        test_probs = model.predict_proba(test_df[features])[:, 1] * 100
        for prob, actual in zip(test_probs, test_df['target']):
            if prob >= 60:
                if actual == 1:
                    wins += 1
                else:
                    losses += 1

    curr = df.iloc[-1]
    sig = int(curr['signal'])
    
    if sig == 0 or (is_stock and sig == -1):
        return {"has_signal": False, "wins": wins, "losses": losses}

    curr_X = df.iloc[-1:][features]
    ai_confidence = float(model.predict_proba(curr_X)[0][1]) * 100

    entry_price = float(curr['close'])
    decimals = 2 if entry_price >= 10 else (4 if entry_price >= 0.1 else 5)
    direction = "بيع (SHORT) 🔴 - كسر ترند صاعد" if sig == -1 else "شراء (LONG) 🟢 - كسر ترند هابط"

    return {
        "has_signal": True,
        "الأصل": label,
        "الرمز": symbol,
        "الاتجاه": direction,
        "تأكيد الذكاء الاصطناعي (%)": round(ai_confidence, 1),
        "سعر الدخول": round(entry_price, decimals),
        "وقف الخسارة (Swing)": round(float(curr['stop_loss']), decimals),
        "جني الأرباح (1:2)": round(float(curr['take_profit']), decimals),
        "العملة": currency,
        "مؤشر RSI": round(float(curr['rsi']), 1),
        "wins": wins,
        "losses": losses
    }

# --- واجهة المستخدم ---
scope = st.radio(
    "اختر نطاق الفحص (الفريم اليومي 1D لجميع الأسواق):",
    [
        "الكل (كريبتو + ذهب + بورصة الدار البيضاء)",
        "العملات الرقمية والذهب فقط",
        "بورصة الدار البيضاء فقط"
    ]
)

min_conf = st.slider("الحد الأدنى لتأكيد الذكاء الاصطناعي على الكسر (%):", 50, 90, 75)

if st.button("بدء الفحص ومراقبة الكسورات بالذكاء الاصطناعي 🚀", type="primary"):
    opportunities = []
    total_wins = 0
    total_losses = 0

    assets_to_scan = []
    if "الكل" in scope or "الرقمية" in scope:
        for sym, lbl, cur in CRYPTO_GOLD_ASSETS:
            assets_to_scan.append((sym, lbl, cur, False))
    if "الكل" in scope or "الدار البيضاء" in scope:
        for sym, lbl, cur in CASABLANCA_STOCKS:
            assets_to_scan.append((sym, lbl, cur, True))

    progress = st.progress(0)
    for idx, (sym, lbl, cur, is_stock) in enumerate(assets_to_scan):
        if is_stock:
            df, _ = fetch_casablanca_stock(sym, is_casa_open)
        else:
            df, _ = fetch_crypto_gold(sym, timeframe='1d')

        if df is not None:
            res = analyze_with_ai(df, sym, lbl, cur, is_stock=is_stock)
            if res:
                total_wins += res["wins"]
                total_losses += res["losses"]
                if res["has_signal"] and res["تأكيد الذكاء الاصطناعي (%)"] >= min_conf:
                    opportunities.append({
                        k: v for k, v in res.items() if k not in ["has_signal", "wins", "losses"]
                    })

        progress.progress((idx + 1) / len(assets_to_scan))

    st.divider()
    if opportunities:
        st.success(f"✅ تم العثور على {len(opportunities)} فرصة كسر ترند RSI مؤكدة من الذكاء الاصطناعي:")
        st.dataframe(pd.DataFrame(opportunities), use_container_width=True)
    else:
        st.warning("⏳ لا يوجد حالياً أي كسر لخط اتجاه RSI يستوفي شروط التشبع وتأكيد الذكاء الاصطناعي. (الانتظار يحمي رأس المال).")

    total_trades = total_wins + total_losses
    win_rate = round((total_wins / total_trades * 100), 1) if total_trades > 0 else 0.0
    
    st.subheader("📊 أداء الاستراتيجية المؤكدة بالذكاء الاصطناعي (اختبار رجعي)")
    col1, col2, col3 = st.columns(3)
    col1.metric("نسبة نجاح الكسورات المؤكدة (%)", f"{win_rate}%")
    col2.metric("صفقات حققت الهدف (1:2)", f"✅ {total_wins}")
    col3.metric("صفقات ضربت وقف الخسارة", f"❌ {total_losses}")
