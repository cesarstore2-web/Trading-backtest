import streamlit as st
import pandas as pd
import numpy as np
import ccxt

st.set_page_config(page_title="لوحة التوصيات وموجات إليوت", layout="centered")

css_style = (
    "<style>"
    ".stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }"
    "div[role='radiogroup'] { display: flex; justify-content: space-around; flex-wrap: wrap; background-color: #1c1c24; padding: 6px; border-radius: 12px; margin-bottom: 15px; }"
    "div[role='radiogroup'] label { padding: 8px 16px; border-radius: 8px; color: #ffffff !important; }"
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

# ربط المدة الزمنية بالإطار الزمني وعدد الشموع الحقيقي
period_config = {
    "24 ساعة": {"tf": "15m", "limit": 96,  "window": 24},  # 96 شمعة × 15 دقيقة = 24 ساعة
    "أسبوع":   {"tf": "1h",  "limit": 168, "window": 36},  # 168 شمعة × 1 ساعة = 7 أيام
    "شهر":     {"tf": "4h",  "limit": 180, "window": 40}   # 180 شمعة × 4 ساعات = 30 يوم
}

selected_period = st.radio(
    "مدة الاختبار والتحليل:",
    options=list(period_config.keys()),
    horizontal=True,
    label_visibility="collapsed"
)

config = period_config[selected_period]
selected_tf = config["tf"]

filter_options = ["الكل"] + [s.replace("/USDT", "") for s in SYMBOLS]
selected_coin = st.selectbox("تصفية حسب العملة:", filter_options)

@st.cache_data(ttl=300)
def run_real_analysis_and_backtest(symbols_list, tf, limit, window):
    exchange = ccxt.binance({'enableRateLimit': True})
    signals_results = []
    backtest_trades = []
    trade_size_usd = 1000.0  # حجم الصفقة الافتراضي لحساب الأرباح بالدولار

    for sym in symbols_list:
        try:
            fetch_sym = "PAXG/USDT" if sym == "XAU/USDT" else sym
            bars = exchange.fetch_ohlcv(fetch_sym, timeframe=tf, limit=limit)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            coin_name = sym.replace("/USDT", "")

            # --- 1. الاختبار الرجعي الحقيقي (Backtest) على الفترة المحددة ---
            i = window
            while i < len(df) - 1:
                sub_df = df.iloc[i - window : i]
                mid = len(sub_df) // 2
                w0 = sub_df['low'].iloc[:mid].min()
                w1 = sub_df['high'].iloc[mid:].max()

                if w1 > w0:
                    diff = w1 - w0
                    entry = w1 - (diff * 0.618)
                    target = w0 + (diff * 1.618)
                    sl = w0

                    # تتبع الشموع التالية لمعرفة هل تفعلت الصفقة ونتيجتها
                    triggered = False
                    for j in range(i, len(df)):
                        low_p = df['low'].iloc[j]
                        high_p = df['high'].iloc[j]

                        if not triggered:
                            if low_p <= entry <= high_p:
                                triggered = True
                        else:
                            if low_p <= sl:
                                loss_pct = (sl - entry) / entry
                                backtest_trades.append({
                                    "coin": coin_name, "status": "loss",
                                    "pnl": trade_size_usd * loss_pct
                                })
                                i = j
                                break
                            elif high_p >= target:
                                win_pct = (target - entry) / entry
                                backtest_trades.append({
                                    "coin": coin_name, "status": "win",
                                    "pnl": trade_size_usd * win_pct
                                })
                                i = j
                                break
                i += max(1, window // 3)

            # --- 2. التوصيات المستقبلية الحالية بناءً على آخر شموع ---
            recent_df = df.iloc[-window:]
            mid_point = len(recent_df) // 2
            wave_0 = recent_df['low'].iloc[:mid_point].min()
            wave_1 = recent_df['high'].iloc[mid_point:].max()

            if wave_1 <= wave_0:
                wave_0 = recent_df['low'].min()
                wave_1 = recent_df['high'].max()

            diff = wave_1 - wave_0
            entry_2 = wave_1 - (diff * 0.618)
            target_5 = wave_0 + (diff * 1.618)
            stop_loss_0 = wave_0
            current_price = df['close'].iloc[-1]

            distance_ratio = abs(current_price - entry_2) / current_price
            ai_score = max(65, min(98, int(98 - (distance_ratio * 150))))
            decimals = 2 if current_price > 10 else 4

            signals_results.append({
                "coin": coin_name,
                "price": round(current_price, decimals),
                "entry": round(entry_2, decimals),
                "target": round(target_5, decimals),
                "sl": round(stop_loss_0, decimals),
                "ai": ai_score
            })
        except Exception:
            continue

    return pd.DataFrame(signals_results), pd.DataFrame(backtest_trades)

with st.spinner(f"جاري فحص بيانات السوق الحقيقية لآخر ({selected_period})..."):
    df_signals, df_trades = run_real_analysis_and_backtest(
        SYMBOLS, selected_tf, config["limit"], config["window"]
    )

# تصفية النتائج حسب العملة المختارة
if selected_coin != "الكل":
    display_signals = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else df_signals
    display_trades = df_trades[df_trades["coin"] == selected_coin] if not df_trades.empty else df_trades
else:
    display_signals = df_signals
    display_trades = df_trades

st.markdown(f"### 📊 النتائج الفعلية من السوق — آخر ({selected_period})")
st.caption(f"الإطار الزمني للتحليل: {selected_tf} | رأس مال الصفقة الافتراضي: $1,000")

# حساب الإحصائيات الحقيقية من الصفقات المكتملة
if not display_trades.empty:
    total_trades = len(display_trades)
    win_trades = len(display_trades[display_trades["status"] == "win"])
    loss_trades = len(display_trades[display_trades["status"] == "loss"])
    win_rate = round((win_trades / total_trades) * 100, 2)
    total_profit_usd = round(display_trades[display_trades["pnl"] > 0]["pnl"].sum(), 2)
    total_loss_usd = round(abs(display_trades[display_trades["pnl"] < 0]["pnl"].sum()), 2)
    net_profit_usd = round(total_profit_usd - total_loss_usd, 2)
else:
    total_trades = win_trades = loss_trades = 0
    win_rate = total_profit_usd = total_loss_usd = net_profit_usd = 0.0

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>🤝 الصفقات المكتملة</div><div class='card-value white-text'>{total_trades}</div><div style='font-size:12px; color:#a0aec0;'>خلال {selected_period}</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>🎯 نسبة النجاح الحقيقية</div><div class='card-value white-text'>{win_rate}%</div><div style='font-size:12px; color:#805ad5;'>معدل الأداء</div></div>", unsafe_allow_html=True)

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
st.markdown(f"<div class='metric-card card-net'><div class='card-title'>✨ صافي الأرباح الفعلية ({selected_period})</div><div class='card-value {net_color}'>${net_profit_usd:,.2f}{net_sign} <span style='font-size:16px; color:#fff;'>USD</span></div></div>", unsafe_allow_html=True)

st.markdown(f"### 🤖 التوصيات المستقبلية الحالية — إطار ({selected_tf})")

if not display_signals.empty:
    sorted_df = display_signals.sort_values(by="ai", ascending=False)
    for _, row in sorted_df.iterrows():
        card_html = (
            f"<div class='signal-box'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
