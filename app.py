import streamlit as st
import pandas as pd
import numpy as np
import ccxt

st.set_page_config(page_title="لوحة التوصيات وموجات إليوت", layout="centered")

css_style = (
    "<style>"
    ".stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }"
    "div[role='radiogroup'] { display: flex; justify-content: space-around; background-color: #1c1c24; padding: 6px; border-radius: 12px; margin-bottom: 15px; }"
    "div[role='radiogroup'] label { padding: 8px 20px; border-radius: 8px; color: #ffffff !important; }"
    ".metric-card { border-radius: 15px; padding: 18px; text-align: center; background-color: #16161e; margin-bottom: 15px; }"
    ".card-blue { border: 1.5px solid #2b6cb0; }"
    ".card-purple { border: 1.5px solid #805ad5; }"
    ".card-green { border: 1.5px solid #38a169; }"
    ".card-red { border: 1.5px solid #e53e3e; }"
    ".card-net { border: 1.5px solid #805ad5; background: linear-gradient(90deg, #16161e 0%, #231934 100%); }"
    ".card-title { font-size: 15px; color: #a0aec0; margin-bottom: 6px; }"
    ".card-value { font-size: 28px; font-weight: bold; }"
    ".green-text { color: #48bb78; }"
    ".red-text { color: #f56565; }"
    ".white-text { color: #ffffff; }"
    ".signal-box { background-color: #1a1a24; border-right: 4px solid #805ad5; padding: 15px; border-radius: 10px; margin-bottom: 12px; }"
    "</style>"
)
st.markdown(css_style, unsafe_allow_html=True)

SYMBOLS = [
    "XLM/USDT", "ZEC/USDT", "XRP/USDT", "HBAR/USDT", "ADA/USDT",
    "LTC/USDT", "BTC/USDT", "ETH/USDT", "PAXG/USDT", "XAU/USDT"
]

# اختيار الفريم: 1 ساعة أو 4 ساعات فقط
timeframe_map = {"فريم 1 ساعة (1H)": "1h", "فريم 4 ساعات (4H)": "4h"}
selected_tf_label = st.radio(
    "الإطار الزمني:",
    options=list(timeframe_map.keys()),
    horizontal=True,
    label_visibility="collapsed"
)
selected_tf = timeframe_map[selected_tf_label]

col_f1, col_f2 = st.columns(2)
with col_f1:
    filter_options = ["الكل"] + [s.replace("/USDT", "") for s in SYMBOLS]
    selected_coin = st.selectbox("تصفية حسب العملة:", filter_options)
with col_f2:
    trade_size_usd = st.number_input("حجم الصفقة ($):", min_value=10, max_value=100000, value=1000, step=100)

@st.cache_data(ttl=300)
def get_elliott_data(symbols_list, tf, capital_usd):
    exchange = ccxt.kucoin({'enableRateLimit': True})
    future_results = []
    past_trades = []
    
    # جلب بيانات تغطي 30 يوماً سابقة: (720 شمعة لـ 1h) أو (180 شمعة لـ 4h)
    limit_bars = 720 if tf == "1h" else 180

    for sym in symbols_list:
        try:
            fetch_sym = "PAXG/USDT" if sym == "XAU/USDT" else sym
            coin_name = sym.replace("/USDT", "")
            bars = exchange.fetch_ohlcv(fetch_sym, timeframe=tf, limit=limit_bars)
            if not bars:
                continue
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # 1. حساب الصفقات الفعلية المغلقة خلال الشهر السابق (30 يوماً)
            step = 24 if tf == "1h" else 6
            window = 48 if tf == "1h" else 18
            for i in range(0, len(df) - window, step):
                sub = df.iloc[i : i + window].reset_index(drop=True)
                w0 = sub['low'].iloc[:window//3].min()
                w1 = sub['high'].iloc[window//6 : (window*2)//3].max()
                if w1 > w0:
                    diff = w1 - w0
                    e2 = w1 - (diff * 0.618)
                    t5 = w0 + (diff * 1.618)
                    sl0 = w0
                    entered = False
                    for _, row in sub.iloc[(window*2)//3:].iterrows():
                        if not entered and row['low'] <= e2 <= row['high']:
                            entered = True
                        elif entered:
                            if row['low'] <= sl0:
                                pnl = capital_usd * ((sl0 - e2) / e2)
                                past_trades.append({"coin": coin_name, "pnl": pnl})
                                break
                            elif row['high'] >= t5:
                                pnl = capital_usd * ((t5 - e2) / e2)
                                past_trades.append({"coin": coin_name, "pnl": pnl})
                                break

            # 2. حساب التوصية المستقبلية الحالية
            recent = df.iloc[-30:]
            wave_0 = recent['low'].iloc[:15].min()
            wave_1 = recent['high'].iloc[15:].max()
            if wave_1 <= wave_0:
                wave_0 = recent['low'].min()
                wave_1 = recent['high'].max()

            diff = wave_1 - wave_0
            entry_2 = wave_1 - (diff * 0.618)
            target_5 = wave_0 + (diff * 1.618)
            stop_loss_0 = wave_0
            current_price = recent['close'].iloc[-1]

            distance_ratio = abs(current_price - entry_2) / current_price
            ai_score = max(65, min(99, int(99 - (distance_ratio * 160))))
            decimals = 2 if current_price > 10 else 4

            future_results.append({
                "coin": coin_name,
                "price": round(current_price, decimals),
                "entry": round(entry_2, decimals),
                "target": round(target_5, decimals),
                "sl": round(stop_loss_0, decimals),
                "ai": ai_score
            })
        except Exception:
            continue

    return pd.DataFrame(past_trades), pd.DataFrame(future_results)

with st.spinner(f"جاري تحليل بيانات {selected_tf_label} وآخر 30 يوماً..."):
    df_history, df_signals = get_elliott_data(SYMBOLS, selected_tf, trade_size_usd)

# تصفية البيانات حسب العملة المختارة
if selected_coin != "الكل":
    hist_df = df_history[df_history["coin"] == selected_coin] if not df_history.empty else pd.DataFrame()
    sig_df = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else pd.DataFrame()
else:
    hist_df = df_history
    sig_df = df_signals

st.markdown(f"### 📊 سجل الأداء الفعلي (آخر شهر سابق — {selected_tf_label})")

if not hist_df.empty:
    total_trades = len(hist_df)
    wins = hist_df[hist_df["pnl"] > 0]
    losses = hist_df[hist_df["pnl"] <= 0]
    win_trades = len(wins)
    loss_trades = len(losses)
    win_rate = round((win_trades / total_trades) * 100, 2)
    total_profit_usd = round(wins["pnl"].sum(), 2)
    total_loss_usd = round(abs(losses["pnl"].sum()), 2)
    net_profit_usd = round(total_profit_usd - total_loss_usd, 2)
else:
    total_trades, win_trades, loss_trades, win_rate = 0, 0, 0, 0.0
    total_profit_usd, total_loss_usd, net_profit_usd = 0.0, 0.0, 0.0

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>🤝 عدد الصفقات</div><div class='card-value white-text'>{total_trades}</div><div style='font-size:12px; color:#a0aec0;'>صفقات</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>🎯 نسبة النجاح</div><div class='card-value white-text'>{win_rate}%</div><div style='font-size:12px; color:#805ad5;'>معدل الأداء</div></div>", unsafe_allow_html=True)

col3, col4 = st.columns(2)
with col3:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title green-text'>📈 الصفقات الرابحة</div><div class='card-value white-text'>{win_trades}</div><div style='font-size:12px; color:#a0aec0;'>صفقات</div></div>", unsafe_allow_html=True)
with col4:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title red-text'>📉 الصفقات الخاسرة</div><div class='card-value white-text'>{loss_trades}</div><div style='font-size:12px; color:#a0aec0;'>صفقات</div></div>", unsafe_allow_html=True)

col5, col6 = st.columns(2)
with col5:
    st.markdown(f"<div class='metric-card card-green'><div class='card-title green-text'>💲 إجمالي الأرباح</div><div class='card-value white-text'>${total_profit_usd:,.2f}+</div><div style='font-size:12px; color:#a0aec0;'>USD</div></div>", unsafe_allow_html=True)
with col6:
    st.markdown(f"<div class='metric-card card-red'><div class='card-title red-text'>💲 إجمالي الخسائر</div><div class='card-value white-text'>${total_loss_usd:,.2f}-</div><div style='font-size:12px; color:#a0aec0;'>USD</div></div>", unsafe_allow_html=True)

net_color = "green-text" if net_profit_usd >= 0 else "red-text"
net_sign = "+" if net_profit_usd >= 0 else ""
st.markdown(f"<div class='metric-card card-net'><div class='card-title'>✨ صافي الأرباح الفعلية (آخر شهر)</div><div class='card-value {net_color}'>${net_profit_usd:,.2f}{net_sign} <span style='font-size:16px; color:#fff;'>USD</span></div></div>", unsafe_allow_html=True)

st.markdown(f"### 🤖 أعلى 5 توصيات مستقبلية تقييماً — ({selected_tf_label})")

if not sig_df.empty:
    # ترتيب التوصيات من الأعلى تقييماً وأخذ أفضل 5 توصيات فقط
    top_5_df = sig_df.sort_values(by="ai", ascending=False).head(5)
    for _, row in top_5_df.iterrows():
        card_html = (
            f"<div class='signal-box'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<span style='font-size:18px; font-weight:bold; color:#fff;'>🪙 {row['coin']}/USD <span style='font-size:13px; color:#a0aec0;'>(الحالي: ${row['price']})</span></span>"
            f"<span style='background-color:#805ad5; padding:3px 10px; border-radius:12px; font-size:13px;'>تقييم AI: {row['ai']}%</span>"
            f"</div>"
            f"<hr style='border-color:#2d3748; margin:10px 0;'>"
            f"<div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; font-size:14px;'>"
            f"<span>🔵 <b>الدخول (2):</b> ${row['entry']}</span>"
            f"<span class='green-text'>🟢 <b>الهدف (5):</b> ${row['target']}</span>"
            f"<span class='red-text'>🔴 <b>ستوب لوس (0):</b> ${row['sl']}</span>"
            f"</div></div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)
else:
