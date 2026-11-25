import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime

# إعدادات الصفحة لتطابق الوضع الليلي واللغة العربية
st.set_page_config(page_title="ماسح النماذج الفنية", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم (مطابقة للصورة الثالثة)
timeframe = st.selectbox("الإطار الزمني:", ["15m", "1h", "4h", "1d"], index=0)
atr_mult = st.number_input("وقف الخسارة (ATR SL):", min_value=0.5, max_value=10.0, value=2.7, step=0.1)
rr_ratio = st.number_input("نسبة العائد (R:R):", min_value=0.5, max_value=10.0, value=3.2, step=0.1)

use_ema200 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=False)
use_breakeven = st.checkbox("تأمين الصفقة عند 1.5 R:R (Break-Even)", value=False)

# قائمة العملات الافتراضية للفحص
SYMBOLS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "AVAX/USDT", "SOL/USDT", "BNB/USDT"]

# 2. دوال المؤشرات الفنية واكتشاف النماذج الستة (مطابقة للصورة الأولى)
def calculate_indicators(df):
    # حساب ATR (14)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # حساب EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # تحديد الاتجاه السابق (آخر 5 شموع) للتأكد من انعكاسية النموذج
    df['downtrend'] = df['close'].shift(1) < df['close'].shift(5)
    df['uptrend'] = df['close'].shift(1) > df['close'].shift(5)
    return df

def detect_patterns(df):
    signals = []
    for i in range(200, len(df) - 1):
        c0 = df.iloc[i]     # الشمعة الحالية (نقطة الدخول عند إغلاقها)
        c1 = df.iloc[i - 1] # الشمعة السابقة
        c2 = df.iloc[i - 2] # ما قبل السابقة
        
        body0 = abs(c0['close'] - c0['open'])
        body1 = abs(c1['close'] - c1['open'])
        body2 = abs(c2['close'] - c2['open'])
        
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
            # 1. المطرقة المقلوبة (Inverted Hammer)
            if upper_wick0 >= (2 * body0) and lower_wick0 <= (0.2 * body0) and body0 > 0:
                pattern_name = "المطرقة المقلوبة"
                direction = "شراء (Long)"
            
            # 2. خط الاختراق (Piercing Line)
            elif is_bear1 and is_bull0 and c0['open'] < c1['low'] and c0['close'] > (c1['open'] + c1['close']) / 2 and c0['close'] < c1['open']:
                pattern_name = "خط الاختراق"
                direction = "شراء (Long)"
                
            # 3. الجنود الثلاثة البيض (Three White Soldiers)
            elif is_bull2 and is_bull1 and is_bull0 and (c0['close'] > c1['close'] > c2['close']) and (c0['open'] > c1['open'] > c2['open']):
                pattern_name = "الجنود الثلاثة البيض"
                direction = "شراء (Long)"

        # --- النماذج الهابطة (بيع) ---
        if c0['uptrend'] and pattern_name is None:
            # 4. الرجل المشنوق (Hanging Man)
            if lower_wick0 >= (2 * body0) and upper_wick0 <= (0.2 * body0) and body0 > 0:
                pattern_name = "الرجل المشنوق"
                direction = "بيع (Short)"
                
            # 5. الغطاء السحابي الداكن (Dark Cloud Cover)
            elif is_bull1 and is_bear0 and c0['open'] > c1['high'] and c0['close'] < (c1['open'] + c1['close']) / 2 and c0['close'] > c1['open']:
                pattern_name = "الغطاء السحابي الداكن"
                direction = "بيع (Short)"
                
            # 6. الغربان السوداء الثلاثة (Three Black Crows)
            elif is_bear2 and is_bear1 and is_bear0 and (c0['close'] < c1['close'] < c2['close']) and (c0['open'] < c1['open'] < c2['open']):
                pattern_name = "الغربان السوداء الثلاثة"
                direction = "بيع (Short)"

        # تطبيق فلتر EMA 200 إذا كان مفعلاً
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

# 3. محاكي الصفقات (Backtest) لحساب النتائج وإحصائيات لوحة القيادة
def run_backtest(exchange, symbols, tf, atr_m, rr, be_active):
    all_trades = []
    # جلب بيانات كافية لتغطية 200 شمعة للـ EMA + آخر 5 أيام
    limit = 680 if tf == "15m" else 300 
    
    for sym in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calculate_indicators(df)
            
            signals = detect_patterns(df)
            
            for sig in signals:
                idx = sig['index']
                entry = sig['entry']
                sl_dist = sig['atr'] * atr_m
                tp_dist = sl_dist * rr
                be_dist = sl_dist * 1.5
                
                is_long = "شراء" in sig['direction']
                sl = entry - sl_dist if is_long else entry + sl_dist
                tp = entry + tp_dist if is_long else entry - tp_dist
                be_trigger = entry + be_dist if is_long else entry - be_dist
                
                be_triggered = False
                outcome = None
                pnl = 0.0
                risk_usd = 10.0 # مخاطرة افتراضية 10 دولار لكل صفقة لحساب الربح الصافي
                
                # تتبع الشموع اللاحقة لمعرفة نتيجة الصفقة
                for j in range(idx + 1, len(df)):
                    future_c = df.iloc[j]
                    
                    if is_long:
                        if be_active and not be_triggered and future_c['high'] >= be_trigger:
                            be_triggered = True
                            sl = entry # نقل وقف الخسارة لنقطة الدخول
                        if future_c['low'] <= sl:
                            outcome = "تعادل" if be_triggered else "خاسرة"
                            pnl = 0.0 if be_triggered else -risk_usd
                            break
                        elif future_c['high'] >= tp:
                            outcome = "ناجحة"
                            pnl = risk_usd * rr
                            break
                    else:
                        if be_active and not be_triggered and future_c['low'] <= be_trigger:
                            be_triggered = True
                            sl = entry
                        if future_c['high'] >= sl:
                            outcome = "تعادل" if be_triggered else "خاسرة"
                            pnl = 0.0 if be_triggered else -risk_usd
                            break
                        elif future_c['low'] <= tp:
                            outcome = "ناجحة"
                            pnl = risk_usd * rr
                            break
                            
                if outcome:
                    all_trades.append({
                        "الوقت": sig['timestamp'].strftime('%Y-%m-%d %H:%M'),
                        "العملة": sym.replace('/USDT', ''),
                        "النوع": sig['direction'],
                        "النموذج": sig['pattern'],
                        "الحالة": outcome,
                        "الربح ($)": round(pnl, 2)
                    })
        except Exception as e:
            continue
            
    return pd.DataFrame(all_trades)

# 4. عرض الإحصائيات والجدول (مطابق للصورة الثانية والثالثة)
exchange = ccxt.binance({'enableRateLimit': True})

with st.spinner('جاري تحليل السوق وحساب الصفقات...'):
    trades_df = run_backtest(exchange, SYMBOLS, timeframe, atr_mult, rr_ratio, use_breakeven)

if not trades_df.empty:
    trades_df = trades_df.sort_values(by="الوقت", ascending=False).reset_index(drop=True)
    
    total_trades = len(trades_df)
    wins = len(trades_df[trades_df['الحالة'] == 'ناجحة'])
    losses = len(trades_df[trades_df['الحالة'] == 'خاسرة'])
    draws = len(trades_df[trades_df['الحالة'] == 'تعادل'])
    
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    net_profit = trades_df['الربح ($)'].sum()

    st.markdown("---")
    st.caption(f"الربح الصافي ({timeframe} - آخر 5 أيام)")
    st.metric(label="", value=f"{net_profit:.2f} $")

    st.caption("نسبة النجاح (Candlestick Patterns)")
    st.metric(label="", value=f"{win_rate:.1f}%", delta=f"إجمالي الصفقات: {total_trades}")

    st.caption("توزيع الصفقات")
    st.markdown(f"### {wins} ناجحة | {draws} تعادل")
    st.markdown(f"<span style='color:#ff4b4b; background-color:rgba(255,75,75,0.1); padding:4px 8px; border-radius:4px;'>↓ -{losses} خاسرة</span>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 فحص الفرص اللحظية الآن", use_container_width=True):
        st.rerun()

    st.markdown("---")
    st.subheader(f"📋 سجل الصفقات المحسوبة (SL: {atr_mult} ATR | R:R: 1:{rr_ratio})")
