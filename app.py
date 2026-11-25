import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="ماسح النماذج الفنية", layout="centered")

st.markdown("<style>.stApp { direction: rtl; text-align: right; } div[data-testid='stMetricValue'] { font-size: 2rem; font-weight: bold; }</style>", unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم
timeframe = st.selectbox("الإطار الزمني:", ["1m", "5m", "15m", "30m", "1h"], index=1)

if timeframe == "5m":
    def_atr, def_rr, def_ema = 2.50, 2.70, False
elif timeframe == "15m":
    def_atr, def_rr, def_ema = 1.90, 3.20, True
else:
    def_atr, def_rr, def_ema = 2.50, 2.70, False

atr_mult = st.number_input("وقف الخسارة (ATR SL):", min_value=0.5, max_value=10.0, value=def_atr, step=0.1, key=f"atr_{timeframe}")
rr_ratio = st.number_input("نسبة العائد (R:R):", min_value=0.5, max_value=10.0, value=def_rr, step=0.1, key=f"rr_{timeframe}")
use_ema200 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=def_ema, key=f"ema_{timeframe}")

POSITION_SIZE_USD = 100.0

HALAL_SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD",
    "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"
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

# 3. فحص النماذج
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

    if c0['downtrend']:
        if upper_wick0 >= (1.5 * body0) and lower_wick0 <= (0.5 * body0):
            pattern_name, direction = "المطرقة المقلوبة", "شراء (Long)"
        elif is_bear1 and is_bull0 and c0['open'] <= (c1['close'] * 1.002) and c0['close'] > (c1['open'] + c1['close']) / 2:
            pattern_name, direction = "خط الاختراق", "شراء (Long)"
        elif is_bull2 and is_bull1 and is_bull0 and (c0['close'] > c1['close'] > c2['close']):
            pattern_name, direction = "الجنود الثلاثة البيض", "شراء (Long)"

    if c0['uptrend'] and pattern_name is None:
        if lower_wick0 >= (1.5 * body0) and upper_wick0 <= (0.5 * body0):
            pattern_name, direction = "الرجل المشنوق", "بيع (Short)"
        elif is_bull1 and is_bear0 and c0['open'] >= (c1['close'] * 0.998) and c0['close'] < (c1['open'] + c1['close']) / 2:
            pattern_name, direction = "الغطاء السحابي الداكن", "بيع (Short)"
        elif is_bear2 and is_bear1 and is_bear0 and (c0['close'] < c1['close'] < c2['close']):
            pattern_name, direction = "الغربان السوداء الثلاثة", "بيع (Short)"

    if pattern_name and apply_ema:
        if direction == "شراء (Long)" and c0['close'] < c0['ema200']:
            return None, None
        if direction == "بيع (Short)" and c0['close'] > c0['ema200']:
            return None, None

    return pattern_name, direction

# 4. جلب البيانات وتحليل السوق
def analyze_market(symbols, tf, atr_m, rr, apply_ema):
    exchange = ccxt.kraken({'enableRateLimit': True})
    all_trades = []
    live_recommendations = []
    errors = []
    
    cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    
    for sym in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe=tf, limit=720)
            if not ohlcv or len(ohlcv) < 50:
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.drop_duplicates(subset=['timestamp'], inplace=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calculate_indicators(df)
            
            # أ) التوصيات المستقبلية (آخر شمعتين مغلقتين)
            for check_idx in [len(df) - 2, len(df) - 3]:
                p_name, p_dir = check_candle_pattern(df, check_idx, apply_ema)
                if p_name and not pd.isna(df.iloc[check_idx]['atr']):
                    c_sig = df.iloc[check_idx]
                    entry_p = c_sig['close']
                    sl_d = c_sig['atr'] * atr_m
                    tp_d = sl_d * rr
                    is_l = "شراء" in p_dir
                    
                    live_recommendations.append({
                        "العملة": sym.replace('/USD', ''),
                        "النوع": p_dir,
                        "النموذج": p_name,
                        "الوقت": c_sig['timestamp'].strftime('%H:%M'),
                        "الدخول": entry_p,
                        "الوقف": entry_p - sl_d if is_l else entry_p + sl_d,
                        "الهدف": entry_p + tp_d if is_l else entry_p - tp_d
                    })
                    break

            # ب) الصفقات التاريخية لآخر 24 ساعة
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
                    "العملة": sym.replace('/USD', ''),
                    "النوع": direction,
                    "النموذج": pattern_name,
                    "الحالة": outcome,
                    "الربح ($)": round(pnl, 2)
                })
        except Exception as e:
            errors.append(f"{sym}: {str(e)}")
            
    return pd.DataFrame(all_trades), live_recommendations, errors

# 5. عرض الواجهة والنتائج
st.markdown("---")
with st.spinner('جاري جلب البيانات وتحليل السوق...'):
    trades_df, live_recs, fetch_errors = analyze_market(HALAL_SYMBOLS, timeframe, atr_mult, rr_ratio, use_ema200)

if fetch_errors and trades_df.empty:
    st.error("تنبيه من السيرفر:")
    st.code("\n".join(fetch_errors[:3]))

# التوصيات المستقبلية
st.subheader("🎯 توصيات مستقبلية (الفرص اللحظية الآن)")
if live_recs:
    for rec in live_recs:
        is_buy = "شراء" in rec["النوع"]
        bg = "rgba(0, 200, 83, 0.15)" if is_buy else "rgba(255, 75, 75, 0.15)"
        border = "#00c853" if is_buy else "#ff4b4b"
        t_color = "#00e676" if is_buy else "#ff5252"
        icon = "🟢" if is_buy else "🔴"
        dec = 4 if rec["الدخول"] < 10 else 2
        
        html_card = f"<div style='background-color:{bg}; border-right:6px solid {border}; padding:15px; border-radius:8px; margin-bottom:12px;'>"
        html_card += f"<div style='color:{t_color}; font-size:1.25rem; font-weight:bold; margin-bottom:6px;'>{icon} {rec['العملة']} | {rec['النوع']} — {rec['النموذج']} ({rec['الوقت']} UTC)</div>"
        html_card += f"<div style='font-size:1.05rem;'><b>🔹 الدخول:</b> <code>{rec['الدخول']:.{dec}f}</code> | <b style='color:#00e676;'>🎯 الهدف:</b> <code>{rec['الهدف']:.{dec}f}</code> | <b style='color:#ff5252;'>🛑 الوقف:</b> <code>{rec['الوقف']:.{dec}f}</code></div>"
        html_card += "</div>"
        st.markdown(html_card, unsafe_allow_html=True)
else:
    st.info("لا توجد إشارة جديدة مكتملة في آخر شمعتين حالياً.")

# الإحصائيات والجدول
if not trades_df.empty:
    trades_df = trades_df.sort_values(by="الوقت", ascending=False).reset_index(drop=True)
    
    closed_df = trades_df[trades_df['الحالة'] != 'مفتوحة ⏳']
    total_closed = len(closed_df)
    wins = len(closed_df[closed_df['الحالة'] == 'ناجحة'])
