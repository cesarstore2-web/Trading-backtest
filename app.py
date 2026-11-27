import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم + Supertrend", layout="centered")

TRADE_AMOUNT = 100.0

HALAL_COINS = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "AVAX-USD": "Avalanche",
    "NEAR-USD": "NEAR Protocol",
    "SUI20947-USD": "Sui",
    "APT21794-USD": "Aptos",
    "INJ-USD": "Injective",
    "SEI-USD": "Sei",
    "TIA-USD": "Celestia",
    "RENDER-USD": "Render",
    "ARB11841-USD": "Arbitrum",
    "DOT-USD": "Polkadot",
    "LINK-USD": "Chainlink",
    "ADA-USD": "Cardano",
    "HBAR-USD": "Hedera"
}

timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3

use_supertrend = True
st_period = 10
st_multiplier = 3.0

show_settings = st.checkbox("إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    
    st.markdown("**إعدادات ضغط الشراء والدعوم**")
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", min_value=51, max_value=95, value=80, step=1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم:", min_value=15, max_value=200, value=100, step=5)

    st.markdown("**فلتر الاتجاه (Supertrend)**")
    s1, s2, s3 = st.columns(3)
    with s1:
        use_supertrend = st.checkbox("تفعيل الفلتر", value=True)
    with s2:
        st_period = st.number_input("ST Period", min_value=2, max_value=50, value=10, step=1)
    with s3:
        st_multiplier = st.number_input("ST Multiplier", min_value=0.5, max_value=10.0, value=3.0, step=0.1, format="%.1f")

    st.markdown("**إدارة المخاطر (ATR / RR)**")
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    st.divider()

st_status = f"Supertrend ({st_period}, {st_multiplier})" if use_supertrend else "بدون فلتر اتجاه"
st.caption(f"العملات: {len(HALAL_COINS)} | الشراء > {min_buy_ratio}% | الفلتر: {st_status} | الفريم: {timeframe}")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

def calc_supertrend(df, period=10, multiplier=3.0):
    atr = calc_atr(df, period)
    hl2 = (df['High'] + df['Low']) / 2.0
    
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    
    n = len(df)
    final_ub = np.zeros(n)
    final_lb = np.zeros(n)
    st_dir = np.ones(n)
    
    close = df['Close'].values
    b_ub = basic_ub.values
    b_lb = basic_lb.values
    
    for i in range(n):
        if i == 0:
            final_ub[i] = b_ub[i]
            final_lb[i] = b_lb[i]
            continue
            
        if b_ub[i] < final_ub[i-1] or close[i-1] > final_ub[i-1]:
            final_ub[i] = b_ub[i]
        else:
            final_ub[i] = final_ub[i-1]
            
        if b_lb[i] > final_lb[i-1] or close[i-1] < final_lb[i-1]:
            final_lb[i] = b_lb[i]
        else:
            final_lb[i] = final_lb[i-1]
            
        if st_dir[i-1] == 1:
            st_dir[i] = -1 if close[i] < final_lb[i] else 1
        else:
            st_dir[i] = 1 if close[i] > final_ub[i] else -1
            
    return pd.Series(st_dir, index=df.index)

@st.cache_data(ttl=300)
def fetch_data(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="30d", interval=yf_int, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if tf == "4h":
        df = df.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
    return df

def check_zone_touch(window_df, curr_candle):
    curr_low = float(curr_candle['Low'])
    curr_close = float(curr_candle['Close'])
    
    lows = window_df['Low'].values
    support_level = np.min(lows)
    tolerance = support_level * 0.005
    if curr_low <= (support_level + tolerance) and curr_close >= support_level:
        return True
    return False

def run_backtest(df, tf, buy_pct_req, lookback, a_len, a_m, rr, use_st, st_per, st_mult, days=7):
    c_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    bars_per_week = c_7d[tf]
    target_bars = bars_per_week if days == 7 else bars_per_week * 4

    min_bars = max(lookback, a_len, st_per) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0, {}

    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    df['ST_Dir'] = calc_supertrend(df, period=st_per, multiplier=st_mult)

    start_i = max(min_bars, len(df) - target_bars)
    total_len = len(df)
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001

    weekly_stats = {
        1: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
        2: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
        3: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
        4: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    }

    i = start_i
    while i < total_len - 1:
        c_row = df.iloc[i]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            i += 1
            continue

        st_ok = (c_row['ST_Dir'] == 1) if use_st else True
        if not st_ok:
            i += 1
            continue

        high_p = float(c_row['High'])
        low_p = float(c_row['Low'])
        close_p = float(c_row['Close'])
        open_p = float(c_row['Open'])
        vol = float(c_row['Volume'])
        candle_range = high_p - low_p

        if candle_range > 0 and vol > 0:
            buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0
        else:
            buy_pressure_ratio = 50.0

        strong_buying = (
            (buy_pressure_ratio >= buy_pct_req)
            and (close_p > open_p)
            and (vol >= float(c_row['Vol_MA']) * 0.8)
        )

        if strong_buying:
            window_df = df.iloc[i - lookback : i]
            in_zone = check_zone_touch(window_df, c_row)

            if in_zone:
                bars_from_end = total_len - i
                week_idx = 4 - int((bars_from_end - 1) // bars_per_week)
                week_idx = max(1, min(4, week_idx))

                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl = entry - sl_dist
                    tp = entry + (sl_dist * rr)
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

tot_w, tot_l, tot_o, tot_p, details = 0, 0, 0, 0.0, []
agg_weekly = {
    1: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    2: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    3: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    4: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
}

with st.spinner("جاري حساب الربح الصافي وتحليل فلتر Supertrend..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                res_7d = run_backtest(
                    df_m,
                    timeframe,
                    int(min_buy_ratio),
                    int(zone_lookback),
                    int(atr_len),
                    float(atr_mult),
                    float(rr_ratio),
                    use_supertrend,
                    int(st_period),
                    float(st_multiplier),
                    days=7
                )
                w, l, o, p, _ = res_7d
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append({
                        "العملة": name,
                        "ناجحة": w,
                        "خاسرة": l,
                        "مفتوحة": o,
                        "الربح الصافي ($)": round(p, 2)
                    })

                res_28d = run_backtest(
                    df_m,
                    timeframe,
                    int(min_buy_ratio),
                    int(zone_lookback),
                    int(atr_len),
                    float(atr_mult),
