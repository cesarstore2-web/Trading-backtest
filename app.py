import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="متتبع التداول الفوري - Bullish CISD & FVG", layout="centered")

css = (
    "<style>"
    ".main { direction: rtl; text-align: right; }"
    "div[data-testid='stCheckbox'] { direction: rtl; text-align: right; }"
    "div[data-testid='stSelectbox'], div[data-testid='stNumberInput'] { direction: rtl; text-align: right; }"
    ".profit-box-green { background-color: #0d3b1e; border: 2px solid #28a745; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-box-red { background-color: #3b0d0d; border: 2px solid #dc3545; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }"
    ".profit-amount-green { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".profit-amount-red { color: #ff6b6b; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".info-bar { color: #aaaaaa; font-size: 13px; text-align: center; margin: 15px 0; padding: 8px; background-color: #1e1e1e; border-radius: 8px; }"
    ".alert-box { background-color: #162436; border: 1px solid #2b4c7e; border-radius: 10px; padding: 15px; text-align: center; color: #90caf9; }"
    "</style>"
)
st.markdown(css, unsafe_allow_html=True)

COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", 
    "XLM-USD", "VET-USD", "HBAR-USD", "FIL-USD", "ICP-USD", 
    "APT-USD", "ARB-USD", "OP-USD", "RENDER-USD", "GRT-USD", 
    "TIA-USD", "SUI-USD"
]

if 'rr_ratio' not in st.session_state:
    st.session_state.rr_ratio = 2.0
if 'swing_lookback' not in st.session_state:
    st.session_state.swing_lookback = 15
if 'use_sl' not in st.session_state:
    st.session_state.use_sl = True
if 'trade_amount' not in st.session_state:
    st.session_state.trade_amount = 100.0

TIMEFRAME_OPTIONS = {
    "5 دقائق (5m)": ("5m", "35d"),
    "15 دقيقة (15m)": ("15m", "35d"),
    "30 دقيقة (30m)": ("30m", "35d"),
    "1 ساعة (1h)": ("1h", "45d"),
    "4 ساعات (4h)": ("4h", "60d"),
    "يومي (1d)": ("1d", "180d")
}

selected_tf_label = st.selectbox(
    "⏱️ اختر الإطار الزمني للتداول:",
    options=list(TIMEFRAME_OPTIONS.keys()),
    index=0
)
TIMEFRAME, DATA_PERIOD = TIMEFRAME_OPTIONS[selected_tf_label]

@st.cache_data(ttl=180)
def run_cisd_scanner(timeframe, period_str, rr_ratio, swing_lookback, use_sl, trade_amount):
    trades_history = []
    current_opportunities = []

    for symbol in COINS:
        try:
            df = yf.download(symbol, period=period_str, interval=timeframe, progress=False)
            if df.empty or len(df) < swing_lookback + 10:
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()
            time_col = df.columns[0]

            in_position = False
            buy_price = 0.0
            sl_price = 0.0
            tp_price = 0.0
            buy_time = None

            # حالة تتبع نموذج CISD و FVG
            cisd_active = False
            sweep_low = 0.0
            old_high = 0.0
            fvg_top = 0.0
            fvg_bottom = 0.0
            has_fvg = False
            cisd_bar_idx = -1

            for i in range(swing_lookback + 3, len(df)):
                curr_open = float(df.loc[i, 'Open'])
                curr_high = float(df.loc[i, 'High'])
                curr_low = float(df.loc[i, 'Low'])
                curr_close = float(df.loc[i, 'Close'])
                curr_time = df.loc[i, time_col]

                # 1. إدارة الصفقة المفتوحة حالياً
                if in_position:
                    sell_reason = None
                    sell_price = 0.0

                    if use_sl and curr_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = "وقف خسارة (SL below low)"
                    elif curr_high >= tp_price:
                        sell_price = tp_price
                        sell_reason = f"هدف الربح (RR 1:{rr_ratio})"

                    if sell_reason:
                        profit_pct = (sell_price - buy_price) / buy_price
                        profit_usd = trade_amount * profit_pct
                        trades_history.append({
                            "العملة": symbol.replace("-USD", ""),
                            "تاريخ الشراء": str(buy_time)[:16],
                            "سعر الشراء": round(buy_price, 4),
                            "تاريخ البيع": str(curr_time)[:16],
                            "سعر البيع": round(sell_price, 4),
                            "سبب الإغلاق": sell_reason,
                            "الربح ($)": round(profit_usd, 2),
                            "النسبة (%)": round(profit_pct * 100, 2)
                        })
                        in_position = False
                    continue

                # 2. البحث عن نموذج Bullish CISD (سحب سيولة + إغلاق فوق افتتاح أول شمعة هابطة)
                prev_window = df.iloc[i - swing_lookback : i]
                prev_swing_low = float(prev_window['Low'].min())
                prev_swing_high = float(prev_window['High'].max())

                # التحقق من سحب السيولة في آخر 4 شموع وإغلاق شمعة صاعدة فوق افتتاح أول شمعة هابطة
                recent_4 = df.iloc[i-4 : i+1]
                recent_min_low = float(recent_4['Low'].min())

                if recent_min_low < prev_swing_low and curr_close > curr_open:
                    # تحديد أول شمعة هابطة في موجة النزول الأخيرة
                    bearish_candles = recent_4[recent_4['Close'] < recent_4['Open']]
                    if not bearish_candles.empty:
                        first_bearish_open = float(bearish_candles.iloc[0]['Open'])
                        # شرط CISD: إغلاق جسم الشمعة الصاعدة فوق افتتاح أول شمعة هابطة
                        if curr_close > first_bearish_open:
                            cisd_active = True
                            sweep_low = recent_min_low
                            old_high = prev_swing_high
                            cisd_bar_idx = i
                            has_fvg = False

                            # البحث عن فجوة قيمة عادلة FVG بين الشمعة i-2 والشمعة الحالية i
                            candle_minus_2_high = float(df.loc[i-2, 'High'])
                            if curr_low > candle_minus_2_high:
                                has_fvg = True
                                fvg_top = curr_low
                                fvg_bottom = candle_minus_2_high

                # 3. الدخول عند إعادة اختبار FVG (Buy here) أو مباشرة بعد CISD
                if cisd_active and i > cisd_bar_idx:
                    # إلغاء النموذج إذا كسر السعر قاع سحب السيولة أو مر أكثر من 8 شموع
                    if curr_low < sweep_low or (i - cisd_bar_idx) > 8:
                        cisd_active = False
                        continue

                    entry_triggered = False
                    entry_price = 0.0

                    if has_fvg:
                        # الدخول عند لمس السعر لمنطقة FVG
                        if curr_low <= fvg_top and curr_close >= fvg_bottom:
                            entry_triggered = True
                            entry_price = fvg_top
                    else:
                        # إذا لم تتشكل FVG واضحة، الدخول عند أول تراجع طفيف بعد CISD
                        if curr_low <= float(df.loc[cisd_bar_idx, 'Close']):
                            entry_triggered = True
                            entry_price = float(df.loc[cisd_bar_idx, 'Close'])

                    if entry_triggered and entry_price > sweep_low:
                        risk = entry_price - sweep_low
                        # تجنب الصفقات ذات المخاطرة المجهرية جداً (أقل من 0.2%)
                        if (risk / entry_price) >= 0.002:
                            in_position = True
                            buy_price = entry_price
                            sl_price = sweep_low * 0.999
                            tp_price = buy_price + (risk * rr_ratio)
                            buy_time = curr_time
                            cisd_active = False

            # 4. فحص الفرص الحالية الجاهزة للدخول الآن (في آخر شمعتين)
            if cisd_active and (len(df) - 1 - cisd_bar_idx) <= 4:
                last_price = float(df.iloc[-1]['Close'])
                risk = last_price - sweep_low
                if risk > 0:
                    est_tp = last_price + (risk * rr_ratio)
                    current_opportunities.append({
                        "العملة": symbol.replace("-USD", ""),
                        "حالة النموذج": "Bullish CISD + FVG" if has_fvg else "Bullish CISD",
                        "السعر الحالي": round(last_price, 4),
                        "منطقة الشراء (FVG)": round(fvg_top, 4) if has_fvg else round(last_price, 4),
                        "وقف الخسارة (SL)": round(sweep_low, 4),
                        f"الهدف (RR 1:{rr_ratio})": round(est_tp, 4),
                        "الوقت": str(df.iloc[-1][time_col])[:16]
                    })

        except Exception:
            continue

    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities)

trades_df, opps_df = run_cisd_scanner(
    TIMEFRAME,
    DATA_PERIOD,
    st.session_state.rr_ratio,
    st.session_state.swing_lookback,
    st.session_state.use_sl,
    st.session_state.trade_amount
)

weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()

if not trades_df.empty:
    trades_df['تاريخ البيع_dt'] = pd.to_datetime(trades_df['تاريخ البيع'])
    now = pd.Timestamp.now(tz=trades_df['تاريخ البيع_dt'].dt.tz)
    
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
