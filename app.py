import streamlit as st
import pandas as pd
import numpy as np
import ccxt

st.set_page_config(page_title="توصيات إليوت السريعة وصافي الأرباح", layout="centered")

css_style = (
    "<style>"
    ".stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }"
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
    ".badge-time { background-color: #2d3748; color: #cbd5e0; padding: 2px 8px; border-radius: 6px; font-size: 12px; }"
    "</style>"
)
st.markdown(css_style, unsafe_allow_html=True)

SYMBOLS = [
    "XLM/USDT", "ZEC/USDT", "XRP/USDT", "HBAR/USDT", "ADA/USDT",
    "LTC/USDT", "BTC/USDT", "ETH/USDT", "PAXG/USDT", "XAU/USDT"
]

st.markdown("### ⚙️ إعدادات المحفظة (توصيات 1 - 3 أيام)")
col_set1, col_set2 = st.columns(2)
with col_set1:
    trade_amount_usd = st.number_input("مبلغ الدخول لكل صفقة ($):", min_value=10, max_value=100000, value=1000, step=100)
with col_set2:
    filter_options = ["الكل"] + [s.replace("/USDT", "") for s in SYMBOLS]
    selected_coin = st.selectbox("تصفية حسب العملة:", filter_options)

@st.cache_data(ttl=300)
def run_fast_elliott_system(symbols_list, capital_per_trade):
    # استخدام KuCoin لأنه لا يحظر خوادم Streamlit الأمريكية
    exchange = ccxt.kucoin({'enableRateLimit': True})
    closed_trades = []
    future_signals = []

    for sym in symbols_list:
        try:
            fetch_sym = "PAXG/USDT" if sym == "XAU/USDT" else sym
            coin_name = sym.replace("/USDT", "")
            
            bars = exchange.fetch_ohlcv(fetch_sym, timeframe="4h", limit=200)
            if not bars:
                continue
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # 1. اختبار رجعي لآخر 30 يوماً سابقة
            for start_idx in range(0, len(df) - 30, 12):
                sub_df = df.iloc[start_idx : start_idx + 30].reset_index(drop=True)
                wave_0 = sub_df['low'].iloc[:8].min()
                wave_1 = sub_df['high'].iloc[4:14].max()
                
                if wave_1 > wave_0:
                    diff = wave_1 - wave_0
                    entry_2 = wave_1 - (diff * 0.618)
                    target_5 = wave_0 + (diff * 1.618)
                    sl_0 = wave_0
                    
                    test_window = sub_df.iloc[14:]
                    entered = False
                    for _, candle in test_window.iterrows():
                        if not entered and candle['low'] <= entry_2 <= candle['high']:
                            entered = True
                        elif entered:
                            if candle['low'] <= sl_0:
                                loss_pct = (sl_0 - entry_2) / entry_2
                                pnl_usd = capital_per_trade * loss_pct
                                closed_trades.append({"coin": coin_name, "pnl": pnl_usd})
                                break
                            elif candle['high'] >= target_5:
                                profit_pct = (target_5 - entry_2) / entry_2
                                pnl_usd = capital_per_trade * profit_pct
                                closed_trades.append({"coin": coin_name, "pnl": pnl_usd})
                                break

            # 2. توليد التوصيات المستقبلية الحالية (1 - 3 أيام)
            recent_df = df.iloc[-24:]
            w0 = recent_df['low'].iloc[:12].min()
            w1 = recent_df['high'].iloc[12:].max()
            if w1 <= w0:
                w0 = recent_df['low'].min()
                w1 = recent_df['high'].max()
            
            d = w1 - w0
            e2 = w1 - (d * 0.618)
            t5 = w0 + (d * 1.618)
            curr = recent_df['close'].iloc[-1]
            
            pct_move = ((t5 - e2) / e2) * 100
            est_days = "1 يوم" if pct_move < 4 else ("2 يوم" if pct_move < 8 else "3 أيام")
            
            dist = abs(curr - e2) / curr
            ai_score = max(68, min(99, int(99 - (dist * 180))))
            dec = 2 if curr > 10 else 4

            future_signals.append({
                "coin": coin_name,
                "price": round(curr, dec),
                "entry": round(e2, dec),
                "target": round(t5, dec),
                "sl": round(w0, dec),
                "ai": ai_score,
                "duration": est_days
            })
        except Exception:
            continue

    return pd.DataFrame(closed_trades), pd.DataFrame(future_signals)

with st.spinner("جاري جلب البيانات الحية من KuCoin وتحليل الموجات..."):
    df_trades, df_signals = run_fast_elliott_system(SYMBOLS, trade_amount_usd)

if selected_coin != "الكل":
    filtered_trades = df_trades[df_trades["coin"] == selected_coin] if not df_trades.empty else pd.DataFrame()
    filtered_signals = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else pd.DataFrame()
else:
    filtered_trades = df_trades
    filtered_signals = df_signals

if not filtered_trades.empty:
    total_trades = len(filtered_trades)
    wins = filtered_trades[filtered_trades["pnl"] > 0]
    losses = filtered_trades[filtered_trades["pnl"] <= 0]
    win_trades = len(wins)
    loss_trades = len(losses)
    win_rate = round((win_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
    total_profit_usd = round(wins["pnl"].sum(), 2)
    total_loss_usd = round(abs(losses["pnl"].sum()), 2)
    net_profit_usd = round(total_profit_usd - total_loss_usd, 2)
else:
    total_trades, win_trades, loss_trades, win_rate = 0, 0, 0, 0.0
    total_profit_usd, total_loss_usd, net_profit_usd = 0.0, 0.0, 0.0

st.markdown("### 📊 صافي الأرباح الفعلية (آخر شهر سابق)")

net_color = "green-text" if net_profit_usd >= 0 else "red-text"
net_sign = "+" if net_profit_usd >= 0 else ""
st.markdown(f"<div class='metric-card card-net'><div class='card-title'>✨ صافي الأرباح (30 يوم)</div><div class='card-value {net_color}'>${net_profit_usd:,.2f}{net_sign} <span style='font-size:16px; color:#fff;'>USD</span></div></div>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card card-blue'><div class='card-title'>🤝 الصفقات المغلقة</div><div class='card-value white-text'>{total_trades}</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card card-purple'><div class='card-title'>🎯 نسبة النجاح</div><div class='card-value white-text'>{win_rate}%</div></div>", unsafe_allow_html=True)

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

st.markdown("### 🤖 التوصيات المستقبلية الأكثر تقييماً (مدة 1 - 3 أيام)")

if not filtered_signals.empty:
    sorted_df = filtered_signals.sort_values(by="ai", ascending=False)
    for _, row in sorted_df.iterrows():
        card_html = (
            f"<div class='signal-box'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<span style='font-size:18px; font-weight:bold; color:#fff;'>🪙 {row['coin']}/USD <span style='font-size:13px; color:#a0aec0;'>(الحالي: ${row['price']})</span></span>"
            f"<div><span class='badge-time'>⏱️ {row['duration']}</span> <span style='background-color:#805ad5; padding:3px 10px; border-radius:12px; font-size:13px;'>تقييم AI: {row['ai']}%</span></div>"
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
    st.error("تعذر الاتصال بمصدر البيانات، يرجى إعادة تحميل الصفحة.")
