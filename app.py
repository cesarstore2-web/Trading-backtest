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
    </style>
    """, unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم
timeframe = st.selectbox(
    "الإطار الزمني:", 
    ["1m", "3m", "5m", "15m", "30m", "1h"], 
    index=3  # الافتراضي 15m
)
atr_mult = st.number_input("وقف الخسارة (ATR SL):", min_value=0.5, max_value=10.0, value=2.7, step=0.1)
rr_ratio = st.number_input("نسبة العائد (R:R):", min_value=0.5, max_value=10.0, value=3.2, step=0.1)

use_ema200 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=False)
use_breakeven = st.checkbox("تأمين الصفقة عند 1.5 R:R (Break-Even)", value=False)

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

# 3. اكتشاف النماذج الستة
def detect_patterns(df, cutoff_time):
    signals = []
    start_idx = min(200, len(df) - 2)
    if start_idx < 10:
        return signals

    for i in range(start_idx, len(df) - 1):
        c0 = df.iloc[i]
        
        if c0['timestamp'] < cutoff_time:
            continue

        c1 = df.iloc[i - 1]
        c2 = df.iloc[i - 2]
        
        body0 = abs(c0['close'] - c0['open'])
        body1 = abs(c1['close'] - c1['open'])
        body2 = abs(c2['close'] - c2['open'])
        
        if body0 == 0 or body1 == 0 or body2 == 0:
            continue

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
        if pattern_name:
            if use_ema200:
                if direction == "شراء (Long)" and c0['close'] < c0['ema200']:
                    continue
                if direction == "بيع (Short)" and c0['close'] > c0['ema200']:
                    continue
            
            signals.append({
                "index": i,
                "timestamp": c0['timestamp'],
                "pattern": pattern_name,
                "direction": direction,
                "entry": c0['close'],
                "atr": c0['atr']
            })
    return signals

# 4. محاكي الصفقات (آخر 24 ساعة برأس مال 100$ للصفقة)
def run_backtest(symbols, tf, atr_m, rr, be_active):
    # استخدام KuCoin لأنه يدعم جلب 1500 شمعة في طلب واحد بدون تقطيع وبدون حظر أمريكي
    exchange = ccxt.kucoin({'enableRateLimit': True})
    all_trades = []
    errors = []
    
    candles_per_day = {"1m": 1440, "3m": 480, "5m": 288, "15m": 96, "30m": 48, "1h": 24}
    needed_candles = min(1500, candles_per_day.get(tf, 96) + 210)
    
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
            
            signals = detect_patterns(df, cutoff_time)
            
            for sig in signals:
                idx = sig['index']
                entry = sig['entry']
                if pd.isna(sig['atr']) or sig['atr'] == 0:
                    continue
                    
                sl_dist = sig['atr'] * atr_m
                tp_dist = sl_dist * rr
                be_dist = sl_dist * 1.5
                
                is_long = "شراء" in sig['direction']
                sl = entry - sl_dist if is_long else entry + sl_dist
                tp = entry + tp_dist if is_long else entry - tp_dist
                be_trigger = entry + be_dist if is_long else entry - be_dist
                
                sl_pct = sl_dist / entry
                tp_pct = tp_dist / entry
                
                be_triggered = False
                outcome = "مفتوحة ⏳"
                pnl = 0.0
                
                for j in range(idx + 1, len(df)):
                    future_c = df.iloc[j]
                    
                    if is_long:
                        if be_active and not be_triggered and future_c['high'] >= be_trigger:
                            be_triggered = True
                            sl = entry
                        if future_c['low'] <= sl:
                            outcome = "تعادل" if be_triggered else "خاسرة"
                            pnl = 0.0 if be_triggered else -(POSITION_SIZE_USD * sl_pct)
                            break
                        elif future_c['high'] >= tp:
                            outcome = "ناجحة"
                            pnl = POSITION_SIZE_USD * tp_pct
                            break
                    else:
                        if be_active and not be_triggered and future_c['low'] <= be_trigger:
                            be_triggered = True
                            sl = entry
                        if future_c['high'] >= sl:
                            outcome = "تعادل" if be_triggered else "خاسرة"
                            pnl = 0.0 if be_triggered else -(POSITION_SIZE_USD * sl_pct)
                            break
                        elif future_c['low'] <= tp:
                            outcome = "ناجحة"
                            pnl = POSITION_SIZE_USD * tp_pct
                            break
                            
                all_trades.append({
                    "الوقت": sig['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    "العملة": sym.replace('/USDT', ''),
                    "النوع": sig['direction'],
                    "النموذج": sig['pattern'],
                    "الحالة": outcome,
                    "الربح ($)": round(pnl, 2)
                })
        except Exception as e:
            errors.append(f"{sym}: {str(e)}")
            
    return pd.DataFrame(all_trades), errors

# 5. عرض النتائج
with st.spinner('جاري تحليل السوق لآخر 24 ساعة...'):
    trades_df, fetch_errors = run_backtest(HALAL_SYMBOLS, timeframe, atr_mult, rr_ratio, use_breakeven)

if fetch_errors and trades_df.empty:
    st.error(f"حدث خطأ في الاتصال بالمنصة: {fetch_errors[0]}")

if not trades_df.empty:
    trades_df = trades_df.sort_values(by="الوقت", ascending=False).reset_index(drop=True)
    
    # حساب الإحصائيات للصفقات المغلقة فقط
    closed_df = trades_df[trades_df['الحالة'] != 'مفتوحة ⏳']
    
    total_closed = len(closed_df)
    wins = len(closed_df[closed_df['الحالة'] == 'ناجحة'])
    losses = len(closed_df[closed_df['الحالة'] == 'خاسرة'])
    draws = len(closed_df[closed_df['الحالة'] == 'تعادل'])
    open_trades = len(trades_df[trades_df['الحالة'] == 'مفتوحة ⏳'])
    
    win_rate = (wins / total_closed) * 100 if total_closed > 0 else 0.0
    net_profit = closed_df['الربح ($)'].sum()

    st.markdown("---")
    st.caption(f"الربح الصافي ({timeframe} - آخر 24 ساعة | صفقة 100$)")
    st.metric(label="", value=f"{net_profit:.2f} $")

    st.caption("نسبة النجاح (للصفقات المغلقة)")
    st.metric(label="", value=f"{win_rate:.1f}%", delta=f"مغلقة: {total_closed} | مفتوحة: {open_trades}")

    st.caption("توزيع الصفقات")
    st.markdown(f"### {wins} ناجحة | {draws} تعادل")
