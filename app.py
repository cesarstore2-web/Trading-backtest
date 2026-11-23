import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="لوحة التوصيات وموجات إليوت (5m)", layout="centered")

css_style = """
<style>
.stApp { background-color: #0d0d12; color: #ffffff; direction: rtl; font-family: Tahoma, sans-serif; }
div[role='radiogroup'] { display: flex; justify-content: space-around; background-color: #1c1c24; padding: 6px; border-radius: 12px; margin-bottom: 15px; }
div[role='radiogroup'] label { padding: 8px 18px; border-radius: 8px; color: #ffffff !important; }
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

# خريطة الرموز المتوافقة مع Yahoo Finance
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

# 1. شريط اختيار المدة الزمنية للاختبار على إطار 5 دقائق
period_map = {
    "24 ساعة": "1d",
    "أسبوع": "7d",
    "شهر": "30d"
}
selected_period_label = st.radio(
    "الفترة:",
    options=list(period_map.keys()),
    horizontal=True,
    label_visibility="collapsed"
)
selected_period = period_map[selected_period_label]

# 2. مدخلات إدارة المخاطر كما في الصورة
atr_mult = st.number_input("ATR SL:", min_value=0.5, max_value=15.0, value=4.0, step=0.1, format="%.2f")
rr_ratio = st.number_input("R:R:", min_value=0.5, max_value=15.0, value=3.70, step=0.1, format="%.2f")

filter_options = ["الكل"] + list(SYMBOLS_MAP.keys())
selected_coin = st.selectbox("العملة:", filter_options)

# 3. مربعات تفعيل خيارات الربح الصافي (شراء أم شراء وبيع)
col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    trade_mode = st.radio(
        "نوع الصفقات المحتسبة:",
        options=["شراء فقط", "شراء و بيع"],
        horizontal=True
    )

@st.cache_data(ttl=300)
def run_backtest_and_signals(symbols_dict, period_str, atr_m, rr_m, allow_short):
    all_trades = []
    latest_signals = []
    risk_per_trade_usd = 100.0  # حجم المخاطرة الثابت لكل صفقة لحساب الربح بالدولار

    for coin_name, yf_ticker in symbols_dict.items():
        try:
            df = yf.download(yf_ticker, period=period_str, interval="5m", progress=False)
            if df.empty or len(df) < 35:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # حساب مؤشر ATR (14)
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATR'] = tr.rolling(14).mean()

            # محاكاة الصفقات التاريخية (Backtest) على إطار 5 دقائق
            in_trade = False
            trade_type = None
            entry_p = sl_p = tp_p = 0.0

            for i in range(20, len(df)):
                row = df.iloc[i]
                atr_val = row['ATR']
                if pd.isna(atr_val) or atr_val == 0:
                    continue

                if not in_trade:
                    window = df.iloc[i-20:i]
                    w0 = window['Low'].min()
                    w1 = window['High'].max()
                    diff = w1 - w0
                    if diff <= 0:
                        continue

                    fib_buy = w1 - (diff * 0.618)
                    fib_sell = w0 + (diff * 0.618)

                    # شرط دخول شراء (ارتداد فيبوناتشي 0.618)
                    if row['Low'] <= fib_buy <= row['High'] and row['Close'] > fib_buy:
                        in_trade = True
                        trade_type = "شراء"
                        entry_p = float(row['Close'])
                        sl_p = entry_p - (atr_val * atr_m)
                        tp_p = entry_p + (atr_val * atr_m * rr_m)

                    # شرط دخول بيع (إذا تم تفعيل خيار شراء وبيع)
                    elif allow_short and row['Low'] <= fib_sell <= row['High'] and row['Close'] < fib_sell:
                        in_trade = True
                        trade_type = "بيع"
                        entry_p = float(row['Close'])
                        sl_p = entry_p + (atr_val * atr_m)
                        tp_p = entry_p - (atr_val * atr_m * rr_m)
                else:
                    if trade_type == "شراء":
                        if row['Low'] <= sl_p:
                            all_trades.append({"coin": coin_name, "result": "loss", "pnl": -risk_per_trade_usd})
                            in_trade = False
                        elif row['High'] >= tp_p:
                            all_trades.append({"coin": coin_name, "result": "win", "pnl": risk_per_trade_usd * rr_m})
                            in_trade = False
                    elif trade_type == "بيع":
                        if row['High'] >= sl_p:
                            all_trades.append({"coin": coin_name, "result": "loss", "pnl": -risk_per_trade_usd})
                            in_trade = False
                        elif row['Low'] <= tp_p:
                            all_trades.append({"coin": coin_name, "result": "win", "pnl": risk_per_trade_usd * rr_m})
                            in_trade = False

            # استخراج أحدث إشارة نشطة لكل عملة
            recent_df = df.tail(30).reset_index(drop=True)
            mid = len(recent_df) // 2
            w0 = float(recent_df['Low'].iloc[:mid].min())
            w1 = float(recent_df['High'].iloc[mid:].max())
            sig_type = "شراء"

            if w1 <= w0 and allow_short:
                w1 = float(recent_df['High'].iloc[:mid].max())
                w0 = float(recent_df['Low'].iloc[mid:].min())
                sig_type = "بيع"

            diff = abs(w1 - w0)
            curr_price = float(recent_df['Close'].iloc[-1])
            curr_atr = float(recent_df['ATR'].iloc[-1]) if not pd.isna(recent_df['ATR'].iloc[-1]) else (curr_price * 0.01)

            if sig_type == "شراء":
                entry_sig = w1 - (diff * 0.618)
                sl_sig = entry_sig - (curr_atr * atr_m)
                tp_sig = entry_sig + (curr_atr * atr_m * rr_m)
                pivot_idx = int(recent_df['Low'].iloc[:mid].idxmin())
            else:
                entry_sig = w0 + (diff * 0.618)
                sl_sig = entry_sig + (curr_atr * atr_m)
                tp_sig = entry_sig - (curr_atr * atr_m * rr_m)
                pivot_idx = int(recent_df['High'].iloc[:mid].idxmax())

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

        except Exception:
            continue

    return pd.DataFrame(all_trades), pd.DataFrame(latest_signals)

allow_short_flag = (trade_mode == "شراء و بيع")

with st.spinner(f"جاري تحليل بيانات Yahoo Finance ({selected_period_label} - 5m)..."):
    df_trades, df_signals = run_backtest_and_signals(
        SYMBOLS_MAP, selected_period, atr_mult, rr_ratio, allow_short_flag
    )

# تصفية النتائج حسب العملة المختارة
if selected_coin != "الكل":
    filtered_trades = df_trades[df_trades["coin"] == selected_coin] if not df_trades.empty else pd.DataFrame()
    filtered_signals = df_signals[df_signals["coin"] == selected_coin] if not df_signals.empty else pd.DataFrame()
else:
    filtered_trades = df_trades
    filtered_signals = df_signals

# حساب الإحصائيات
total_trades = len(filtered_trades)
win_trades = len(filtered_trades[filtered_trades["result"] == "win"]) if total_trades > 0 else 0
loss_trades = len(filtered_trades[filtered_trades["result"] == "loss"]) if total_trades > 0 else 0
win_rate = round((win_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
total_profit_usd = round(filtered_trades[filtered_trades["pnl"] > 0]["pnl"].sum(), 2) if total_trades > 0 else 0.0
total_loss_usd = round(abs(filtered_trades[filtered_trades["pnl"] < 0]["pnl"].sum()), 2) if total_trades > 0 else 0.0
net_profit_usd = round(total_profit_usd - total_loss_usd, 2)

# 4. بطاقة صافي الربح في الأعلى كما طلبت
net_color_class = "green-text" if net_profit_usd >= 0 else "red-text"
st.markdown(
    f"<div class='metric-card card-net'>"
    f"<div class='card-title'>✨ صافي الربح ({trade_mode})</div>"
    f"<div class='net-value {net_color_class}'>${net_profit_usd:,.2f}</div>"
    f"</div>",
    unsafe_allow_html=True
)

# 5. قسم النتائج والإحصائيات
st.markdown(f"### 📊 نتائج {selected_period_label} (5m)")

col1, col2 = st.columns(2)
with col1:
