import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم", layout="centered")

# رأس مال كل صفقة ثابت في الخفاء (100 دولار)
TRADE_AMOUNT = 100.0

# قائمة العملات الرقمية النقية (مشاريع بنية تحتية وطبقة أولى حلال)
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

# القيم الافتراضية
timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3

# إعدادات فلتر EMA الافتراضية
use_ema_filter = True
ema_length = 200

# مربع إظهار أو إخفاء الإعدادات
show_settings = st.checkbox("إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    
    st.markdown("**إعدادات ضغط الشراء والدعوم**")
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", min_value=51, max_value=95, value=80, step=1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم:", min_value=15, max_value=200, value=100, step=5)

    st.markdown("**فلتر الاتجاه (EMA Filter)**")
    e1, e2 = st.columns(2)
    with e1:
        use_ema_filter = st.checkbox("تفعيل فلتر EMA (الشراء فوق المتوسط)", value=True)
    with e2:
        ema_length = st.number_input("طول متوسط EMA:", min_value=10, max_value=500, value=200, step=10, disabled=not use_ema_filter)

    st.markdown("**إدارة المخاطر (ATR / RR)**")
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    st.divider()

ema_caption = f" | فلتر EMA {ema_length}" if use_ema_filter else ""
st.caption(f"العملات النقية: {len(HALAL_COINS)} عملة | الشراء > {min_buy_ratio}% عند الدعوم{ema_caption} | الفريم: {timeframe}")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_data(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="30d", interval=yf_int, progress=False)
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
    
    lows = window_df['Low'].values
    support_level = np.min(lows)
    tolerance = support_level * 0.005
    if curr_low <= (support_level + tolerance) and curr_close >= support_level:
        return True

    return False

def run_backtest(df, tf, buy_pct_req, lookback, a_len, a_m, rr, en_ema, ema_len, days=7):
    c_7d = {"5m": 2016, "15m": 672, "30m": 336, "1h": 168, "4h": 42}
    bars_per_week = c_7d[tf]
    target_bars = bars_per_week if days == 7 else bars_per_week * 4

    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0, {}

    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()

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
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']) or pd.isna(c_row['EMA']):
            i += 1
            continue

        high_p = float(c_row['High'])
        low_p = float(c_row['Low'])
        close_p = float(c_row['Close'])
        open_p = float(c_row['Open'])
        vol = float(c_row['Volume'])
        ema_val = float(c_row['EMA'])
        candle_range = high_p - low_p

        if candle_range > 0 and vol > 0:
            buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0
        else:
            buy_pressure_ratio = 50.0

        # التحقق من شرط فلتر EMA (إغلاق الشمعة فوق المتوسط المتحرك)
        ema_condition = (close_p > ema_val) if en_ema else True

        strong_buying = (
            (buy_pressure_ratio >= buy_pct_req)
            and (close_p > open_p)
            and (vol >= float(c_row['Vol_MA']) * 0.8)
            and ema_condition
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

with st.spinner("جاري حساب الربح الصافي..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                w, l, o, p, _ = run_backtest(
                    df_m, timeframe, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio),
                    use_ema_filter, int(ema_length), days=7
                )
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح الصافي ($)": round(p, 2)})

                _, _, _, _, w_stats = run_backtest(
                    df_m, timeframe, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio),
                    use_ema_filter, int(ema_length), days=28
                )
                for wk in range(1, 5):
                    if wk in w_stats:
                        agg_weekly[wk]["wins"] += w_stats[wk]["wins"]
                        agg_weekly[wk]["losses"] += w_stats[wk]["losses"]
                        agg_weekly[wk]["open"] += w_stats[wk]["open"]
                        agg_weekly[wk]["profit"] += w_stats[wk]["profit"]
        except Exception:
            pass

closed_t = tot_w + tot_l
win_r = (tot_w / closed_t * 100) if closed_t > 0 else 0.0

st.markdown(f"**الربح الصافي سبوت لمدة 7 أيام ({timeframe})**")
st.title(f"$ {tot_p:.2f}")
st.markdown("**نسبة النجاح**")
st.title(f"{win_r:.1f}%")
st.info(f"↑ مغلقة: {closed_t} | مفتوحة: {tot_o}")
st.success(f"✅ {tot_w} ناجحة")
st.error(f"❌ {tot_l} خاسرة")

# جدول الربح الصافي لكل أسبوع على حدة لمدة الشهر الحالي
st.subheader("الربح الصافي لكل أسبوع خلال الشهر الحالي")
week_labels = {
    1: "الأسبوع الأول",
    2: "الأسبوع الثاني",
    3: "الأسبوع الثالث",
    4: "الأسبوع الرابع (الأخير)"
}

weekly_rows = []
sum_w, sum_l, sum_o, sum_p = 0, 0, 0, 0.0

for wk in range(1, 5):
    w_wins = agg_weekly[wk]["wins"]
    w_losses = agg_weekly[wk]["losses"]
    w_open = agg_weekly[wk]["open"]
    w_prof = agg_weekly[wk]["profit"]
    
    sum_w += w_wins
    sum_l += w_losses
    sum_o += w_open
    sum_p += w_prof
    
    w_closed = w_wins + w_losses
