import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# إعدادات الصفحة
st.set_page_config(page_title="ماسح النماذج الفنية", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: bold; }
    .signal-card-buy {
        background-color: rgba(0, 200, 83, 0.15);
        border-right: 6px solid #00c853;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .signal-card-sell {
        background-color: rgba(255, 75, 75, 0.15);
        border-right: 6px solid #ff4b4b;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .signal-title-buy { color: #00e676; font-size: 1.3rem; font-weight: bold; margin-bottom: 5px; }
    .signal-title-sell { color: #ff5252; font-size: 1.3rem; font-weight: bold; margin-bottom: 5px; }
    .signal-details { font-size: 1.05rem; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم مع الضبط التلقائي للفريمات (5m و 15m)
timeframe = st.selectbox(
    "الإطار الزمني:", 
    ["1m", "3m", "5m", "15m", "30m", "1h"], 
    index=2  # الافتراضي 5m
)

# تحديد القيم الافتراضية الذكية حسب الفريم المختار
if timeframe == "5m":
    def_atr = 2.50
    def_rr = 2.70
    def_ema = False
elif timeframe == "15m":
    def_atr = 1.90
    def_rr = 3.20
    def_ema = True
else:
    def_atr = 2.50
    def_rr = 2.70
    def_ema = False

# استخدام key ديناميكي مرتبط بالفريم لتحديث القيم تلقائياً عند تغيير الفريم
atr_mult = st.number_input("وقف الخسارة (ATR SL):", min_value=0.5, max_value=10.0, value=def_atr, step=0.1, key=f"atr_{timeframe}")
rr_ratio = st.number_input("نسبة العائد (R:R):", min_value=0.5, max_value=10.0, value=def_rr, step=0.1, key=f"rr_{timeframe}")
use_ema200 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=def_ema, key=f"ema_{timeframe}")

# رأس مال كل صفقة 100 دولار (تداول فوري بدون رافعة)
POSITION_SIZE_USD = 100.0

# قائمة العملات ذات المشاريع التقنية الحقيقية
HALAL_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "ADA/USDT",
    "DOT/USDT", "LINK/USDT", "ATOM/USDT", "NEAR/USDT", "ALGO/USDT"
]

# 2. حساب المؤشرات
def calculate_indicators(df):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    df['downtrend'] = df['close'].shift(1) < df['close'].shift(3)
    df['uptrend'] = df['close'].shift(1) > df['close'].shift(3)
    return df

# دالة فحص شمعة واحدة لتحديد النموذج
def check_candle_pattern(df, i, apply_ema):
    c0 = df.iloc[i]
    c1 = df.iloc[i - 1]
    c2 = df.iloc[i - 2]
    
    body0 = abs(c0['close'] - c0['open'])
    body1 = abs(c1['close'] - c1['open'])
    body2 = abs(c2['close'] - c2['open'])
    
    if body0 == 0 or body1 == 0 or body2 == 0:
        return None, None

    upper_wick0 = c0['high'] - max(c0['open'], c0['close'])
    lower_wick0 = min(c0['open'], c0['close']) - c0['low']
    
    is_bull0 = c0['close'] > c0['open']
    is_bear0 = c0['close'] < c0['open']
    is_bull1 = c1['close'] > c1['open']
    is_bear1 = c1['close'] < c1['open']
    is_bull2 = c2['close'] > c2['open']
    is_bear2 = c2['close'] < c2['open']

    pattern_name = None
    direction = None

    # --- النماذج الصاعدة (شراء) ---
    if c0['downtrend']:
        if upper_wick0 >= (1.5 * body0) and lower_wick0 <= (0.5 * body0):
            pattern_name = "المطرقة المقلوبة"
            direction = "شراء (Long)"
        elif is_bear1 and is_bull0 and c0['open'] <= (c1['close'] * 1.002) and c0['close'] > (c1['open'] + c1['close']) / 2:
            pattern_name = "خط الاختراق"
            direction = "شراء (Long)"
        elif is_bull2 and is_bull1 and is_bull0 and (c0['close'] > c1['close'] > c2['close']):
            pattern_name = "الجنود الثلاثة البيض"
            direction = "شراء (Long)"

    # --- النماذج الهابطة (بيع) ---
    if c0['uptrend'] and pattern_name is None:
        if lower_wick0 >= (1.5 * body0) and upper_wick0 <= (0.5 * body0):
            pattern_name = "الرجل المشنوق"
            direction = "بيع (Short)"
        elif is_bull1 and is_bear0 and c0['open'] >= (c1['close'] * 0.998) and c0['close'] < (c1['open'] + c1['close']) / 2:
            pattern_name = "الغطاء السحابي الداكن"
            direction = "بيع (Short)"
        elif is_bear2 and is_bear1 and is_bear0 and (c0['close'] < c1['close'] < c2['close']):
            pattern_name = "الغربان السوداء الثلاثة"
            direction = "بيع (Short)"

    # تطبيق فلتر EMA 200
    if pattern_name and apply_ema:
        if direction == "شراء (Long)" and c0['close'] < c0['ema200']:
            return None, None
        if direction == "بيع (Short)" and c0['close'] > c0['ema200']:
            return None, None

    return pattern_name, direction

# 3. تحليل البيانات التاريخية + البحث عن التوصيات المستقبلية اللحظية
def analyze_market(symbols, tf, atr_m, rr, apply_ema):
    exchange = ccxt.kucoin({'enableRateLimit': True})
    all_trades = []
    live_recommendations = []
    errors = []
    
    candles_per_day = {"1m": 1440, "3m": 480, "5m": 288, "15m": 96, "30m": 48, "1h": 24}
    needed_candles = min(1500, candles_per_day.get(tf, 288) + 210)
    
    cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    
    for sym in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe=tf, limit=needed_candles)
            if not ohlcv or len(ohlcv) < 50:
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.drop_duplicates(subset=['timestamp'], inplace=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calculate_indicators(df)
            
            # أ) فحص التوصيات المستقبلية (آخر شمعتين مغلقتين: -2 و -3)
            for check_idx in [len(df) - 2, len(df) - 3]:
                p_name, p_dir = check_candle_pattern(df, check_idx, apply_ema)
                if p_name and not pd.isna(df.iloc[check_idx]['atr']):
                    c_sig = df.iloc[check_idx]
                    entry_p = c_sig['close']
                    sl_d = c_sig['atr'] * atr_m
                    tp_d = sl_d * rr
                    is_l = "شراء" in p_dir
                    
                    live_recommendations.append({
                        "العملة": sym.replace('/USDT', ''),
                        "النوع": p_dir,
                        "النموذج": p_name,
                        "الوقت": c_sig['timestamp'].strftime('%H:%M'),
                        "الدخول": entry_p,
                        "الوقف": entry_p - sl_d if is_l else entry_p + sl_d,
                        "الهدف": entry_p + tp_d if is_l else entry_p - tp_d
                    })
                    break # نكتفي بأحدث إشارة للعملة

            # ب) محاكاة الصفقات التاريخية لآخر 24 ساعة
            start_idx = min(200, len(df) - 2)
            for i in range(start_idx, len(df) - 1):
                c0 = df.iloc[i]
                if c0['timestamp'] < cutoff_time or pd.isna(c0['atr']) or c0['atr'] == 0:
                    continue
                    
                pattern_name, direction = check_candle_pattern(df, i, apply_ema)
                if not pattern_name:
                    continue
                    
                entry = c0['close']
                sl_dist = c0['atr'] * atr_m
                tp_dist = sl_dist * rr
                
                is_long = "شراء" in direction
                sl = entry - sl_dist if is_long else entry + sl_dist
                tp = entry + tp_dist if is_long else entry - tp_dist
                
                sl_pct = sl_dist / entry
                tp_pct = tp_dist / entry
                
                outcome = "مفتوحة ⏳"
                pnl = 0.0
                
                for j in range(i + 1, len(df)):
                    future_c = df.iloc[j]
                    if is_long:
                        if future_c['low'] <= sl:
                            outcome = "خاسرة"
                            pnl = -(POSITION_SIZE_USD * sl_pct)
                            break
                        elif future_c['high'] >= tp:
                            outcome = "ناجحة"
                            pnl = POSITION_SIZE_USD * tp_pct
                            break
                    else:
                        if future_c['high'] >= sl:
                            outcome = "خاسرة"
                            pnl = -(POSITION_SIZE_USD * sl_pct)
                            break
                        elif future_c['low'] <= tp:
                            outcome = "ناجحة"
                            pnl = POSITION_SIZE_USD * tp_pct
                            break
                            
                all_trades.append({
                    "الوقت": c0['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    "العملة": sym.replace('/USDT', ''),
                    "النوع": direction,
                    "النموذج": pattern_name,
                    "الحالة": outcome,
                    "الربح ($)": round(pnl, 2)
                })
        except Exception as e:
            errors.append(f"{sym}: {str(e)}")
            
    return pd.DataFrame(all_trades), live_recommendations, errors

# 4. عرض النتائج
with st.spinner('جاري تحليل السوق واستخراج التوصيات...'):
    trades_df, live_recs, fetch_errors = analyze_market(HALAL_SYMBOLS, timeframe, atr_mult, rr_ratio, use_ema200)

# --- القسم الأول: التوصيات المستقبلية بخط وألوان واضحة ---
st.markdown("---")
