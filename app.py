import streamlit as st
import pandas as pd
import numpy as np
import ccxt

st.set_page_config(page_title="Tricks HeLaL V 0.01 — Backtest", layout="centered")

css_style = """
<style>
.stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }
div[role='radiogroup'] { display: flex; justify-content: space-around; flex-wrap: wrap; background-color: #1c1c24; padding: 6px; border-radius: 12px; margin-bottom: 15px; }
div[role='radiogroup'] label { padding: 8px 16px; border-radius: 8px; color: #ffffff !important; }
.metric-card { border-radius: 15px; padding: 18px; text-align: center; background-color: #16161e; margin-bottom: 15px; }
.card-blue { border: 1.5px solid #2b6cb0; }
.card-purple { border: 1.5px solid #805ad5; }
.card-green { border: 1.5px solid #38a169; }
.card-red { border: 1.5px solid #e53e3e; }
.card-net { border: 1.5px solid #805ad5; background: linear-gradient(90deg, #16161e 0%, #231934 100%); }
.card-title { font-size: 15px; color: #a0aec0; margin-bottom: 6px; }
.card-value { font-size: 28px; font-weight: bold; }
.green-text { color: #48bb78; }
.red-text { color: #f56565; }
.white-text { color: #ffffff; }
.signal-box-buy { background-color: #1a1a24; border-right: 4px solid #03ff85; padding: 15px; border-radius: 10px; margin-bottom: 12px; }
.signal-box-sell { background-color: #1a1a24; border-right: 4px solid #fc0808; padding: 15px; border-radius: 10px; margin-bottom: 12px; }
</style>
"""
st.markdown(css_style, unsafe_allow_html=True)

SYMBOLS = [
    "XLM/USDT", "ZEC/USDT", "XRP/USDT", "HBAR/USDT", "ADA/USDT",
    "LTC/USDT", "BTC/USDT", "ETH/USDT", "PAXG/USDT", "XAU/USDT"
]

period_config = {
    "24 ساعة": {"tf": "5m",  "limit": 288},
    "أسبوع":   {"tf": "15m", "limit": 672},
    "شهر":     {"tf": "15m", "limit": 1000}
}

selected_period = st.radio(
    "مدة الاختبار والتحليل:",
    options=list(period_config.keys()),
    horizontal=True,
    label_visibility="collapsed"
)

config = period_config[selected_period]
selected_tf = config["tf"]

# نافذتان لتعديل ATR SL و R:R + تصفية العملة
c_set1, c_set2, c_set3 = st.columns(3)
with c_set1:
    atr_mult = st.number_input("مضاعف ATR SL:", min_value=0.1, max_value=10.0, value=1.5, step=0.1)
with c_set2:
    rr_ratio = st.number_input("نسبة R : R :", min_value=0.5, max_value=15.0, value=2.0, step=0.1)
with c_set3:
    filter_options = ["الكل"] + [s.replace("/USDT", "") for s in SYMBOLS]
    selected_coin = st.selectbox("العملة:", filter_options)

@st.cache_data(ttl=300)
def fetch_market_data(symbols_list, tf, limit):
    exchange = ccxt.binance({'enableRateLimit': True})
    try:
        markets = exchange.load_markets()
    except Exception:
        markets = {}

    data_dict = {}
    for sym in symbols_list:
        try:
            fetch_sym = "PAXG/USDT" if sym == "XAU/USDT" else sym
            bars = exchange.fetch_ohlcv(fetch_sym, timeframe=tf, limit=limit)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # استخراج mintick الحقيقي للعملة مثل TradingView
            tick_size = 0.0001
            if fetch_sym in markets:
                prec = markets[fetch_sym].get('precision', {}).get('price')
                if isinstance(prec, float) and prec > 0:
                    tick_size = prec
                elif isinstance(prec, int) and prec >= 0:
                    tick_size = 10 ** (-prec)

            data_dict[sym.replace("/USDT", "")] = {"df": df, "tick": tick_size}
        except Exception:
            continue
    return data_dict

def run_tricks_helal_strategy(data_dict, atr_mult, rr_ratio, depth=30, backstep=30, deviation=5, min_bars=8):
    signals_results = []
    backtest_trades = []
    trade_size_usd = 1000.0

    for coin_name, item in data_dict.items():
        df = item["df"].copy()
        tick_size = item["tick"]

        if len(df) < depth + backstep + 5:
            continue

        # حساب ATR 14
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - prev_close).abs(),
            (df['low'] - prev_close).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean().bfill()

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        atrs = df['atr'].values

        min_dist = deviation * tick_size
        last_pivot_price = None
        last_dir = 0
        last_signal_bar = None
        confirmed_signals = []

        # مطابقة منطق ta.pivothigh / ta.pivotlow في Pine Script حرفياً
        for bar_index in range(depth + backstep, len(df)):
            piv_idx = bar_index - backstep
            cand_h = highs[piv_idx]
            cand_l = lows[piv_idx]

            # فحص Pivot High (left=depth, right=backstep)
            left_h = highs[piv_idx - depth : piv_idx]
            right_h = highs[piv_idx + 1 : piv_idx + backstep + 1]
            is_ph = (cand_h >= np.max(left_h)) and (cand_h > np.max(right_h))

            # فحص Pivot Low (left=depth, right=backstep)
            left_l = lows[piv_idx - depth : piv_idx]
            right_l = lows[piv_idx + 1 : piv_idx + backstep + 1]
            is_pl = (cand_l <= np.min(left_l)) and (cand_l < np.min(right_l))

            if is_ph or is_pl:
                # منطق Pine Script: isSell = newSell and (not newBuy or na(pl) or ph >= pl)
                is_sell = is_ph and (not is_pl or cand_h >= cand_l)
                price_at_sig = cand_h if is_sell else cand_l

                pass_dev = (last_pivot_price is None) or (abs(price_at_sig - last_pivot_price) >= min_dist)
                pass_spacing = (last_signal_bar is None) or ((bar_index - last_signal_bar) >= min_bars)

                if pass_dev and pass_spacing and ((is_sell and last_dir != 1) or (not is_sell and last_dir != -1)):
                    last_dir = 1 if is_sell else -1
                    last_pivot_price = price_at_sig
                    last_signal_bar = bar_index
                    confirmed_signals.append((bar_index, "SELL" if is_sell else "BUY"))
        # فحص الصفقات الحقيقية عند إغلاق الشمعة التي تأكدت فيها الإشارة (bar_index)
        active_until = -1
        for sig_idx, side in confirmed_signals:
            if sig_idx <= active_until:
                continue

            entry_price = closes[sig_idx]
            atr_val = atrs[sig_idx]
            sl_dist = atr_val * atr_mult

            if side == "BUY":
                sl_price = entry_price - sl_dist
                tp_price = entry_price + (sl_dist * rr_ratio)
            else:
                sl_price = entry_price + sl_dist
                tp_price = entry_price - (sl_dist * rr_ratio)

            for j in range(sig_idx + 1, len(df)):
                if side == "BUY":
                    if lows[j] <= sl_price:
                        pnl = trade_size_usd * ((sl_price - entry_price) / entry_price)
                        backtest_trades.append({"coin": coin_name, "side": "BUY", "status": "loss", "pnl": pnl})
                        active_until = j
                        break
                    elif highs[j] >= tp_price:
                        pnl = trade_size_usd * ((tp_price - entry_price) / entry_price)
                        backtest_trades.append({"coin": coin_name, "side": "BUY", "status": "win", "pnl": pnl})
                        active_until = j
                        break
                else:
                    if highs[j] >= sl_price:
                        pnl = trade_size_usd * ((entry_price - sl_price) / entry_price)
                        backtest_trades.append({"coin": coin_name, "side": "SELL", "status": "loss", "pnl": pnl})
                        active_until = j
                        break
                    elif lows[j] <= tp_price:
                        pnl = trade_size_usd * ((entry_price - tp_price) / entry_price)
                        backtest_trades.append({"coin": coin_name, "side": "SELL", "status": "win", "pnl": pnl})
                        active_until = j
                        break

        # استخراج أحدث إشارة مؤكدة لكل عملة
        if confirmed_signals:
            last_idx, last_side = confirmed_signals[-1]
            entry_p = closes[last_idx]
            sl_d = atrs[last_idx] * atr_mult
            if last_side == "BUY":
                sl_p = entry_p - sl_d
                tp_p = entry_p + (sl_d * rr_ratio)
            else:
                sl_p = entry_p + sl_d
                tp_p = entry_p - (sl_d * rr_ratio)

            curr_p = closes[-1]
            bars_ago = (len(df) - 1) - last_idx
            ai_score = max(65, min(98, int(98 - (bars_ago * 1.2))))
            dec = 2 if curr_p > 10 else 4

            signals_results.append({
                "coin": coin_name,
                "side": "شراء (Buy-point)" if last_side == "BUY" else "بيع (Sell-point)",
                "is_buy": last_side == "BUY",
                "price": round(curr_p, dec),
                "entry": round(entry_p, dec),
                "target": round(tp_p, dec),
                "sl": round(sl_p, dec),
                "bars_ago": bars_ago,
                "ai": ai_score
            })

    return pd.DataFrame(signals_results), pd.DataFrame(backtest_trades)

with st.spinner(f"جاري فحص إشارات Tricks HeLaL لآخر ({selected_period})..."):
    market_data = fetch_market_data(SYMBOLS, selected_tf, config["limit"])
    df_signals, df_trades = run_tricks_helal_strategy(
        market_data, atr_mult, rr_ratio, depth=30, backstep=30, deviation=5, min_bars=8
    )

if selected_coin != "الكل":
    display_signals = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else df_signals
    display_trades = df_trades[df_trades["coin"] == selected_coin] if not df_trades.empty else df_trades
else:
    display_signals = df_signals
    display_trades = df_trades

st.markdown(f"### 📊 نتائج Tricks HeLaL الفعلية — آخر ({selected_period})")
st.caption(f"الفريم: {selected_tf} | Depth: 30 | Backstep: 30 | Dev: 5 | ATR SL: {atr_mult}x | R:R: 1:{rr_ratio}")

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

st.markdown(f"### 🤖 أحدث إشارات Tricks HeLaL المؤكدة — إطار ({selected_tf})")

if not display_signals.empty:
    for _, row in display_signals.sort_values(by="bars_ago", ascending=True).iterrows():
        box_cls = "signal-box-buy" if row["is_buy"] else "signal-box-sell"
        badge_bg = "#38a169" if row["is_buy"] else "#e53e3e"
        st.markdown(f"<div class='{box_cls}'><div style='display:flex; justify-content:space-between; align-items:center;'><span style='font-size:18px; font-weight:bold; color:#fff;'>🪙 {row['coin']}/USD <span style='font-size:13px; color:#a0aec0;'>(الحالي: ${row['price']})</span></span><span style='background-color:{badge_bg}; padding:3px 10px; border-radius:12px; font-size:13px;'>{row['side']} | منذ {row['bars_ago']} شمعة</span></div><hr style='border-color:#2d3748; margin:10px 0;'><div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; font-size:14px;'><span>🔵 <b>الدخول (إغلاق):</b> ${row['entry']}</span><span class='green-text'>🟢 <b>الهدف (TP):</b> ${row['target']}</span><span class='red-text'>🔴 <b>ستوب لوس (SL):</b> ${row['sl']}</span></div></div>", unsafe_allow_html=True)
else:
    st.warning("لا توجد إشارات مؤكدة حالياً ضمن هذه النافذة.")
