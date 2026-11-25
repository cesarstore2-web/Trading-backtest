import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time

# إعدادات الصفحة
st.set_page_config(page_title="CRYPTO SCALPING AI | ALL-IN-ONE", layout="centered")

# تصميم النيون الداكن (Cyberpunk UI)
st.markdown("""
<style>
    .stApp {
        background-color: #0b0e14;
        color: #ffffff;
        font-family: 'Courier New', Courier, monospace;
    }
    .header-box {
        border: 2px solid #00ffcc;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        background: linear-gradient(90deg, #0d1b2a 0%, #1b263b 100%);
        box-shadow: 0 0 15px rgba(0, 255, 204, 0.3);
        margin-bottom: 20px;
    }
    .scan-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
        margin-bottom: 25px;
        background-color: #131926;
        border: 1px solid #00ffcc;
        box-shadow: 0 0 15px rgba(0, 255, 204, 0.15);
    }
    .scan-table th {
        background-color: #0d1b2a;
        color: #00ffcc;
        padding: 12px 8px;
        border-bottom: 2px solid #00ffcc;
        font-size: 13px;
        text-align: center;
    }
    .scan-table td {
        padding: 10px 8px;
        border-bottom: 1px solid #233044;
        text-align: center;
        font-weight: bold;
        font-size: 13px;
    }
    .badge-buy {
        color: #00ff66;
        background-color: rgba(0, 255, 102, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid #00ff66;
        text-shadow: 0 0 8px #00ff66;
    }
    .badge-sell {
        color: #ff0055;
        background-color: rgba(255, 0, 85, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid #ff0055;
        text-shadow: 0 0 8px #ff0055;
    }
    .badge-wait {
        color: #ffcc00;
        background-color: rgba(255, 204, 0, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid #ffcc00;
    }
    .signal-box-buy {
        border: 2px solid #00ff66;
        border-radius: 12px;
        padding: 25px;
        text-align: center;
        background-color: rgba(0, 255, 102, 0.08);
        box-shadow: 0 0 25px rgba(0, 255, 102, 0.4);
        margin: 20px 0;
    }
    .signal-box-sell {
        border: 2px solid #ff0055;
        border-radius: 12px;
        padding: 25px;
        text-align: center;
        background-color: rgba(255, 0, 85, 0.08);
        box-shadow: 0 0 25px rgba(255, 0, 85, 0.4);
        margin: 20px 0;
    }
    .signal-box-scan {
        border: 2px solid #ffcc00;
        border-radius: 12px;
        padding: 25px;
        text-align: center;
        background-color: rgba(255, 204, 0, 0.08);
        box-shadow: 0 0 25px rgba(255, 204, 0, 0.3);
        margin: 20px 0;
    }
    .big-text-buy {
        font-size: 60px;
        font-weight: bold;
        color: #00ff66;
        text-shadow: 0 0 20px #00ff66;
        margin: 0;
    }
    .big-text-sell {
        font-size: 60px;
        font-weight: bold;
        color: #ff0055;
        text-shadow: 0 0 20px #ff0055;
        margin: 0;
    }
    .big-text-scan {
        font-size: 45px;
        font-weight: bold;
        color: #ffcc00;
        text-shadow: 0 0 20px #ffcc00;
        margin: 0;
    }
    .targets-box {
        display: flex;
        justify-content: space-around;
        margin-top: 15px;
        padding-top: 15px;
        border-top: 1px dashed rgba(255,255,255,0.2);
        font-size: 15px;
        font-weight: bold;
    }
    .confluence-row {
        display: flex;
        justify-content: space-between;
        background-color: #131926;
        border: 1px solid #233044;
        padding: 10px 15px;
        border-radius: 6px;
        margin-bottom: 8px;
        font-weight: bold;
    }
    .pass-badge {
        color: #00ff66;
        background-color: rgba(0, 255, 102, 0.15);
        padding: 2px 10px;
        border-radius: 4px;
        border: 1px solid #00ff66;
    }
    .fail-badge {
        color: #ff0055;
        background-color: rgba(255, 0, 85, 0.15);
        padding: 2px 10px;
        border-radius: 4px;
        border: 1px solid #ff0055;
    }
    .perf-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .perf-card {
        background-color: #131926;
        border: 1px solid #00ffcc;
        border-radius: 8px;
        padding: 12px 8px;
        text-align: center;
        box-shadow: 0 0 10px rgba(0, 255, 204, 0.15);
    }
    .perf-title {
        font-size: 11px;
        color: #a0aec0;
        margin-bottom: 5px;
    }
    .perf-val {
        font-size: 18px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# الهيدر العلوي
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; color:#00ffcc;">⚡ CRYPTO SCALPING AI | LIVE RADAR ⚡</h2>
    <p style="margin:5px 0 0 0; color:#a0aec0; font-size:13px;">مسح شامل فوري للعملات التسع + فريمات 1m / 3m / 5m / 15m</p>
</div>
""", unsafe_allow_html=True)

# قائمة العملات التسع
pairs = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "XRPUSDT": "XRP-USD",
    "ADAUSDT": "ADA-USD",
    "XLMUSDT": "XLM-USD",
    "HBARUSDT": "HBAR-USD",
    "LTCUSDT": "LTC-USD",
    "ZECUSDT": "ZEC-USD",
    "PAXGUSDT": "PAXG-USD"
}

pair_options = ["🌐 ALL COINS (مسح شامل)"] + list(pairs.keys())
timeframe_options = ["1m", "3m", "5m", "15m"]

col1, col2, col3 = st.columns([2.0, 1.1, 1.4])
with col1:
    selected_mode = st.selectbox("PAIR:", pair_options, index=0, label_visibility="collapsed")
with col2:
    selected_tf = st.selectbox("TIMEFRAME:", timeframe_options, index=1, label_visibility="collapsed")
with col3:
    refresh_btn = st.button("🔄 REFRESH SCAN", use_container_width=True, type="primary")
# تنسيق الأسعار
def format_price(price):
    if price < 1:
        return f"{price:.5f}"
    elif price < 50:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"

# جلب البيانات (مع بناء فريم 3m من شموع 1m لضمان الدقة)
def fetch_scalp_data(ticker, interval):
    if interval == "3m":
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        df_3m = df.resample('3min').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        return df_3m
    else:
        period = "1d" if interval == "1m" else "5d"
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()

# تحليل عملة واحدة
def analyze_coin(df):
    df['EMA9'] = ta.trend.ema_indicator(df['Close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['Close'], window=21)
    df['EMA50'] = ta.trend.ema_indicator(df['Close'], window=50)
    df['RSI7'] = ta.momentum.rsi(df['Close'], window=7)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    df = df.dropna()

    if len(df) < 20:
        return None

    last = df.iloc[-2]
    curr = df.iloc[-1]
    price = curr['Close']
    atr = last['ATR']

    c1 = last['EMA9'] > last['EMA21']
    c2 = price > last['EMA50']
    c3 = last['RSI7'] > 50
    c4 = last['Close'] > last['Open']
    c5 = last['ATR'] >= df['ATR'].tail(15).mean() * 0.9
    c6 = 25 < last['RSI7'] < 75

    conditions = [
        ("1. FAST CROSS (EMA 9/21)", c1),
        ("2. MICRO TREND (EMA 50)", c2),
        ("3. SCALP MOMENTUM (RSI 7)", c3),
        ("4. CANDLE BODY DIRECTION", c4),
        ("5. LIQUIDITY / VOLATILITY", c5),
        ("6. EXHAUSTION FILTER", c6)
    ]

    bull_score = sum([1 for _, st_val in conditions if st_val])
    bear_score = 6 - bull_score

    if bull_score >= 4:
        decision = "BUY"
        conf = int((bull_score / 6) * 100)
        sl = price - (1.2 * atr)
        tp = price + (2.0 * atr)
    elif bear_score >= 4:
        decision = "SELL"
        conf = int((bear_score / 6) * 100)
        sl = price + (1.2 * atr)
        tp = price - (2.0 * atr)
    else:
        decision = "WAIT"
        conf = 50
        sl = 0.0
        tp = 0.0

    return {
        "df": df,
        "price": price,
        "decision": decision,
        "conf": conf,
        "sl": sl,
        "tp": tp,
        "conditions": conditions
    }

# محاكاة أداء 24 ساعة
def run_backtest(df, interval, trade_size=100.0, fee_rate=0.001):
    candles_map = {"1m": 1440, "3m": 480, "5m": 288, "15m": 96}
    lookback = min(candles_map.get(interval, 480), len(df) - 20)
    if lookback <= 10:
        return 0, 0, 0.0, 0.0

    start_idx = len(df) - lookback
    wins, losses, net_profit = 0, 0, 0.0
    in_trade, trade_type = False, ""
    entry_p, sl_p, tp_p = 0.0, 0.0, 0.0

    for i in range(start_idx, len(df) - 1):
        row = df.iloc[i]
        if in_trade:
            if trade_type == "BUY":
                if row['Low'] <= sl_p:
                    losses += 1
                    net_profit += (-trade_size * ((entry_p - sl_p) / entry_p)) - (trade_size * fee_rate * 2)
                    in_trade = False
                elif row['High'] >= tp_p:
                    wins += 1
                    net_profit += (trade_size * ((tp_p - entry_p) / entry_p)) - (trade_size * fee_rate * 2)
                    in_trade = False
            elif trade_type == "SELL":
                if row['High'] >= sl_p:
                    losses += 1
                    net_profit += (-trade_size * ((sl_p - entry_p) / entry_p)) - (trade_size * fee_rate * 2)
                    in_trade = False
                elif row['Low'] <= tp_p:
                    wins += 1
                    net_profit += (trade_size * ((entry_p - tp_p) / entry_p)) - (trade_size * fee_rate * 2)
                    in_trade = False
            continue

        atr_mean = df['ATR'].iloc[i-15:i].mean()
        c1 = row['EMA9'] > row['EMA21']
        c2 = row['Close'] > row['EMA50']
        c3 = row['RSI7'] > 50
        c4 = row['Close'] > row['Open']
        c5 = row['ATR'] >= atr_mean * 0.9
        c6 = 25 < row['RSI7'] < 75

        bull = sum([c1, c2, c3, c4, c5, c6])
        bear = 6 - bull
        if bull >= 4:
            in_trade, trade_type = True, "BUY"
            entry_p = row['Close']
            sl_p = entry_p - (1.2 * row['ATR'])
            tp_p = entry_p + (2.0 * row['ATR'])
        elif bear >= 4:
            in_trade, trade_type = True, "SELL"
            entry_p = row['Close']
            sl_p = entry_p + (1.2 * row['ATR'])
            tp_p = entry_p - (2.0 * row['ATR'])

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    return wins, losses, win_rate, net_profit

# الوضع الافتراضي: مسح شامل لكل العملات التسع
if selected_mode == "🌐 ALL COINS (مسح شامل)":
    st.markdown(f"<h4 style='color:#00ffcc; margin-bottom:5px;'>📡 LIVE MULTI-COIN RADAR ({selected_tf.upper()})</h4>", unsafe_allow_html=True)
    
    progress_bar = st.progress(0)
    rows_html = ""
    total_wins, total_losses, total_net = 0, 0, 0.0

    for idx, (coin_name, ticker) in enumerate(pairs.items()):
        df = fetch_scalp_data(ticker, selected_tf)
        res = analyze_coin(df)
        
        if res:
            w, l, wr, net = run_backtest(res['df'], selected_tf)
            total_wins += w
            total_losses += l
            total_net += net

            dec = res['decision']
            if dec == "BUY":
                badge = f'<span class="badge-buy">BUY ({res["conf"]}%)</span>'
                sl_str = format_price(res['sl'])
                tp_str = format_price(res['tp'])
            elif dec == "SELL":
                badge = f'<span class="badge-sell">SELL ({res["conf"]}%)</span>'
                sl_str = format_price(res['sl'])
                tp_str = format_price(res['tp'])
            else:
                badge = '<span class="badge-wait">WAIT</span>'
                sl_str = "-"
                tp_str = "-"

            net_color = "#00ff66" if net >= 0 else "#ff0055"
            rows_html += f"""
            <tr>
                <td style="color:#00ffcc;">{coin_name}</td>
                <td>{format_price(res['price'])}</td>
                <td>{badge}</td>
                <td style="color:#ff0055;">{sl_str}</td>
                <td style="color:#00ff66;">{tp_str}</td>
                <td style="color:{net_color};">${net:+.2f}</td>
            </tr>
            """
        progress_bar.progress((idx + 1) / len(pairs))
    
    progress_bar.empty()

    overall_wr = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0.0
    net_col = "#00ff66" if total_net >= 0 else "#ff0055"

    st.markdown(f"""
    <div class="perf-grid">
        <div class="perf-card">
            <div class="perf-title">TOTAL WINS (24H)</div>
            <div class="perf-val" style="color:#00ff66;">{total_wins} 🟢</div>
        </div>
        <div class="perf-card">
            <div class="perf-title">TOTAL LOSSES (24H)</div>
            <div class="perf-val" style="color:#ff0055;">{total_losses} 🔴</div>
        </div>
        <div class="perf-card">
            <div class="perf-title">AVG WIN RATE</div>
            <div class="perf-val" style="color:#00ffcc;">{overall_wr:.1f}%</div>
        </div>
        <div class="perf-card">
            <div class="perf-title">PORTFOLIO NET</div>
            <div class="perf-val" style="color:{net_col};">${total_net:+.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <table class="scan-table">
        <thead>
            <tr>
                <th>PAIR</th>
                <th>PRICE</th>
                <th>SIGNAL</th>
                <th>SL</th>
                <th>TP</th>
                <th>24H PNL</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    """, unsafe_allow_html=True)

# وضع تحليل عملة واحدة بالتفصيل
else:
    df = fetch_scalp_data(pairs[selected_mode], selected_tf)
    res = analyze_coin(df)

    if res:
        wins, losses, win_rate, net_profit = run_backtest(res['df'], selected_tf)
        dec = res['decision']
        price = res['price']

        if dec == "BUY":
            box_class, text_class = "signal-box-buy", "big-text-buy"
            targets_html = f"""
            <div class="targets-box">
                <span style="color:#00ffcc;">ENTRY: {format_price(price)}</span>
                <span style="color:#ff0055;">SL: {format_price(res['sl'])}</span>
                <span style="color:#00ff66;">TP: {format_price(res['tp'])}</span>
            </div>"""
        elif dec == "SELL":
            box_class, text_class = "signal-box-sell", "big-text-sell"
            targets_html = f"""
            <div class="targets-box">
                <span style="color:#00ffcc;">ENTRY: {format_price(price)}</span>
                <span style="color:#ff0055;">SL: {format_price(res['sl'])}</span>
                <span style="color:#00ff66;">TP: {format_price(res['tp'])}</span>
            </div>"""
        else:
            box_class, text_class = "signal-box-scan", "big-text-scan"
            targets_html = f"""
            <div class="targets-box">
                <span style="color:#ffcc00;">PRICE: {format_price(price)} (CHOPPY MARKET - WAIT)</span>
            </div>"""

        profit_color = "#00ff66" if net_profit >= 0 else "#ff0055"

        st.markdown(f"""
        <div class="{box_class}">
