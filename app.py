import streamlit as st
import requests
import pandas as pd
import numpy as np

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم (Spot)", layout="centered")

TRADE_AMOUNT = 100.0

HALAL_COINS = {
    "BTCUSDT": "Bitcoin",
    "ETHUSDT": "Ethereum",
    "SOLUSDT": "Solana",
    "AVAXUSDT": "Avalanche",
    "NEARUSDT": "NEAR Protocol",
    "SUIUSDT": "Sui",
    "APTUSDT": "Aptos",
    "INJUSDT": "Injective",
    "SEIUSDT": "Sei",
    "TIAUSDT": "Celestia",
    "RENDERUSDT": "Render",
    "ARBUSDT": "Arbitrum",
    "DOTUSDT": "Polkadot",
    "LINKUSDT": "Chainlink",
    "ADAUSDT": "Cardano",
    "HBARUSDT": "Hedera"
}

timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3

col_btn, col_chk = st.columns(2)
with col_btn:
    if st.button("🔄 تحديث البيانات"):
        st.cache_data.clear()
with col_chk:
    show_settings = st.checkbox("إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    st.markdown("**إعدادات ضغط الشراء والدعوم**")
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", min_value=51, max_value=95, value=80, step=1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم:", min_value=15, max_value=200, value=100, step=5)
    st.markdown("**إدارة المخاطر (ATR / RR)**")
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    st.divider()

st.caption(f"تداول فوري (Spot 1:1 بدون رافعة) | {len(HALAL_COINS)} عملة | الشراء > {min_buy_ratio}% | الفريم: {timeframe}")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_data(symbol, tf):
    url = f"https://binance.vision{symbol}&interval={tf}&limit=1000"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            url_alt = f"https://binance.com{symbol}&interval={tf}&limit=1000"
            resp = requests.get(url_alt, timeout=5)
        if resp.status_code != 200:
            return pd.DataFrame()
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            'Open_time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close_time', 'Quote_vol', 'Trades', 'Taker_buy_base', 'Taker_buy_quote', 'Ignore'
        ])
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return pd.DataFrame()

def check_zone_touch(window_df, curr_candle):
    curr_low = float(curr_candle['Low'])
    curr_close = float(curr_candle['Close'])
    lows = window_df['Low'].values
    support_level = np.min(lows)
    tolerance = support_level * 0.005
    return (curr_low <= (support_level + tolerance)) and (curr_close >= support_level)

def check_live_signal(df, buy_pct_req, lookback, a_len, a_m, rr):
    if len(df) < max(lookback, a_len) + 5:
        return None
    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    c_row = df.iloc[-2]
    if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
        return None
    high_p, low_p = float(c_row['High']), float(c_row['Low'])
    close_p, open_p = float(c_row['Close']), float(c_row['Open'])
    vol = float(c_row['Volume'])
    candle_range = high_p - low_p
    buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0 if (candle_range > 0 and vol > 0) else 50.0
    strong_buying = (buy_pressure_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8)
    if strong_buying:
        window_df = df.iloc[-2 - lookback : -2]
        if check_zone_touch(window_df, c_row):
            sl_dist = float(c_row['ATR']) * a_m
            if sl_dist > 0:
                return {
                    "سعر الشراء ($)": round(close_p, 4),
                    "هدف البيع TP ($)": round(close_p + (sl_dist * rr), 4),
                    "وقف الخسارة SL ($)": round(close_p - sl_dist, 4),
                    "قوة الشراء (%)": f"{buy_pressure_ratio:.1f}%"
                }
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
        high_p, low_p = float(c_row['High']), float(c_row['Low'])
        close_p, open_p = float(c_row['Close']), float(c_row['Open'])
        vol = float(c_row['Volume'])
        candle_range = high_p - low_p
        buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0 if (candle_range > 0 and vol > 0) else 50.0
        strong_buying = (buy_pressure_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8)
        if strong_buying:
            window_df = df.iloc[i - lookback : i]
            if check_zone_touch(window_df, c_row):
                bars_from_end = total_len - i
                week_idx = max(1, min(4, 4 - int((bars_from_end - 1) // bars_per_week)))
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

tot_w, tot_l, tot_o, tot_p, details, live_signals = 0, 0, 0, 0.0, [], []
agg_weekly = {
    1: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    2: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    3: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
    4: {"wins": 0, "losses": 0, "open": 0, "profit": 0.0},
}

progress_bar = st.progress(0, text="جاري جلب بيانات العملات...")
coins_list = list(HALAL_COINS.items())

for idx, (symbol, name) in enumerate(coins_list):
    progress_bar.progress((idx + 1) / len(coins_list), text=f"جاري فحص {name}...")
    df_m = fetch_data(symbol, timeframe)
    if not df_m.empty:
        sig = check_live_signal(
            df_m, int(min_buy_ratio), int(zone_lookback),
            int(atr_len), float(atr_mult), float(rr_ratio)
        )
        if sig:
            live_signals.append({"العملة": name, **sig})

        w, l, o, p, _ = run_backtest(
            df_m, timeframe, int(min_buy_ratio), int(zone_lookback),
            int(atr_len), float(atr_mult), float(rr_ratio), days=7
        )
        tot_w += w
        tot_l += l
        tot_o += o
        tot_p += p
        if (w + l + o) > 0:
            details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح الصافي ($)": round(p, 2)})

        _, _, _, _, w_stats = run_backtest(
            df_m, timeframe, int(min_buy_ratio), int(zone_lookback),
            int(atr_len), float(atr_mult), float(rr_ratio), days=28
        )
        for wk in range(1, 5):
            if wk in w_stats:
                agg_weekly[wk]["wins"] += w_stats[wk]["wins"]
                agg_weekly[wk]["losses"] += w_stats[wk]["losses"]
                agg_weekly[wk]["open"] += w_stats[wk]["open"]
                agg_weekly[wk]["profit"] += w_stats[wk]["profit"]

progress_bar.empty()

st.subheader("🎯 فرص الشراء الحية الآن (Spot)")
if live_signals:
    st.success(f"تم رصد {len(live_signals)} فرصة شراء مطابقة للشروط على آخر شمعة مغلقة!")
