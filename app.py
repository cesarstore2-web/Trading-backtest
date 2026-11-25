import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time

# إعدادات الصفحة
st.set_page_config(page_title="CRYPTO SCALPING AI | LIVE & 24H STATS", layout="centered")

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
        font-size: 65px;
        font-weight: bold;
        color: #00ff66;
        text-shadow: 0 0 20px #00ff66;
        margin: 0;
    }
    .big-text-sell {
        font-size: 65px;
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
        font-size: 16px;
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
        font-size: 12px;
        color: #a0aec0;
        margin-bottom: 5px;
    }
    .perf-val {
        font-size: 20px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# الهيدر العلوي
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; color:#00ffcc;">⚡ CRYPTO SCALPING AI | LIVE & 24H STATS ⚡</h2>
    <p style="margin:5px 0 0 0; color:#a0aec0; font-size:14px;">خوارزمية المضاربة السريعة + محاكاة حقيقية لآخر 24 ساعة</p>
</div>
""", unsafe_allow_html=True)

# قائمة العملات التسع المطلوبة
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

# شريط التحكم
col1, col2, col3 = st.columns([1.8, 1.3, 1.4])
with col1:
    selected_pair = st.selectbox("PAIR:", list(pairs.keys()), label_visibility="collapsed")
with col2:
    selected_tf = st.selectbox("TIMEFRAME:", ["5m", "15m"], label_visibility="collapsed")
with col3:
    start_btn = st.button("▶ SCALP SCAN", use_container_width=True, type="primary")

# جلب البيانات الحية من السوق
def fetch_scalp_data(ticker, interval):
    df = yf.download(ticker, period="5d", interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

# تنسيق الأرقام العشرية حسب سعر العملة
def format_price(price):
    if price < 1:
        return f"{price:.5f}"
    elif price < 50:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"

# دالة محاكاة صفقات آخر 24 ساعة (مع خصم عمولة المنصة 0.1% دخول وخروج)
def run_24h_backtest(df, interval, trade_size=100.0, fee_rate=0.001):
    candles_24h = 288 if interval == "5m" else 96
    if len(df) < candles_24h + 20:
        return 0, 0, 0.0, 0.0

    start_idx = len(df) - candles_24h
    wins = 0
    losses = 0
    net_profit = 0.0
    in_trade = False
    trade_type = ""
    entry_p = 0.0
    sl_p = 0.0
    tp_p = 0.0

    for i in range(start_idx, len(df) - 1):
        row = df.iloc[i]
        
        if in_trade:
            if trade_type == "BUY":
                if row['Low'] <= sl_p:
                    losses += 1
                    gross = -trade_size * ((entry_p - sl_p) / entry_p)
                    net_profit += gross - (trade_size * fee_rate * 2)
                    in_trade = False
                elif row['High'] >= tp_p:
                    wins += 1
                    gross = trade_size * ((tp_p - entry_p) / entry_p)
                    net_profit += gross - (trade_size * fee_rate * 2)
                    in_trade = False
            elif trade_type == "SELL":
                if row['High'] >= sl_p:
                    losses += 1
                    gross = -trade_size * ((sl_p - entry_p) / entry_p)
                    net_profit += gross - (trade_size * fee_rate * 2)
                    in_trade = False
                elif row['Low'] <= tp_p:
                    wins += 1
                    gross = trade_size * ((entry_p - tp_p) / entry_p)
                    net_profit += gross - (trade_size * fee_rate * 2)
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
            in_trade = True
            trade_type = "BUY"
            entry_p = row['Close']
            sl_p = entry_p - (1.2 * row['ATR'])
            tp_p = entry_p + (2.0 * row['ATR'])
        elif bear >= 4:
            in_trade = True
            trade_type = "SELL"
            entry_p = row['Close']
            sl_p = entry_p + (1.2 * row['ATR'])
            tp_p = entry_p - (2.0 * row['ATR'])

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    return wins, losses, win_rate, net_profit

if start_btn:
    placeholder = st.empty()
    
    with placeholder.container():
        st.markdown(f"""
        <div class="signal-box-scan">
            <p class="big-text-scan">SCANNING...</p>
            <p style="color:#ffffff; margin-top:10px;">CONF: --% &nbsp;|&nbsp; MODE: SCALPING ({selected_tf.upper()}) &nbsp;|&nbsp; ANALYZING...</p>
        </div>
        """, unsafe_allow_html=True)
        time.sleep(1.0)

    df = fetch_scalp_data(pairs[selected_pair], selected_tf)
    
    if len(df) > 50:
        df['EMA9'] = ta.trend.ema_indicator(df['Close'], window=9)
        df['EMA21'] = ta.trend.ema_indicator(df['Close'], window=21)
        df['EMA50'] = ta.trend.ema_indicator(df['Close'], window=50)
        df['RSI7'] = ta.momentum.rsi(df['Close'], window=7)
        df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
        df = df.dropna()

        wins, losses, win_rate, net_profit = run_24h_backtest(df, selected_tf, trade_size=100.0)
        
        last = df.iloc[-2]
        curr = df.iloc[-1]
        price = curr['Close']
        atr = last['ATR']
        
        c1_fast_trend = last['EMA9'] > last['EMA21']
        c2_macro_trend = price > last['EMA50']
        c3_fast_momentum = last['RSI7'] > 50
        c4_candle_action = last['Close'] > last['Open']
        c5_volatility_spike = last['ATR'] >= df['ATR'].tail(15).mean() * 0.9
        c6_rsi_not_extreme = 25 < last['RSI7'] < 75

        conditions = [
            ("1. FAST CROSS (EMA 9/21)", c1_fast_trend),
            ("2. MICRO TREND (EMA 50)", c2_macro_trend),
            ("3. SCALP MOMENTUM (RSI 7)", c3_fast_momentum),
            ("4. CANDLE BODY DIRECTION", c4_candle_action),
            ("5. LIQUIDITY / VOLATILITY", c5_volatility_spike),
            ("6. EXHAUSTION FILTER", c6_rsi_not_extreme)
        ]

        bull_score = sum([1 for _, status in conditions if status])
        bear_score = 6 - bull_score

        if bull_score >= 4:
            decision = "BUY"
            conf = int((bull_score / 6) * 100)
            box_class = "signal-box-buy"
            text_class = "big-text-buy"
            sl = price - (1.2 * atr)
            tp = price + (2.0 * atr)
            targets_html = f"""
            <div class="targets-box">
                <span style="color:#00ffcc;">ENTRY: {format_price(price)}</span>
                <span style="color:#ff0055;">SL: {format_price(sl)}</span>
                <span style="color:#00ff66;">TP: {format_price(tp)}</span>
            </div>
            """
