import streamlit as st
import ccxt
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score

# إعداد صفحة التطبيق
st.set_page_config(page_title="ماسح AI الشامل: كريبتو، ذهب، وبورصة الدار البيضاء", layout="wide")

# ضبط التوقيت المغربي الرسمي (Africa/Casablanca)
MOROCCO_TZ = ZoneInfo("Africa/Casablanca")
now_ma = datetime.now(MOROCCO_TZ)

# التحقق من حالة جلسة بورصة الدار البيضاء
is_weekday = now_ma.weekday() < 5
market_open_time = now_ma.replace(hour=9, minute=30, second=0, microsecond=0)
market_close_time = now_ma.replace(hour=15, minute=30, second=0, microsecond=0)
is_casa_open = is_weekday and (market_open_time <= now_ma <= market_close_time)

st.title("🤖 ماسح الذكاء الاصطناعي الشامل للتوصيات (تقييم +75%)")

st.info(
    f"🇲🇦 التوقيت الحالي في المغرب: **{now_ma.strftime('%Y-%m-%d %H:%M')}** | "
    f"بورصة الدار البيضاء: **{'🟢 مفتوحة (يتم التحليل على آخر إغلاق مكتمل)' if is_casa_open else '🔴 مغلقة (تحليل على الإغلاق الرسمي)'}**"
)

# 1. قائمة العملات الرقمية والذهب (فريم 4 ساعات)
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

# 2. قائمة أبرز أسهم بورصة الدار البيضاء (فريم يومي - بالدرهم المغربي)
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

@st.cache_data(ttl=600)
def fetch_crypto_gold(symbol, timeframe='4h', limit=720):
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange = getattr(ccxt, ex_id)({'enableRateLimit': True})
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 150:
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
            hist_url = f"https://yahoo.com{ticker}{suf}?interval=1d&range=2y"
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
                if len(df) > 100:
                    last_candle_date = df['timestamp'].iloc[-1].date()
                    if market_is_open and last_candle_date == now_ma.date():
                        df = df.iloc[:-1]
                    return df, "Bourse de Casablanca"
        except Exception:
            continue
    return None, None
def add_features(df):
    df = df.copy()
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_6'] = df['close'].pct_change(6)
    
    df['sma_10'] = df['close'].rolling(10).mean() / df['close']
    df['sma_30'] = df['close'].rolling(30).mean() / df['close']
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    df['volatility'] = df['atr'] / df['close']
    
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    return df

def run_ai_model(df, symbol, label, currency, is_stock=False):
    df = add_features(df)
    features = ['return_1', 'return_3', 'return_6', 'sma_10', 'sma_30', 'rsi', 'volatility']
    
    current_row = df.iloc[-1]
    current_candle = df.iloc[-1:][features]
    entry_price = float(current_row['close'])
    atr_value = float(current_row['atr'])
    last_time_ma = current_row['timestamp'].strftime('%Y-%m-%d %H:%M')
    
    if np.isnan(atr_value) or atr_value == 0:
        atr_value = entry_price * 0.015
        
    decimals = 2 if entry_price >= 10 else (4 if entry_price >= 0.1 else 5)
    
    train_df = df.iloc[:-1].dropna()
    if len(train_df) < 100:
        return None
        
    # تحديد عدد شموع آخر شهر (22 يوم تداول للأسهم، 180 شمعة 4 ساعات للكريبتو)
    month_candles = 22 if is_stock else 180
    if len(train_df) <= month_candles + 50:
        month_candles = int(len(train_df) * 0.2)
        
    X_train = train_df[features].iloc[:-month_candles]
    y_train = train_df['target'].iloc[:-month_candles]
    
    X_month = train_df[features].iloc[-month_candles:]
    y_month = train_df['target'].iloc[-month_candles:]
    
    model = LGBMClassifier(n_estimators=120, learning_rate=0.03, max_depth=4, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    
    # حساب الصفقات الناجحة والفاشلة لآخر شهر
    month_preds = model.predict(X_month)
    month_probs = model.predict_proba(X_month)
    
    wins = 0
    losses = 0
    for i in range(len(month_preds)):
        pred = month_preds[i]
        actual = y_month.iloc[i]
        prob_up_m = month_probs[i][1] * 100
        
        if is_stock:
            if prob_up_m >= 52:
                if actual == 1:
                    wins += 1
                else:
                    losses += 1
        else:
            if pred == actual:
                wins += 1
            else:
                losses += 1
                
    total_month_trades = wins + losses
    hist_acc = (wins / total_month_trades * 100) if total_month_trades > 0 else (accuracy_score(y_month, month_preds) * 100)
    
    # التنبؤ بالشمعة القادمة
    probs = model.predict_proba(current_candle)[0]
    prob_down = float(probs[0]) * 100
    prob_up = float(probs[1]) * 100
    
    if is_stock:
        direction = "شراء (BUY) 🟢" if prob_up >= 52 else "انتظار 🟡"
        confidence = prob_up
        stop_loss = round(entry_price - (1.2 * atr_value), decimals)
        take_profit = round(entry_price + (2.0 * atr_value), decimals)
    else:
        if prob_up >= prob_down:
            direction = "شراء (LONG) 🟢"
            confidence = prob_up
            stop_loss = round(entry_price - (1.0 * atr_value), decimals)
            take_profit = round(entry_price + (1.5 * atr_value), decimals)
        else:
            direction = "بيع (SHORT) 🔴"
            confidence = prob_down
            stop_loss = round(entry_price + (1.0 * atr_value), decimals)
            take_profit = round(entry_price - (1.5 * atr_value), decimals)
            
    overall_score = round((confidence * 0.7) + (hist_acc * 0.3), 1)
    
    return {
        "الأصل / الرمز": label if is_stock else symbol,
        "السوق": "بورصة الدار البيضاء (1D)" if is_stock else f"{label} (4H)",
        "التوصية": direction,
        "التقييم العام (%)": overall_score,
        "نسبة الثقة (%)": round(confidence, 1),
        "نجاح الشهر (%)": round(hist_acc, 1),
        "صفقات الشهر (ناجحة ✅ / فاشلة ❌)": f"✅ {wins}  |  ❌ {losses}",
        "سعر الدخول": f"{round(entry_price, decimals)} {currency}",
        "الهدف (TP)": f"{take_profit} {currency}",
        "وقف الخسارة (SL)": f"{stop_loss} {currency}",
        "آخر شمعة (المغرب)": last_time_ma
    }

# --- واجهة المستخدم ---
market_choice = st.radio(
    "اختر نطاق الفحص:",
    ["الكل (كريبتو + ذهب + بورصة الدار البيضاء)", "العملات الرقمية والذهب فقط (4H)", "بورصة الدار البيضاء فقط (1D)"],
    horizontal=True
)

st.caption("🔒 الفلتر مفعّل تلقائياً: يتم عرض الفرص ذات **التقييم العام فوق 75%** فقط.")

if st.button("🚀 بدء الفحص بالذكاء الاصطناعي", type="primary"):
    results = []
    tasks = []
    
    if "الكل" in market_choice or "العملات" in market_choice:
        for sym, lbl, curr in CRYPTO_GOLD_ASSETS:
            tasks.append((sym, lbl, curr, False))
            
    if "الكل" in market_choice or "الدار البيضاء" in market_choice:
        for sym, lbl, curr in CASABLANCA_STOCKS:
            tasks.append((sym, lbl, curr, True))
            
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, (sym, lbl, curr, is_stock) in enumerate(tasks):
        status_text.text(f"⏳ جاري تحليل {lbl if is_stock else sym}...")
        
        if is_stock:
            df, _ = fetch_casablanca_stock(sym, is_casa_open)
        else:
            df, _ = fetch_crypto_gold(sym)
            
        if df is not None:
            res = run_ai_model(df, sym, lbl, curr, is_stock=is_stock)
            if res and res["التقييم العام (%)"] > 75.0:
                results.append(res)
                
        progress_bar.progress((idx + 1) / len(tasks))
        
    status_text.empty()
    progress_bar.empty()
    
    if results:
        res_df = pd.DataFrame(results).sort_values(by="التقييم العام (%)", ascending=False)
        st.success(f"✅ تم العثور على {len(res_df)} فرصة قوية بتقييم أعلى من 75%:")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ لا توجد حالياً أي أصول يتجاوز تقييمها العام 75% وفق إغلاق الشمعة الأخيرة.")
