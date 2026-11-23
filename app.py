import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="لوحة التوصيات — تقاطع المتوسطات + ترند 100 (5m)", layout="centered")

css_style = """
<style>
.stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }
div[role='radiogroup'] { display: flex; justify-content: space-around; background-color: #1c1c24; padding: 6px; border-radius: 12px; margin-bottom: 15px; }
div[role='radiogroup'] label { padding: 8px 18px; border-radius: 8px; color: #ffffff !important; cursor: pointer; }
.metric-card { border-radius: 15px; padding: 18px; text-align: center; background-color: #16161e; margin-bottom: 15px; }
.card-blue { border: 1.5px solid #2b6cb0; }
.card-purple { border: 1.5px solid #805ad5; }
.card-green { border: 1.5px solid #38a169; }
.card-red { border: 1.5px solid #e53e3e; }
.card-net { border: 1.5px solid #805ad5; background: linear-gradient(180deg, #1a1625 0%, #16161e 100%); padding: 22px; }
.card-title { font-size: 15px; color: #a0aec0; margin-bottom: 8px; }
.card-value { font-size: 28px; font-weight: bold; }
.net-value { font-size: 36px; font-weight: bold; color: #48bb78; margin-top: 5px; }
.green-text { color: #48bb78; }
.red-text { color: #f56565; }
.white-text { color: #ffffff; }
.signal-box { background-color: #16161e; border-right: 4px solid #38a169; padding: 15px; border-radius: 12px; margin-bottom: 12px; border-top: 1px solid #23232f; border-bottom: 1px solid #23232f; border-left: 1px solid #23232f; }
.signal-box-short { border-right: 4px solid #e53e3e; }
</style>
"""
st.markdown(css_style, unsafe_allow_html=True)

SYMBOLS_MAP = {
    "XLM": "XLM-USD",
    "ZEC": "ZEC-USD",
    "XRP": "XRP-USD",
    "HBAR": "HBAR-USD",
    "ADA": "ADA-USD",
    "LTC": "LTC-USD",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "PAXG": "PAXG-USD",
    "XAU": "GC=F"
}

period_map = {
    "24 ساعة": "1d",
    "أسبوع": "7d",
    "شهر": "30d"
}
selected_period_label = st.radio(
    "الفترة:",
    options=list(period_map.keys()),
    horizontal=True,
    label_visibility="collapsed",
    key="period_radio"
)
selected_period = period_map[selected_period_label]

atr_mult = st.number_input("ATR SL:", min_value=0.5, max_value=15.0, value=4.0, step=0.1, format="%.2f", key="atr_input")
rr_ratio = st.number_input("R:R:", min_value=0.5, max_value=15.0, value=3.70, step=0.1, format="%.2f", key="rr_input")

filter_options = ["الكل"] + list(SYMBOLS_MAP.keys())
selected_coin = st.selectbox("العملة:", filter_options, key="coin_select")

col_opt1, col_opt2 = st.columns([2, 1])
with col_opt1:
    trade_mode = st.radio(
        "نوع الصفقات:",
        options=["شراء فقط (Spot)", "شراء و بيع (Futures)"],
        horizontal=True,
        key="trade_mode_radio"
    )
with col_opt2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    use_trend_filter = st.checkbox("فلتر الترند (EMA 100)", value=True, key="trend_checkbox")

def calc_wma(series, period=20):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

@st.cache_data(ttl=300)
def fetch_market_data(symbols_dict, period_str):
    data_store = {}
    fetch_period = "5d" if period_str == "1d" else ("14d" if period_str == "7d" else "45d")
    eval_bars = 288 if period_str == "1d" else (2016 if period_str == "7d" else 8640)

    for coin_name, yf_ticker in symbols_dict.items():
        try:
            df = yf.download(yf_ticker, period=fetch_period, interval="5m", progress=False)
            if df.empty or len(df) < 110:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATR'] = tr.rolling(14).mean()

            # حساب المتوسطات: EMA 2 و WMA 20 و EMA 100 للترند
            df['EMA2'] = df['Close'].ewm(span=2, adjust=False).mean()
            df['WMA20'] = calc_wma(df['Close'], period=20)
            df['EMA100'] = df['Close'].ewm(span=100, adjust=False).mean()

            df_eval = df.tail(eval_bars).copy()
            data_store[coin_name] = df_eval
        except Exception:
            continue
    return data_store
def analyze_ma_crossover(data_store, atr_m, rr_m, allow_short, trend_active):
    all_trades = []
    latest_signals = []
    capital_usd = 100.0  # رأس مال ثابت 100 دولار لكل صفقة في الخلفية

    for coin_name, df in data_store.items():
        in_trade = False
        trade_type = None
        entry_p = sl_p = tp_p = 0.0
        last_signal = None

        for i in range(1, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            atr_val = float(curr['ATR'])
            if pd.isna(atr_val) or atr_val == 0 or pd.isna(curr['WMA20']) or pd.isna(prev['WMA20']) or pd.isna(curr['EMA100']):
                continue

            close_p = float(curr['Close'])
            ema100_p = float(curr['EMA100'])

            # شروط الترند (EMA 100)
            trend_up = (close_p > ema100_p) if trend_active else True
            trend_down = (close_p < ema100_p) if trend_active else True

            cross_up = (float(prev['EMA2']) <= float(prev['WMA20'])) and (float(curr['EMA2']) > float(curr['WMA20'])) and trend_up
            cross_down = (float(prev['EMA2']) >= float(prev['WMA20'])) and (float(curr['EMA2']) < float(curr['WMA20'])) and trend_down

            # تسجيل آخر تقاطع متوافق مع الفلتر
            if cross_up:
                last_signal = {
                    "type": "شراء",
                    "entry": close_p,
                    "sl": close_p - (atr_val * atr_m),
                    "tp": close_p + (atr_val * atr_m * rr_m),
                    "bar_idx": i,
                    "trend_dir": "صاعد ↗" if close_p > ema100_p else "هابط ↘"
                }
            elif cross_down and allow_short:
                last_signal = {
                    "type": "بيع",
                    "entry": close_p,
                    "sl": close_p + (atr_val * atr_m),
                    "tp": close_p - (atr_val * atr_m * rr_m),
                    "bar_idx": i,
                    "trend_dir": "هابط ↘" if close_p < ema100_p else "صاعد ↗"
                }

            # محاكاة الصفقات التاريخية (Backtest)
            if not in_trade:
                if cross_up:
                    in_trade = True
                    trade_type = "شراء"
                    entry_p = close_p
                    sl_p = entry_p - (atr_val * atr_m)
                    tp_p = entry_p + (atr_val * atr_m * rr_m)

                elif allow_short and cross_down:
                    in_trade = True
                    trade_type = "بيع"
                    entry_p = close_p
                    sl_p = entry_p + (atr_val * atr_m)
                    tp_p = entry_p - (atr_val * atr_m * rr_m)
            else:
                if trade_type == "شراء":
                    if float(curr['Low']) <= sl_p:
                        loss_pct = (entry_p - sl_p) / entry_p
                        all_trades.append({"coin": coin_name, "result": "loss", "pnl": -(capital_usd * loss_pct)})
                        in_trade = False
                    elif float(curr['High']) >= tp_p:
                        profit_pct = (tp_p - entry_p) / entry_p
                        all_trades.append({"coin": coin_name, "result": "win", "pnl": (capital_usd * profit_pct)})
                        in_trade = False
                elif trade_type == "بيع":
                    if float(curr['High']) >= sl_p:
                        loss_pct = (sl_p - entry_p) / entry_p
                        all_trades.append({"coin": coin_name, "result": "loss", "pnl": -(capital_usd * loss_pct)})
                        in_trade = False
                    elif float(curr['Low']) <= tp_p:
                        profit_pct = (entry_p - tp_p) / entry_p
                        all_trades.append({"coin": coin_name, "result": "win", "pnl": (capital_usd * profit_pct)})
                        in_trade = False

        if last_signal is not None:
            curr_price = float(df['Close'].iloc[-1])
            candles_ago = (len(df) - 1) - last_signal["bar_idx"]
            decimals = 2 if curr_price >= 10 else 4

            latest_signals.append({
                "coin": coin_name,
                "type": last_signal["type"],
                "price": round(curr_price, decimals),
                "entry": round(last_signal["entry"], decimals),
                "target": round(last_signal["tp"], decimals),
                "sl": round(last_signal["sl"], decimals),
                "candles_ago": candles_ago,
                "trend_dir": last_signal["trend_dir"]
            })

    return pd.DataFrame(all_trades), pd.DataFrame(latest_signals)

allow_short_flag = (trade_mode == "شراء و بيع (Futures)")

with st.spinner(f"جاري تحليل تقاطع EMA2 × WMA20 ({selected_period_label} - 5m)..."):
    market_data = fetch_market_data(SYMBOLS_MAP, selected_period)

df_trades, df_signals = analyze_ma_crossover(
    market_data, atr_mult, rr_ratio, allow_short_flag, use_trend_filter
)

if selected_coin != "الكل":
    filtered_trades = df_trades[df_trades["coin"] == selected_coin] if not df_trades.empty else pd.DataFrame()
    filtered_signals = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else pd.DataFrame()
else:
    filtered_trades = df_trades
    filtered_signals = df_signals

total_trades = len(filtered_trades)
win_trades = len(filtered_trades[filtered_trades["result"] == "win"]) if total_trades > 0 else 0
loss_trades = len(filtered_trades[filtered_trades["result"] == "loss"]) if total_trades > 0 else 0
win_rate = round((win_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
total_profit_usd = round(filtered_trades[filtered_trades["pnl"] > 0]["pnl"].sum(), 2) if total_trades > 0 else 0.0
total_loss_usd = round(abs(filtered_trades[filtered_trades["pnl"] < 0]["pnl"].sum()), 2) if total_trades > 0 else 0.0
net_profit_usd = round(total_profit_usd - total_loss_usd, 2)

trend_badge = "مع فلتر EMA 100" if use_trend_filter else "بدون فلتر ترند"
net_color_class = "green-text" if net_profit_usd >= 0 else "red-text"
st.markdown(
    f"<div class='metric-card card-net'>"
    f"<div class='card-title'>✨ صافي الربح ({trade_mode} | {trend_badge})</div>"
    f"<div class='net-value {net_color_class}'>${net_profit_usd:,.2f}</div>"
    f"</div>",
    unsafe_allow_html=True
)

st.markdown(f"### 📊 نتائج {selected_period_label} (5m)")

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>🤝 الصفقات</div><div class='card-value white-text'>{total_trades}</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>🎯 النجاح</div><div class='card-value white-text'>{win_rate}%</div></div>", unsafe_allow_html=True)

col3, col4 = st.columns(2)
with col3:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title green-text'>📈 الصفقات الرابحة</div><div class='card-value white-text'>{win_trades}</div></div>", unsafe_allow_html=True)
with col4:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title red-text'>📉 الصفقات الخاسرة</div><div class='card-value white-text'>{loss_trades}</div></div>", unsafe_allow_html=True)

col5, col6 = st.columns(2)
with col5:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title green-text'>💲 إجمالي الأرباح</div><div class='card-value white-text'>${total_profit_usd:,.2f}+</div></div>", unsafe_allow_html=True)
with col6:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title red-text'>💲 إجمالي الخسائر</div><div class='card-value white-text'>${total_loss_usd:,.2f}-</div></div>", unsafe_allow_html=True)

st.markdown("### 🧭 أحدث الإشارات (EMA2 × WMA20)")

if not filtered_signals.empty:
    sorted_signals = filtered_signals.sort_values(by="candles_ago", ascending=True)
    for _, row in sorted_signals.iterrows():
        is_buy = (row["type"] == "شراء")
        box_class = "signal-box" if is_buy else "signal-box signal-box-short"
        type_color = "green-text" if is_buy else "red-text"

        card_html = (
            f"<div class='{box_class}'>"
            f"<div style='font-size:17px; font-weight:bold; color:#fff; margin-bottom:8px;'>"
            f"🪙 {row['coin']} (${row['price']}) — <span class='{type_color}'>{row['type']}</span> "
            f"<span style='font-size:13px; color:#a0aec0; font-weight:normal;'>(منذ {row['candles_ago']} شمعة | ترند 100: {row['trend_dir']})</span>"
            f"</div>"
            f"<div style='font-size:14px; color:#e2e8f0; line-height:1.8;'>"
            f"🔵 دخول: <b>{row['entry']}$</b> &nbsp;|&nbsp; "
            f"🟢 هدف: <b>{row['target']}$</b> &nbsp;|&nbsp; "
            f"🔴 وقف: <b>{row['sl']}$</b>"
            f"</div>"
            f"</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)
else:
    st.warning("لا توجد تقاطعات متوافقة مع الشروط الحالية.")
