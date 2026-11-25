import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="ماسح استراتيجيات الهارمونيك والبرايس أكشن", layout="centered")

st.markdown("<style>.stApp { direction: rtl; text-align: right; } div[data-testid='stMetricValue'] { font-size: 2rem; font-weight: bold; }</style>", unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم
timeframe = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h"], index=1)

# إعدادات حساسية استخراج القمم والقيعان (Swing) وإدارة المخاطر
swing_len = st.slider("حساسية القمم والقيعان (Swing Length):", min_value=3, max_value=10, value=5)
use_ema200 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=False)

POSITION_SIZE_USD = 100.0

HALAL_SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD",
    "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"
]

# 2. جلب البيانات بسرعة فائقة بالتوازي مع كاش 60 ثانية
@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_ohlcv(symbols, tf):
    exchange = ccxt.kraken({'enableRateLimit': False})
    def fetch_one(sym):
        try:
            data = exchange.fetch_ohlcv(sym, timeframe=tf, limit=500)
            if data and len(data) > 60:
                df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
                return sym, df
        except Exception:
            pass
        return sym, None

    results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        for sym, df in executor.map(fetch_one, symbols):
            if df is not None:
                results[sym] = df
    return results

# 3. استخراج القمم والقيعان المحورية (Pivots)
def get_pivots(df, left_right=5):
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    pivot_highs = []
    pivot_lows = []
    
    for i in range(left_right, n - left_right):
        if highs[i] == np.max(highs[i - left_right : i + left_right + 1]):
            pivot_highs.append((i, highs[i]))
        if lows[i] == np.min(lows[i - left_right : i + left_right + 1]):
            pivot_lows.append((i, lows[i]))
            
    return pivot_highs, pivot_lows

# 4. فحص الاستراتيجيات الثلاث المستخرجة من الصور
def detect_image_strategies(df, s_len, apply_ema):
    signals = []
    ph, pl = get_pivots(df, s_len)
    if len(ph) < 3 or len(pl) < 3:
        return signals

    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    ema = df['ema200'].values
    times = df['timestamp'].values

    # أ) استراتيجية الصورة 1 و 3: نموذج التنين (Dragon) والقاع المزدوج مع كسر الترند (شراء)
    for k in range(1, len(pl)):
        idx_leg1, price_leg1 = pl[k - 1]
        idx_leg2, price_leg2 = pl[k]
        
        if idx_leg2 - idx_leg1 < 4 or idx_leg2 - idx_leg1 > 60:
            continue
            
        # القاع الثاني قريب من القاع الأول (نسبة تفاوت 1.5%)
        if abs(price_leg2 - price_leg1) / price_leg1 > 0.015:
            continue
            
        # البحث عن سنام التنين / خط العنق بين القاعين
        mid_highs = [p for p in ph if idx_leg1 < p[0] < idx_leg2]
        # البحث عن رأس التنين / بداية الهبوط قبل القاع الأول
        head_highs = [p for p in ph if p[0] < idx_leg1 and idx_leg1 - p[0] < 60]
        
        if not mid_highs or not head_highs:
            continue
            
        idx_hump, price_hump = max(mid_highs, key=lambda x: x[1])
        idx_head, price_head = max(head_highs, key=lambda x: x[1])
        
        if price_head <= price_hump or price_hump <= max(price_leg1, price_leg2):
            continue

        # معادلة خط الترند الهابط بين الرأس والسنام
        slope = (price_hump - price_head) / (idx_hump - idx_head)
        
        # مراقبة كسر خط الترند بعد القاع الثاني
        for i in range(idx_leg2 + 1, min(idx_leg2 + 25, len(df) - 1)):
            trend_val = price_head + slope * (i - idx_head)
            
            # شرط الكسر الصاعد للترند أو خط العنق
            if closes[i] > trend_val and closes[i - 1] <= (price_head + slope * (i - 1 - idx_head)):
                if apply_ema and closes[i] < ema[i]:
                    break
                    
                # التمييز بين التنين (كسر الترند مباشرة) والقاع المزدوج (كسر خط العنق)
                is_double_bottom = closes[i] >= price_hump
                pat_name = "قاع مزدوج + كسر ترند (صورة 3)" if is_double_bottom else "نموذج التنين Dragon (صورة 1)"
                
                entry_p = closes[i]
                sl_p = min(price_leg1, price_leg2) * 0.998
                tp_p = price_head
                
                if tp_p > entry_p and entry_p > sl_p:
                    signals.append({
                        "index": i,
                        "timestamp": pd.Timestamp(times[i]),
                        "direction": "شراء (Long)",
                        "pattern": pat_name,
                        "entry": entry_p,
                        "sl": sl_p,
                        "tp": tp_p
                    })
                break

    # ب) استراتيجية الصورة 2: كسر الترند الصاعد + فجوة FVG + إعادة الاختبار (بيع)
    for k in range(1, len(ph)):
        idx_h1, price_h1 = ph[k - 1]
        idx_h2, price_h2 = ph[k]
        
        if price_h2 <= price_h1 or idx_h2 - idx_h1 < 5 or idx_h2 - idx_h1 > 50:
            continue
            
        # القاع الذي يرتكز عليه خط الترند الصاعد
        lows_before = [p for p in pl if p[0] < idx_h1 and idx_h1 - p[0] < 40]
        mid_lows = [p for p in pl if idx_h1 < p[0] < idx_h2]
        
        if not lows_before or not mid_lows:
            continue
            
        idx_l1, price_l1 = min(lows_before, key=lambda x: x[1])
        idx_l2, price_l2 = min(mid_lows, key=lambda x: x[1])
        
        if price_l2 <= price_l1:
            continue
            
        # معادلة خط الترند الصاعد
        up_slope = (price_l2 - price_l1) / (idx_l2 - idx_l1)
        
        # البحث عن كسر الترند الصاعد مع وجود FVG هابط بعد القمة الثانية
        fvg_top = None
        fvg_bottom = None
        
        for i in range(idx_h2 + 2, min(idx_h2 + 25, len(df) - 1)):
            trend_up_val = price_l1 + up_slope * (i - idx_l1)
            
            # اكتشاف FVG هابط (قاع شمعة i-2 أعلى من قمة شمعة i)
            if fvg_top is None and lows[i - 2] > highs[i] and closes[i] < trend_up_val:
                fvg_top = lows[i - 2]
                fvg_bottom = highs[i]
                continue
                
            # بعد تشكل FVG، ننتظر عودة السعر لإعادة اختبار الفجوة (الدخول بيع)
            if fvg_top is not None:
                if highs[i] >= fvg_bottom and closes[i] <= fvg_top:
                    if apply_ema and closes[i] > ema[i]:
                        break
                    entry_p = closes[i]
                    sl_p = fvg_top * 1.002
                    tp_p = price_l1
                    
                    if entry_p > tp_p and sl_p > entry_p:
                        signals.append({
                            "index": i,
                            "timestamp": pd.Timestamp(times[i]),
                            "direction": "بيع (Short)",
                            "pattern": "كسر ترند + FVG (صورة 2)",
                            "entry": entry_p,
                            "sl": sl_p,
                            "tp": tp_p
                        })
                    break
                elif highs[i] > fvg_top * 1.005:
                    break

    return signals

# 5. تشغيل الفحص والمحاكاة لآخر 24 ساعة برأس مال 100$
market_data = fetch_all_ohlcv(HALAL_SYMBOLS, timeframe)

all_trades = []
live_recs = []
cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

for sym, df in market_data.items():
    coin_name = sym.replace('/USD', '')
    sigs = detect_image_strategies(df, swing_len, use_ema200)
    
    for s in sigs:
        idx = s['index']
        # إذا كانت الإشارة في آخر 4 شموع، تعتبر توصية مستقبلية لحظية
        if idx >= len(df) - 5:
            live_recs.append({
                "العملة": coin_name,
                "النوع": s['direction'],
                "النموذج": s['pattern'],
                "الوقت": s['timestamp'].strftime('%H:%M'),
                "الدخول": s['entry'],
                "الوقف": s['sl'],
                "الهدف": s['tp']
            })
            
        # محاكاة الصفقات لآخر 24 ساعة
        if s['timestamp'] >= cutoff_time:
            entry = s['entry']
            sl = s['sl']
            tp = s['tp']
            is_long = "شراء" in s['direction']
            
            sl_pct = abs(entry - sl) / entry
            tp_pct = abs(tp - entry) / entry
            
            outcome = "مفتوحة ⏳"
            pnl = 0.0
            
            for j in range(idx + 1, len(df)):
                fc = df.iloc[j]
                if is_long:
                    if fc['low'] <= sl:
                        outcome = "خاسرة"
                        pnl = -(POSITION_SIZE_USD * sl_pct)
                        break
                    elif fc['high'] >= tp:
                        outcome = "ناجحة"
                        pnl = POSITION_SIZE_USD * tp_pct
                        break
                else:
                    if fc['high'] >= sl:
                        outcome = "خاسرة"
                        pnl = -(POSITION_SIZE_USD * sl_pct)
                        break
                    elif fc['low'] <= tp:
                        outcome = "ناجحة"
                        pnl = POSITION_SIZE_USD * tp_pct
                        break
                        
            all_trades.append({
                "الوقت": s['timestamp'].strftime('%Y-%m-%d %H:%M'),
                "العملة": coin_name,
