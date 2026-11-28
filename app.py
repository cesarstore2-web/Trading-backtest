import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="قناص السكالبينج الذكي - ATR & RSI", layout="centered")

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

if 'ema_scalp' not in st.session_state:
    st.session_state.ema_scalp = 50
if 'rsi_scalp' not in st.session_state:
    st.session_state.rsi_scalp = 35
if 'atr_sl_mult' not in st.session_state:
    st.session_state.atr_sl_mult = 1.5
if 'rr_ratio' not in st.session_state:
    st.session_state.rr_ratio = 2.2
if 'trade_amount' not in st.session_state:
    st.session_state.trade_amount = 100.0

TIMEFRAME_OPTIONS = {
    "15 دقيقة (15m) - الأفضل لقنص 3-5 صفقات يومياً": ("15m", "35d"),
    "30 دقيقة (30m)": ("30m", "45d"),
    "1 ساعة (1h)": ("1h", "60d"),
    "5 دقائق (5m)": ("5m", "14d")
}

selected_tf_label = st.selectbox(
    "⏱️ اختر الإطار الزمني للسكالبينج:",
    options=list(TIMEFRAME_OPTIONS.keys()),
    index=0
)
TIMEFRAME, DATA_PERIOD = TIMEFRAME_OPTIONS[selected_tf_label]

@st.cache_data(ttl=180, show_spinner=False)
def fetch_coin_data(symbol, period_str, timeframe):
    return yf.Ticker(symbol).history(period=period_str, interval=timeframe)

def calculate_rsi(series, period=7):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def run_smart_scalper(timeframe, period_str, ema_len, rsi_level, atr_mult, rr_ratio, trade_amount):
    trades_history = []
    current_opportunities = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx_coin, symbol in enumerate(COINS):
        coin_name = symbol.replace("-USD", "")
        status_text.caption(f"⚡ جاري تحليل الزخم والسيولة لـ {coin_name} ({idx_coin + 1}/{len(COINS)})...")
        progress_bar.progress((idx_coin + 1) / len(COINS))

        try:
            df = fetch_coin_data(symbol, period_str, timeframe)
            if df is None or df.empty or len(df) < ema_len + 20:
                continue

            # توحيد التوقيت وإزالة المنطقة الزمنية لتجنب أخطاء التصفية
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
            df['RSI'] = calculate_rsi(df['Close'], period=7)
            df['Prev_RSI'] = df['RSI'].shift(1)
            df['ATR'] = calculate_atr(df, period=14)
            df['Vol_MA'] = df['Volume'].rolling(window=20).mean()
            df['Is_Green'] = df['Close'] > df['Open']

            # شروط الدخول الذكية:
            # 1. السعر فوق EMA 50 (زخم صاعد)
            # 2. RSI(7) ارتد صعوداً من مستوى التشبع
            # 3. شمعة خضراء مدعومة بسيولة أعلى من متوسط 20 شمعة
            df['Buy_Signal'] = (
                (df['Close'] > df['EMA']) &
                (df['Prev_RSI'] <= rsi_level) &
                (df['RSI'] > rsi_level) &
                df['Is_Green'] &
                (df['Volume'] >= df['Vol_MA'] * 0.9)
            )

            # فحص الفرص الحالية (آخر شمعتين)
            if df.tail(2)['Buy_Signal'].any():
                last_price = float(df['Close'].iloc[-1])
                last_atr = float(df['ATR'].iloc[-1])
                last_rsi = float(df['RSI'].iloc[-1])
                if not np.isnan(last_atr) and last_atr > 0:
                    risk_dist = last_atr * atr_mult
                    sl_p = last_price - risk_dist
                    tp_p = last_price + (risk_dist * rr_ratio)
                    tp_pct_est = ((tp_p - last_price) / last_price) * 100
                    current_opportunities.append({
                        "العملة": coin_name,
                        "السعر الحالي": round(last_price, 4),
                        "هدف الربح (ATR)": f"{round(tp_p, 4)} (+{round(tp_pct_est, 2)}%)",
                        "وقف الخسارة (ATR)": round(sl_p, 4),
                        "RSI (7)": round(last_rsi, 1),
                        "الوقت": str(df.index[-1])[:16]
                    })

            # محاكاة الصفقات التاريخية
            in_position = False
            buy_price = 0.0
            tp_price = 0.0
            sl_price = 0.0
            buy_time = None

            sub_df = df.iloc[ema_len:]
            for idx, row in sub_df.iterrows():
                curr_high = float(row['High'])
                curr_low = float(row['Low'])
                curr_close = float(row['Close'])
                curr_atr = float(row['ATR'])

                if not in_position and row['Buy_Signal'] and not np.isnan(curr_atr) and curr_atr > 0:
                    in_position = True
                    buy_price = curr_close
                    risk_dist = curr_atr * atr_mult
                    sl_price = buy_price - risk_dist
                    tp_price = buy_price + (risk_dist * rr_ratio)
                    buy_time = idx

                elif in_position:
                    sell_reason = None
                    sell_price = 0.0

                    if curr_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = "وقف خسارة (ATR)"
                    elif curr_high >= tp_price:
                        sell_price = tp_price
                        sell_reason = f"هدف ربح (1:{rr_ratio})"

                    if sell_reason:
                        profit_pct = (sell_price - buy_price) / buy_price
                        profit_usd = trade_amount * profit_pct
                        trades_history.append({
                            "العملة": coin_name,
                            "تاريخ الشراء": buy_time,
                            "سعر الشراء": round(buy_price, 4),
                            "تاريخ البيع": idx,
                            "سعر البيع": round(sell_price, 4),
                            "سبب الإغلاق": sell_reason,
                            "الربح ($)": round(profit_usd, 2),
                            "النسبة (%)": round(profit_pct * 100, 2)
                        })
                        in_position = False

        except Exception:
            continue

    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities)

trades_df, opps_df = run_smart_scalper(
    TIMEFRAME,
    DATA_PERIOD,
    st.session_state.ema_scalp,
    st.session_state.rsi_scalp,
    st.session_state.atr_sl_mult,
    st.session_state.rr_ratio,
    st.session_state.trade_amount
)

weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()
now = pd.Timestamp.utcnow().tz_localize(None)

if not trades_df.empty:
    trades_df['تاريخ البيع'] = pd.to_datetime(trades_df['تاريخ البيع'])
    trades_df['تاريخ الشراء'] = pd.to_datetime(trades_df['تاريخ الشراء'])
    
    # بداية الشهر الحالي (بدون فروقات توقيت)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_trades = trades_df[trades_df['تاريخ البيع'] >= start_of_month].copy()
    
    # بداية الأسبوع الحالي (الإثنين)
    start_of_week = (now - pd.Timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_trades = trades_df[trades_df['تاريخ البيع'] >= start_of_week].copy()
    weekly_profit = weekly_trades['الربح ($)'].sum()

box_class = "profit-box-green" if weekly_profit >= 0 else "profit-box-red"
amount_class = "profit-amount-green" if weekly_profit >= 0 else "profit-amount-red"
sign = "+" if weekly_profit > 0 else ""

profit_html = f'<div class="{box_class}"><div class="profit-title">الربح الصافي للأسبوع الحالي 💰</div><div class="{amount_class}">{sign}{weekly_profit:.2f}$</div></div>'
st.markdown(profit_html, unsafe_allow_html=True)

if st.checkbox("🔥 إظهار ملخص الأداء للأسبوع الحالي"):
    if not weekly_trades.empty:
        win_rate = (len(weekly_trades[weekly_trades['الربح ($)'] > 0]) / len(weekly_trades)) * 100
        days_passed = max(1, now.weekday() + 1)
        avg_daily = len(weekly_trades) / days_passed
