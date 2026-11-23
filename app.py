import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="لوحة التوصيات وموجات إليوت (5m)", layout="centered")

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
trade_capital = st.number_input("رأس مال الصفقة ($):", min_value=10.0, max_value=100000.0, value=100.0, step=10.0, format="%.2f", key="cap_input")

filter_options = ["الكل"] + list(SYMBOLS_MAP.keys())
selected_coin = st.selectbox("العملة:", filter_options, key="coin_select")

trade_mode = st.radio(
    "نوع الصفقات:",
    options=["شراء فقط (Spot)", "شراء و بيع (Futures)"],
    horizontal=True,
    key="trade_mode_radio"
)

@st.cache_data(ttl=300)
def fetch_market_data(symbols_dict, period_str):
    data_store = {}
    for coin_name, yf_ticker in symbols_dict.items():
        try:
            df = yf.download(yf_ticker, period=period_str, interval="5m", progress=False)
            if df.empty or len(df) < 35:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATR'] = tr.rolling(14).mean()
            data_store[coin_name] = df
        except Exception:
            continue
    return data_store
def analyze_trades_and_signals(data_store, atr_m, rr_m, capital_usd, allow_short):
    all_trades = []
    latest_signals = []

    for coin_name, df in data_store.items():
        in_trade = False
        trade_type = None
        entry_p = sl_p = tp_p = 0.0

        for i in range(20, len(df)):
            row = df.iloc[i]
            atr_val = float(row['ATR'])
            if pd.isna(atr_val) or atr_val == 0:
                continue

            if not in_trade:
                window = df.iloc[i-20:i]
                w0 = float(window['Low'].min())
                w1 = float(window['High'].max())
                diff = w1 - w0
                if diff <= 0:
                    continue

                fib_buy = w1 - (diff * 0.618)
                fib_sell = w0 + (diff * 0.618)

                if float(row['Low']) <= fib_buy <= float(row['High']) and float(row['Close']) > fib_buy:
                    in_trade = True
                    trade_type = "شراء"
                    entry_p = float(row['Close'])
                    sl_p = entry_p - (atr_val * atr_m)
                    tp_p = entry_p + (atr_val * atr_m * rr_m)

                elif allow_short and float(row['Low']) <= fib_sell <= float(row['High']) and float(row['Close']) < fib_sell:
                    in_trade = True
                    trade_type = "بيع"
                    entry_p = float(row['Close'])
                    sl_p = entry_p + (atr_val * atr_m)
                    tp_p = entry_p - (atr_val * atr_m * rr_m)
            else:
                if trade_type == "شراء":
                    if float(row['Low']) <= sl_p:
                        loss_pct = (entry_p - sl_p) / entry_p
                        all_trades.append({"coin": coin_name, "side": "شراء", "result": "loss", "pnl": -(capital_usd * loss_pct)})
                        in_trade = False
                    elif float(row['High']) >= tp_p:
                        profit_pct = (tp_p - entry_p) / entry_p
                        all_trades.append({"coin": coin_name, "side": "شراء", "result": "win", "pnl": (capital_usd * profit_pct)})
                        in_trade = False
                elif trade_type == "بيع":
                    if float(row['High']) >= sl_p:
                        loss_pct = (sl_p - entry_p) / entry_p
                        all_trades.append({"coin": coin_name, "side": "بيع", "result": "loss", "pnl": -(capital_usd * loss_pct)})
                        in_trade = False
                    elif float(row['Low']) <= tp_p:
                        profit_pct = (entry_p - tp_p) / entry_p
                        all_trades.append({"coin": coin_name, "side": "بيع", "result": "win", "pnl": (capital_usd * profit_pct)})
                        in_trade = False

        recent_df = df.tail(30).reset_index(drop=True)
        low_idx = int(recent_df['Low'].idxmin())
        high_idx = int(recent_df['High'].idxmax())
        w0 = float(recent_df['Low'].iloc[low_idx])
        w1 = float(recent_df['High'].iloc[high_idx])
        diff = abs(w1 - w0)
        curr_price = float(recent_df['Close'].iloc[-1])
        curr_atr = float(recent_df['ATR'].iloc[-1]) if not pd.isna(recent_df['ATR'].iloc[-1]) else (curr_price * 0.01)

        if allow_short and high_idx < low_idx:
            sig_type = "بيع"
            entry_sig = w0 + (diff * 0.618)
            sl_sig = entry_sig + (curr_atr * atr_m)
            tp_sig = entry_sig - (curr_atr * atr_m * rr_m)
            pivot_idx = high_idx
        else:
            sig_type = "شراء"
            entry_sig = w1 - (diff * 0.618)
            sl_sig = entry_sig - (curr_atr * atr_m)
            tp_sig = entry_sig + (curr_atr * atr_m * rr_m)
            pivot_idx = low_idx

        candles_ago = (len(recent_df) - 1) - pivot_idx
        decimals = 2 if curr_price >= 10 else 4

        latest_signals.append({
            "coin": coin_name,
            "type": sig_type,
            "price": round(curr_price, decimals),
            "entry": round(entry_sig, decimals),
            "target": round(tp_sig, decimals),
            "sl": round(sl_sig, decimals),
            "candles_ago": candles_ago
        })

    return pd.DataFrame(all_trades), pd.DataFrame(latest_signals)

allow_short_flag = (trade_mode == "شراء و بيع (Futures)")

with st.spinner(f"جاري تحميل بيانات Yahoo Finance ({selected_period_label} - 5m)..."):
    market_data = fetch_market_data(SYMBOLS_MAP, selected_period)

df_trades, df_signals = analyze_trades_and_signals(
    market_data, atr_mult, rr_ratio, trade_capital, allow_short_flag
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

net_color_class = "green-text" if net_profit_usd >= 0 else "red-text"
st.markdown(
    f"<div class='metric-card card-net'>"
    f"<div class='card-title'>✨ صافي الربح — {trade_mode} (رأس مال ${trade_capital:,.0f})</div>"
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

st.markdown("### 🧭 أحدث الإشارات")

if not filtered_signals.empty:
    for _, row in filtered_signals.iterrows():
        is_buy = (row["type"] == "شراء")
        box_class = "signal-box" if is_buy else "signal-box signal-box-short"
        type_color = "green-text" if is_buy else "red-text"

        card_html = (
            f"<div class='{box_class}'>"
            f"<div style='font-size:17px; font-weight:bold; color:#fff; margin-bottom:8px;'>"
            f"🪙 {row['coin']} (${row['price']}) — <span class='{type_color}'>{row['type']}</span> "
            f"<span style='font-size:14px; color:#a0aec0; font-weight:normal;'>(منذ {row['candles_ago']} شمعة)</span>"
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
    st.warning("لا توجد بيانات متاحة حالياً من Yahoo Finance، يرجى المحاولة بعد لحظات.")
