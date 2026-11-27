import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم المطور", layout="centered")

TRADE_AMOUNT = 100.0
MOROCCO_TZ = timezone.utc

HALAL_COINS = {
    "TIA-USD": "Celestia (TIA)",
    "SUI20947-USD": "Sui (SUI)",
    "RENDER-USD": "Render (RENDER)",
    "ARB11841-USD": "Arbitrum (ARB)",
    "DOT-USD": "Polkadot (DOT)",
    "TAO22974-USD": "Bittensor (TAO)",
    "HBAR-USD": "Hedera (HBAR)",
    "LINK-USD": "Chainlink (LINK)",
    "SOL-USD": "Solana (SOL)",
    "AVAX-USD": "Avalanche (AVAX)",
    "NEAR-USD": "NEAR Protocol (NEAR)",
    "APT21794-USD": "Aptos (APT)",
    "SEI-USD": "Sei (SEI)",
    "ATOM-USD": "Cosmos (ATOM)",
    "ALGO-USD": "Algorand (ALGO)",
    "IMX10603-USD": "Immutable (IMX)",
    "ICP-USD": "Internet Computer (ICP)",
    "FIL-USD": "Filecoin (FIL)",
    "STX4847-USD": "Stacks (STX)",
    "VET-USD": "VeChain (VET)",
    "KAS-USD": "Kaspa (KAS)",
    "EGLD-USD": "MultiversX (EGLD)"
}

def get_sunday_to_sunday_window(ref_dt):
    days_since_sunday = (ref_dt.weekday() + 1) % 7
    start_dt = (ref_dt - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = (start_dt + timedelta(days=7)).replace(hour=23, minute=55, second=0, microsecond=0)
    return start_dt, end_dt

def get_current_month_weeks(now_dt):
    first_day_month = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    w_start, w_end = get_sunday_to_sunday_window(first_day_month)
    weeks = []
    week_num = 1
    while w_start <= now_dt:
        weeks.append((f"الأسبوع {week_num}", w_start, w_end))
        w_start = w_start + timedelta(days=7)
        w_end = (w_start + timedelta(days=7)).replace(hour=23, minute=55, second=0, microsecond=0)
        week_num += 1
    return weeks

now_ma = datetime.now(MOROCCO_TZ)
start_window, end_window = get_sunday_to_sunday_window(now_ma)
month_weeks = get_current_month_weeks(now_ma)

# القيم الافتراضية المحسنة
timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3
use_demand = False
use_support = True
use_trend_guard = True
max_open_trades = 3

show_settings = st.checkbox("إظهار إعدادات الاستراتيجية", value=False)

if show_settings:
    timeframe = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=3)
    st.markdown("**إعدادات ضغط الشراء والدعوم**")
    c1, c2 = st.columns(2)
    with c1:
        min_buy_ratio = st.number_input("نسبة سيطرة الشراء (%):", min_value=51, max_value=95, value=80, step=1)
    with c2:
        zone_lookback = st.number_input("نطاق البحث عن الدعوم والطلب:", min_value=15, max_value=200, value=100, step=5)

    st.markdown("**إدارة المخاطر (ATR / RR)**")
    r1, r2, r3 = st.columns(3)
    with r1:
        atr_len = st.number_input("ATR Length", 2, 100, 13, 1)
    with r2:
        atr_mult = st.number_input("ATR Multiplier (SL)", 0.1, 10.0, 2.3, 0.1, format="%.1f")
    with r3:
        rr_ratio = st.number_input("Risk-to-Reward (1:X)", 0.1, 10.0, 2.3, 0.1, format="%.1f")

    st.markdown("**فلاتر الحماية وإدارة المحفظة**")
    p1, p2 = st.columns(2)
    with p1:
        use_trend_guard = st.checkbox("درع الاتجاه العام (4H EMA 50)", value=True)
    with p2:
        max_open_trades = st.number_input("أقصى صفقات مفتوحة معاً:", min_value=1, max_value=22, value=3, step=1)

    st.markdown("**مصدر مناطق الدخول**")
    z1, z2 = st.columns(2)
    with z1:
        use_demand = st.checkbox("مناطق الطلب (Demand Zones)", value=False)
    with z2:
        use_support = st.checkbox("مستويات الدعم (Support Levels)", value=True)
    st.divider()

st.caption(f"العملات: {len(HALAL_COINS)} عملة | أقصى صفقات متزامنة: {max_open_trades} | الدورة: {start_window.strftime('%m-%d %H:%M')} إلى {end_window.strftime('%m-%d %H:%M')} (UTC)")

def calc_atr(df, length):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()

@st.cache_data(ttl=300)
def fetch_data(ticker, tf):
    yf_int = "1h" if tf == "4h" else tf
    df = yf.download(ticker, period="60d", interval=yf_int, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize(MOROCCO_TZ)
    else:
        df.index = df.index.tz_convert(MOROCCO_TZ)
    if tf == "4h":
        df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    return df

@st.cache_data(ttl=300)
def fetch_btc_regime():
    df_btc = yf.download("BTC-USD", period="60d", interval="1h", progress=False)
    if df_btc.empty:
        return pd.DataFrame()
    if isinstance(df_btc.columns, pd.MultiIndex):
        df_btc.columns = df_btc.columns.get_level_values(0)
    if df_btc.index.tz is None:
        df_btc.index = df_btc.index.tz_localize(MOROCCO_TZ)
    else:
        df_btc.index = df_btc.index.tz_convert(MOROCCO_TZ)
    df_4h = df_btc.resample('4h').agg({'Close': 'last'}).dropna()
    df_4h['BTC_EMA50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()
    # السوق آمن للشراء إذا كان البيتكوين فوق EMA50 على 4 ساعات أو في حالة ارتداد واضح
    df_4h['Market_Safe'] = (df_4h['Close'] >= df_4h['BTC_EMA50'] * 0.985).shift(1).fillna(True)
    return df_4h[['Market_Safe']]
def check_zone_touch(window_df, curr_candle, enable_demand, enable_support):
    curr_low = float(curr_candle['Low'])
    curr_close = float(curr_candle['Close'])
    
    if enable_demand:
        for k in range(len(window_df) - 2):
            c = window_df.iloc[k]
            next_c = window_df.iloc[k + 1]
            c_body = abs(float(c['Close']) - float(c['Open']))
            next_body = float(next_c['Close']) - float(next_c['Open'])
            if next_body > 0 and next_body > (c_body * 1.8):
                zone_top = max(float(c['Open']), float(c['Close']))
                zone_bottom = float(c['Low'])
                if curr_low <= zone_top and curr_close >= zone_bottom:
                    return True, "منطقة طلب"

    if enable_support:
        lows = window_df['Low'].values
        support_level = np.min(lows)
        tolerance = support_level * 0.005
        if curr_low <= (support_level + tolerance) and curr_close >= support_level:
            return True, "مستوى دعم"

    return False, ""

def generate_coin_signals(df, name, btc_df, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support, trend_guard):
    min_bars = max(lookback, a_len, 60)
    if len(df) < min_bars:
        return []

    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    # متوسط 200 ساعة (يعادل تقريباً 50 شمعة على فريم 4 ساعات) لتحديد اتجاه العملة
    df['Coin_EMA'] = df['Close'].ewm(span=200, adjust=False).mean()

    if trend_guard and not btc_df.empty:
        merged = pd.merge_asof(df.sort_index(), btc_df.sort_index(), left_index=True, right_index=True, direction='backward')
        df['Market_Safe'] = merged['Market_Safe'].fillna(True)
    else:
        df['Market_Safe'] = True

    signals = []
    for i in range(min_bars, len(df) - 1):
        c_row = df.iloc[i]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            continue

        # تطبيق درع الاتجاه العام (البيتكوين آمن + العملة ليست في انهيار حاد)
        if trend_guard:
            if not bool(c_row['Market_Safe']) or float(c_row['Close']) < float(c_row['Coin_EMA']) * 0.96:
                continue

        high_p, low_p = float(c_row['High']), float(c_row['Low'])
        close_p, open_p = float(c_row['Close']), float(c_row['Open'])
        vol = float(c_row['Volume'])
        candle_range = high_p - low_p

        buy_ratio = ((close_p - low_p) / candle_range) * 100.0 if (candle_range > 0 and vol > 0) else 50.0
        strong_buying = (buy_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8)

        if strong_buying:
            window_df = df.iloc[i - lookback : i]
            in_zone, _ = check_zone_touch(window_df, c_row, en_demand, en_support)

            if in_zone:
                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl = entry - sl_dist
                    tp = entry + (sl_dist * rr)
                    exit_time = df.index[-1]
                    outcome = "open"
                    pnl = 0.0
                    fee = 0.001

                    for j in range(i + 1, len(df)):
                        fut = df.iloc[j]
                        if float(fut['Low']) <= sl:
                            outcome = "loss"
                            pnl = -(TRADE_AMOUNT * (sl_dist / entry) + TRADE_AMOUNT * fee * 2)
                            exit_time = df.index[j]
                            break
                        elif float(fut['High']) >= tp:
                            outcome = "win"
                            pnl = (TRADE_AMOUNT * ((tp - entry) / entry) - TRADE_AMOUNT * fee * 2)
                            exit_time = df.index[j]
                            break

                    signals.append({
                        "coin": name,
                        "entry_time": df.index[i],
                        "exit_time": exit_time,
                        "buy_ratio": buy_ratio,
                        "outcome": outcome,
                        "pnl": pnl
                    })
    return signals

# محاكاة المحفظة بحد أقصى للصفقات المتزامنة لمنع التكدس وقت الهبوط
def simulate_portfolio(all_signals, start_dt, end_dt, max_concurrent):
    period_sigs = [s for s in all_signals if start_dt <= s["entry_time"] <= end_dt]
    # ترتيب الإشارات زمنياً ثم حسب قوة ضغط الشراء
    period_sigs.sort(key=lambda x: (x["entry_time"], -x["buy_ratio"]))

    active_trades = []
    wins, losses, open_t, net_profit = 0, 0, 0, 0.0
    coin_breakdown = {}

    for sig in period_sigs:
        curr_t = sig["entry_time"]
        # إزالة الصفقات التي أغلقت قبل وقت الإشارة الجديدة
        active_trades = [t for t in active_trades if t["exit_time"] > curr_t]

        # منع تكرار نفس العملة أو تجاوز الحد الأقصى للصفقات المفتوحة معاً
        if len(active_trades) >= max_concurrent:
            continue
        if any(t["coin"] == sig["coin"] for t in active_trades):
            continue

        # قبول الصفقة
        active_trades.append(sig)
        c_name = sig["coin"]
        if c_name not in coin_breakdown:
            coin_breakdown[c_name] = {"العملة": c_name, "ناجحة": 0, "خاسرة": 0, "مفتوحة": 0, "الربح الصافي ($)": 0.0}

        # إذا أغلقت الصفقة بعد نهاية الأسبوع الحالي تُحسب كمفتوحة في هذا الأسبوع
        if sig["outcome"] == "open" or sig["exit_time"] > end_dt:
            open_t += 1
            coin_breakdown[c_name]["مفتوحة"] += 1
        elif sig["outcome"] == "win":
            wins += 1
            net_profit += sig["pnl"]
            coin_breakdown[c_name]["ناجحة"] += 1
            coin_breakdown[c_name]["الربح الصافي ($)"] = round(coin_breakdown[c_name]["الربح الصافي ($)"] + sig["pnl"], 2)
        elif sig["outcome"] == "loss":
            losses += 1
            net_profit += sig["pnl"]
            coin_breakdown[c_name]["خاسرة"] += 1
            coin_breakdown[c_name]["الربح الصافي ($)"] = round(coin_breakdown[c_name]["الربح الصافي ($)"] + sig["pnl"], 2)

    return wins, losses, open_t, net_profit, list(coin_breakdown.values())

def check_live_signals(df, name, btc_df, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support, trend_guard):
    min_bars = max(lookback, a_len, 60)
    if len(df) < min_bars:
        return None, None

    df = df.copy()
    df['ATR'] = calc_atr(df, a_len)
    df['Coin_EMA'] = df['Close'].ewm(span=200, adjust=False).mean()
    last_candle = df.iloc[-1]
    window_df = df.iloc[-lookback - 1 : -1]

    market_ok = True
    if trend_guard and not btc_df.empty:
        market_ok = bool(btc_df['Market_Safe'].iloc[-1]) and (float(last_candle['Close']) >= float(last_candle['Coin_EMA']) * 0.96)

    high_p, low_p = float(last_candle['High']), float(last_candle['Low'])
    close_p, open_p = float(last_candle['Close']), float(last_candle['Open'])
    candle_range = high_p - low_p

    buy_ratio = ((close_p - low_p) / candle_range * 100.0) if candle_range > 0 else 50.0
    in_zone, z_type = check_zone_touch(window_df, last_candle, en_demand, en_support)

    if market_ok and in_zone and buy_ratio >= buy_pct_req and close_p > open_p:
        sl_dist = float(last_candle['ATR']) * a_m
        if sl_dist > 0:
            return {
                "العملة": name,
                "الحالة": f"شراء مؤكد ({z_type})",
                "سعر الدخول": round(close_p, 4),
                "الهدف (TP)": round(close_p + (sl_dist * rr), 4),
                "وقف الخسارة (SL)": round(close_p - sl_dist, 4),
                "قوة الشراء": f"{buy_ratio:.0f}%"
            }, None

    support_lvl = float(np.min(window_df['Low'].values))
    dist_to_support = ((close_p - support_lvl) / support_lvl) * 100.0
    if market_ok and 0 <= dist_to_support <= 1.5:
        sl_dist = float(last_candle['ATR']) * a_m
        return None, {
            "العملة": name,
            "السعر الحالي": round(close_p, 4),
            "منطقة الشراء (الدعم)": round(support_lvl, 4),
            "البعد عن الدعم": f"{dist_to_support:.2f}%",
            "الهدف المتوقع": round(support_lvl + (sl_dist * rr), 4)
        }
    return None, None

# --- تنفيذ التحليل ---
all_signals = []
live_buys, watchlist = [], []

with st.spinner("جاري تشغيل درع الاتجاه العام وتحليل المحفظة..."):
    btc_regime = fetch_btc_regime()
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                sigs = generate_coin_signals(
                    df_m, name, btc_regime, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support, use_trend_guard
                )
                all_signals.extend(sigs)

                sig, watch = check_live_signals(
                    df_m, name, btc_regime, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support, use_trend_guard
                )
                if sig:
                    live_buys.append(sig)
                if watch:
                    watchlist.append(watch)
        except Exception:
            pass

# نتائج الدورة الأسبوعية الحالية
tot_w, tot_l, tot_o, tot_p, details = simulate_portfolio(all_signals, start_window, end_window, int(max_open_trades))
closed_t = tot_w + tot_l
win_r = (tot_w / closed_t * 100) if closed_t > 0 else 0.0

st.markdown(f"**الربح الصافي للدورة الحالية ({timeframe})**")
st.title(f"$ {tot_p:.2f}")
st.markdown("**نسبة النجاح**")
st.title(f"{win_r:.1f}%")
st.info(f"↑ مغلقة: {closed_t} | مفتوحة: {tot_o}")
st.success(f"✅ {tot_w} ناجحة")
st.error(f"❌ {tot_l} خاسرة")

st.divider()
st.subheader("🎯 التوصيات المستقبلية والإشارات الحية")
if live_buys:
    live_buys.sort(key=lambda x: x["قوة الشراء"], reverse=True)
    st.success(f"أقوى إشارات الشراء الجاهزة الآن (بحد أقصى {max_open_trades} صفقات):")
