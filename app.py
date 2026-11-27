import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم", layout="centered")

TRADE_AMOUNT = 100.0

HALAL_COINS = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana",
    "AVAX-USD": "Avalanche", "NEAR-USD": "NEAR Protocol", "SUI20947-USD": "Sui",
    "APT21794-USD": "Aptos", "INJ-USD": "Injective", "SEI-USD": "Sei",
    "TIA-USD": "Celestia", "RENDER-USD": "Render", "ARB11841-USD": "Arbitrum",
    "DOT-USD": "Polkadot", "LINK-USD": "Chainlink", "ADA-USD": "Cardano",
    "HBAR-USD": "Hedera"
}

timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3

# مكان مخصص في الأعلى لعرض الربح الصافي دائماً
top_profit_placeholder = st.empty()

# --- ترتيب المربعات حسب الأولوية ---
show_weekly_summary = st.checkbox("🔥 إظهار ملخص الأداء للأسبوع الحالي", value=False)
show_details = st.checkbox("📋 إظهار تفاصيل الصفقات", value=False)
show_4weeks = st.checkbox("📅 إظهار سجل آخر 4 أسابيع", value=False)
show_settings = st.checkbox("⚙️ إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    st.divider()
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", 51, 95, 80, 1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم:", 15, 200, 100, 5)
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1)
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1)
    st.divider()

st.caption(f"العملات: {len(HALAL_COINS)} | الشراء > {min_buy_ratio}% | الفريم: {timeframe}")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_data(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="45d", interval=yf_int, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if tf == "4h":
        df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    return df

def check_zone_touch(window_df, curr_candle):
    curr_low = float(curr_candle['Low'])
    curr_close = float(curr_candle['Close'])
    support_level = np.min(window_df['Low'].values)
    tolerance = support_level * 0.005
    return (curr_low <= (support_level + tolerance)) and (curr_close >= support_level)

def check_live_signals(df, name, buy_pct_req, lookback, a_len, a_m, rr):
    if len(df) < max(lookback, a_len) + 5:
        return None
    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    
    for idx, status in [(-2, "مؤكدة (مغلقة)"), (-1, "قيد التشكّل")]:
        c_row = df.iloc[idx]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            continue
        high_p, low_p, close_p, open_p, vol = float(c_row['High']), float(c_row['Low']), float(c_row['Close']), float(c_row['Open']), float(c_row['Volume'])
        c_range = high_p - low_p
        buy_ratio = ((close_p - low_p) / c_range * 100.0) if (c_range > 0 and vol > 0) else 50.0
        
        if (buy_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8):
            end_pos = len(df) + idx
            if check_zone_touch(df.iloc[end_pos - lookback : end_pos], c_row):
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    return dict(العملة=name, الحالة=status, الشراء=f"{buy_ratio:.0f}%", الدخول=round(close_p, 4), SL=round(close_p - sl_dist, 4), TP=round(close_p + (sl_dist * rr), 4))
    return None

def run_backtest(df, tf, buy_pct_req, lookback, a_len, a_m, rr, days=7):
    c_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    bars_per_week = c_7d[tf]
    target_bars = bars_per_week if days == 7 else bars_per_week * 4
    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0, {}
        
    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    start_i = max(min_bars, len(df) - target_bars)
    total_len = len(df)
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001
    weekly_stats = {w: dict(wins=0, losses=0, open=0, profit=0.0) for w in range(1, 5)}
    
    i = start_i
    while i < total_len - 1:
        c_row = df.iloc[i]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            i += 1
            continue
        high_p, low_p, close_p, open_p, vol = float(c_row['High']), float(c_row['Low']), float(c_row['Close']), float(c_row['Open']), float(c_row['Volume'])
        c_range = high_p - low_p
        buy_ratio = ((close_p - low_p) / c_range * 100.0) if (c_range > 0 and vol > 0) else 50.0
        
        if (buy_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8):
            if check_zone_touch(df.iloc[i - lookback : i], c_row):
                week_idx = max(1, min(4, 4 - int((total_len - i - 1) // bars_per_week)))
                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl, tp = entry - sl_dist, entry + (sl_dist * rr)
                    closed = False
                    for j in range(i + 1, total_len):
                        fut = df.iloc[j]
                        if float(fut['Low']) <= sl:
                            loss_val = (TRADE_AMOUNT * (sl_dist / entry) + TRADE_AMOUNT * fee * 2)
                            losses += 1
                            profit -= loss_val
                            weekly_stats[week_idx]["losses"] += 1
                            weekly_stats[week_idx]["profit"] -= loss_val
                            closed = True
                            i = j
                            break
                        elif float(fut['High']) >= tp:
                            win_val = (TRADE_AMOUNT * ((tp - entry) / entry) - TRADE_AMOUNT * fee * 2)
                            wins += 1
                            profit += win_val
                            weekly_stats[week_idx]["wins"] += 1
                            weekly_stats[week_idx]["profit"] += win_val
                            closed = True
                            i = j
                            break
                    if not closed:
                        open_t += 1
                        weekly_stats[week_idx]["open"] += 1
                        break
        i += 1
    return wins, losses, open_t, profit, weekly_stats

tot_w, tot_l, tot_o, tot_p = 0, 0, 0, 0.0
details, live_signals = [], []
agg_weekly = {w: dict(wins=0, losses=0, open=0, profit=0.0) for w in range(1, 5)}

with st.spinner("جاري تحليل السوق..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                sig = check_live_signals(df_m, name, int(min_buy_ratio), int(zone_lookback), int(atr_len), float(atr_mult), float(rr_ratio))
                if sig:
                    live_signals.append(sig)

                w, l, o, p, _ = run_backtest(df_m, timeframe, int(min_buy_ratio), int(zone_lookback), int(atr_len), float(atr_mult), float(rr_ratio), days=7)
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append(dict(العملة=name, ناجحة=w, خاسرة=l, مفتوحة=o, الربح=round(p, 2)))
                
                _, _, _, _, w_stats = run_backtest(df_m, timeframe, int(min_buy_ratio), int(zone_lookback), int(atr_len), float(atr_mult), float(rr_ratio), days=28)
                for wk in range(1, 5):
                    if wk in w_stats:
                        agg_weekly[wk]["wins"] += w_stats[wk]["wins"]
                        agg_weekly[wk]["losses"] += w_stats[wk]["losses"]
                        agg_weekly[wk]["open"] += w_stats[wk]["open"]
                        agg_weekly[wk]["profit"] += w_stats[wk]["profit"]
        except Exception:
            pass

# --- عرض بطاقة الربح الصافي الدائمة في أعلى الصفحة ---
p_color = "#16a34a" if tot_p >= 0 else "#dc2626"
p_bg = "rgba(22, 163, 74, 0.14)" if tot_p >= 0 else "rgba(220, 38, 38, 0.14)"
p_sign = "+" if tot_p > 0 else ""

top_profit_placeholder.markdown(
    f"""
    <div style="background-color:{p_bg}; border:2px solid {p_color}; border-radius:12px; padding:14px; text-align:center; margin-bottom:14px;">
        <div style="font-size:15px; font-weight:bold; opacity:0.9;">💰 الربح الصافي للأسبوع الحالي</div>
        <div style="font-size:32px; font-weight:900; color:{p_color}; direction:ltr; margin-top:4px;">{p_sign}{tot_p:.2f}$</div>
    </div>
    """,
    unsafe_allow_html=True
)

# 1. التوصيات المستقبلية (الفرص الحالية)
st.subheader("🎯 التوصيات المستقبلية (الفرص الحالية)")
if live_signals:
    st.dataframe(pd.DataFrame(live_signals), use_container_width=True, hide_index=True)
else:
    st.info("لا توجد فرص مطابقة للشروط في الشمعة الحالية أو السابقة.")

# 2. ملخص الأسبوع الحالي (يظهر عند تفعيل المربع الأول)
if show_weekly_summary:
    st.subheader("🔥 ملخص الأداء للأسبوع الحالي")
    c1, c2, c3 = st.columns(3)
    c1.metric("ناجحة", tot_w)
    c2.metric("خاسرة", tot_l)
    c3.metric("مفتوحة", tot_o)
    cw_closed = tot_w + tot_l
    cw_winrate = (tot_w / cw_closed * 100) if cw_closed > 0 else 0.0
