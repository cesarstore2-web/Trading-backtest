import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="قناص الاختراق والسيولة - Spot", layout="centered")

css = (
    "<style>"
    ".main { direction: rtl; text-align: right; }"
    "div[data-testid='stSelectbox'], div[data-testid='stNumberInput'], div[data-testid='stCheckbox'] { direction: rtl; text-align: right; }"
    ".profit-box-green { background-color: #0d3b1e; border: 2px solid #28a745; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 15px; }"
    ".profit-box-red { background-color: #3b0d0d; border: 2px solid #dc3545; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 15px; }"
    ".profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }"
    ".profit-amount-green { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".profit-amount-red { color: #ff6b6b; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".info-bar { color: #aaaaaa; font-size: 13px; text-align: center; margin: 10px 0 15px 0; padding: 8px; background-color: #1e1e1e; border-radius: 8px; }"
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

if 'swing_len' not in st.session_state:
    st.session_state.swing_len = 12
if 'vol_mult' not in st.session_state:
    st.session_state.vol_mult = 1.3
if 'rr_ratio' not in st.session_state:
    st.session_state.rr_ratio = 2.0
if 'trade_amount' not in st.session_state:
    st.session_state.trade_amount = 100.0
if 'use_trend' not in st.session_state:
    st.session_state.use_trend = True
if 'ema_period' not in st.session_state:
    st.session_state.ema_period = 200

TIMEFRAME_OPTIONS = {
    "5 دقائق (5m)": ("5m", "30d"),
    "15 دقيقة (15m)": ("15m", "35d"),
    "30 دقيقة (30m)": ("30m", "45d"),
    "1 ساعة (1h)": ("1h", "60d")
}

col_top1, col_top2 = st.columns(2)
with col_top1:
    selected_tf_label = st.selectbox("⏱️ الإطار الزمني:", options=list(TIMEFRAME_OPTIONS.keys()), index=0)
with col_top2:
    st.write("")
    st.write("")
    st.session_state.use_trend = st.checkbox(f"ترند EMA {st.session_state.ema_period}", value=st.session_state.use_trend)

TIMEFRAME, DATA_PERIOD = TIMEFRAME_OPTIONS[selected_tf_label]

@st.cache_data(ttl=180, show_spinner=False)
def run_breakout_scanner(timeframe, period_str, swing_len, vol_mult, rr_ratio, trade_amount, use_trend, ema_period):
    trades_history = []
    current_opportunities = []
    try:
        all_data = yf.download(COINS, period=period_str, interval=timeframe, group_by='ticker', progress=False, threads=True)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

    for symbol in COINS:
        coin_name = symbol.replace("-USD", "")
        try:
            if symbol not in all_data.columns.get_level_values(0):
                continue
            df = all_data[symbol].dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
            min_bars = (ema_period + 5) if use_trend else (swing_len + 25)
            if len(df) < min_bars:
                continue
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            df['EMA'] = df['Close'].ewm(span=ema_period, adjust=False).mean()
            df['PSH'] = df['High'].shift(1).rolling(window=swing_len).max()
            df['PSL'] = df['Low'].shift(1).rolling(window=swing_len).min()
            df['Vol_MA'] = df['Volume'].shift(1).rolling(window=20).mean()
            df['Is_Green'] = df['Close'] > df['Open']

            trend_cond = (df['Close'] > df['EMA']) if use_trend else True
            df['Buy_Signal'] = trend_cond & (df['Close'] > df['PSH']) & df['Is_Green'] & (df['Volume'] >= df['Vol_MA'] * vol_mult)

            if df.tail(3)['Buy_Signal'].any():
                last_price = float(df['Close'].iloc[-1])
                sl_p = float(df['PSL'].iloc[-1])
                risk = last_price - sl_p
                if risk > 0 and (risk / last_price) >= 0.003:
                    tp_p = last_price + (risk * rr_ratio)
                    tp_pct = ((tp_p - last_price) / last_price) * 100
                    current_opportunities.append({
                        "العملة": coin_name,
                        "سعر الدخول": round(last_price, 4),
                        f"الهدف (1:{rr_ratio})": f"{round(tp_p, 4)} (+{round(tp_pct, 2)}%)",
                        "وقف الخسارة": round(sl_p, 4),
                        "الوقت": str(df.index[-1])[:16]
                    })

            in_position = False
            buy_price = 0.0
            sl_price = 0.0
            tp_price = 0.0
            breakeven_price = 0.0
            is_secured = False
            buy_time = None

            start_idx = ema_period if use_trend else (swing_len + 20)
            sub_df = df.iloc[start_idx:]

            for idx, row in sub_df.iterrows():
                curr_high = float(row['High'])
                curr_low = float(row['Low'])
                curr_close = float(row['Close'])

                if not in_position and row['Buy_Signal']:
                    psl_val = float(row['PSL'])
                    risk = curr_close - psl_val
                    if risk > 0 and 0.003 <= (risk / curr_close) <= 0.06:
                        in_position = True
                        buy_price = curr_close
                        sl_price = psl_val
                        tp_price = buy_price + (risk * rr_ratio)
                        breakeven_price = buy_price + risk
                        is_secured = False
                        buy_time = idx
                elif in_position:
                    if not is_secured and curr_high >= breakeven_price:
                        sl_price = buy_price * 1.001
                        is_secured = True
                    sell_reason = None
                    sell_price = 0.0
                    if curr_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = "تأمين بدون خسارة (BE)" if is_secured else "وقف خسارة (PSL)"
                    elif curr_high >= tp_price:
                        sell_price = tp_price
                        sell_reason = f"هدف كامل (1:{rr_ratio})"
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

    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities)

with st.spinner("⚡ جاري تحديث البيانات والسجلات..."):
    trades_df, opps_df = run_breakout_scanner(
        TIMEFRAME, DATA_PERIOD, st.session_state.swing_len, st.session_state.vol_mult,
        st.session_state.rr_ratio, st.session_state.trade_amount, st.session_state.use_trend, st.session_state.ema_period
    )

weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()
now = pd.Timestamp.utcnow().tz_localize(None)

if not trades_df.empty:
    trades_df['تاريخ البيع'] = pd.to_datetime(trades_df['تاريخ البيع'])
    trades_df['تاريخ الشراء'] = pd.to_datetime(trades_df['تاريخ الشراء'])
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_trades = trades_df[trades_df['تاريخ البيع'] >= start_of_month].copy()
    start_of_week = (now - pd.Timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_trades = trades_df[trades_df['تاريخ البيع'] >= start_of_week].copy()
    weekly_profit = weekly_trades['الربح ($)'].sum()

box_class = "profit-box-green" if weekly_profit >= 0 else "profit-box-red"
amount_class = "profit-amount-green" if weekly_profit >= 0 else "profit-amount-red"
sign = "+" if weekly_profit > 0 else ""

profit_html = f'<div class="{box_class}"><div class="profit-title">الربح الصافي للأسبوع الحالي 💰</div><div class="{amount_class}">{sign}{weekly_profit:.2f}$</div></div>'
st.markdown(profit_html, unsafe_allow_html=True)

trend_label = f"مفعل (EMA {st.session_state.ema_period})" if st.session_state.use_trend else "ملغي (حر)"
info_html = f'<div class="info-bar">العملات: {len(COINS)} | الترند: {trend_label} | الهدف: 1:{st.session_state.rr_ratio} | الفريم: {TIMEFRAME}</div>'
st.markdown(info_html, unsafe_allow_html=True)

section = st.selectbox(
    "📂 اختر القسم للعرض:",
    options=[
        "🎯 التوصيات والفرص الحالية",
        "🔥 أداء الأسبوع الحالي",
        "📅 سجل 4 أسابيع (الشهر الحالي)",
        "📋 تفاصيل جميع الصفقات",
        "⚙️ إعدادات الاستراتيجية والمتوسط"
    ],
    index=0
)

st.divider()

if section == "🎯 التوصيات والفرص الحالية":
    st.subheader("🎯 التوصيات المستقبلية (الفرص الحالية)")
    if not opps_df.empty:
        st.success(f"تم قنص {len(opps_df)} فرصة مطابقة للشروط!")
        st.dataframe(opps_df, use_container_width=True)
    else:
        st.markdown('<div class="alert-box">لا توجد إشارة اختراق في آخر 3 شموع.. الماسح يراقب الـ 22 عملة تلقائياً.</div>', unsafe_allow_html=True)

