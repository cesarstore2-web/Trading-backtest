import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="ماسح ضغط الشراء والدعوم", layout="centered")

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

# القيم الافتراضية المعتمدة
timeframe = "1h"
min_buy_ratio = 80
zone_lookback = 100
atr_len = 13
atr_mult = 2.3
rr_ratio = 2.3
use_demand = False
use_support = True

# مربعات تفعيل الميزات الثلاث (القيم الافتراضية)
use_breakeven = True
use_circuit_breaker = True
use_soft_bounce = False

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

    st.markdown("**ميزات التحسين والحماية (قابلة للتفعيل المستقل)**")
    use_breakeven = st.checkbox("1. تأمين الدخول عند ربح 1:1 (Break-Even)", value=True)
    use_circuit_breaker = st.checkbox("2. قاطع الحماية (إيقاف العملة بعد خسارتين في الأسبوع)", value=True)
    use_soft_bounce = st.checkbox("3. فلتر ارتداد مرن (إغلاق فوق إغلاق الشمعة السابقة)", value=False)

    st.markdown("**مصدر مناطق الدخول**")
    z1, z2 = st.columns(2)
    with z1:
        use_demand = st.checkbox("مناطق الطلب (Demand Zones)", value=False)
    with z2:
        use_support = st.checkbox("مستويات الدعم (Support Levels)", value=True)
    st.divider()

st.caption(f"العملات: {len(HALAL_COINS)} عملة نقية | الدورة: {start_window.strftime('%Y-%m-%d %H:%M')} إلى {end_window.strftime('%Y-%m-%d %H:%M')} (UTC)")

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

def run_backtest(df, start_dt, end_dt, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support, en_be, en_cb, en_sb):
    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return 0, 0, 0, 0.0

    df['ATR'] = calc_atr(df, a_len)
    df['Vol_MA'] = df['Volume'].rolling(window=10).mean()
    wins, losses, open_t, profit, fee = 0, 0, 0, 0.0, 0.001
    consecutive_losses = 0

    i = min_bars
    while i < len(df) - 1:
        candle_time = df.index[i]
        if candle_time < start_dt or candle_time > end_dt:
            i += 1
            continue

        # الميزة 2: قاطع الحماية (توقف العملة عن التداول لبقية الأسبوع بعد خسارتين متتاليتين)
        if en_cb and consecutive_losses >= 2:
            break

        c_row = df.iloc[i]
        p_row = df.iloc[i - 1]
        if pd.isna(c_row['ATR']) or pd.isna(c_row['Vol_MA']):
            i += 1
            continue

        high_p, low_p = float(c_row['High']), float(c_row['Low'])
        close_p, open_p = float(c_row['Close']), float(c_row['Open'])
        vol = float(c_row['Volume'])
        candle_range = high_p - low_p

        buy_pressure_ratio = ((close_p - low_p) / candle_range) * 100.0 if (candle_range > 0 and vol > 0) else 50.0
        strong_buying = (buy_pressure_ratio >= buy_pct_req) and (close_p > open_p) and (vol >= float(c_row['Vol_MA']) * 0.8)

        # الميزة 3: فلتر الارتداد المرن (إغلاق فوق إغلاق الشمعة السابقة)
        if en_sb and close_p <= float(p_row['Close']):
            i += 1
            continue

        if strong_buying:
            window_df = df.iloc[i - lookback : i]
            in_zone, _ = check_zone_touch(window_df, c_row, en_demand, en_support)

            if in_zone:
                entry = close_p
                sl_dist = float(c_row['ATR']) * a_m
                if sl_dist > 0:
                    sl = entry - sl_dist
                    tp = entry + (sl_dist * rr)
                    be_trigger = entry + sl_dist
                    be_activated = False
                    closed = False

                    for j in range(i + 1, len(df)):
                        if df.index[j] > end_dt:
                            break
                        fut = df.iloc[j]
                        fut_low = float(fut['Low'])
                        fut_high = float(fut['High'])

                        # الميزة 1: تأمين الدخول عند ربح 1:1
                        if en_be and not be_activated and fut_high >= be_trigger:
                            be_activated = True
                            sl = entry * 1.002

                        if fut_low <= sl:
                            if be_activated:
                                wins += 1
                                consecutive_losses = 0
                            else:
                                losses += 1
                                consecutive_losses += 1
                                profit -= (TRADE_AMOUNT * (sl_dist / entry) + TRADE_AMOUNT * fee * 2)
                            closed = True
                            i = j
                            break
                        elif fut_high >= tp:
                            wins += 1
                            consecutive_losses = 0
                            profit += (TRADE_AMOUNT * ((tp - entry) / entry) - TRADE_AMOUNT * fee * 2)
                            closed = True
                            i = j
                            break
                    if not closed:
                        open_t += 1
                        break
        i += 1
    return wins, losses, open_t, profit

def check_live_signals(df, name, buy_pct_req, lookback, a_len, a_m, rr, en_demand, en_support, en_sb):
    min_bars = max(lookback, a_len) + 5
    if len(df) < min_bars:
        return None, None

    df['ATR'] = calc_atr(df, a_len)
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    window_df = df.iloc[-lookback - 1 : -1]

    high_p, low_p = float(last_candle['High']), float(last_candle['Low'])
    close_p, open_p = float(last_candle['Close']), float(last_candle['Open'])
    candle_range = high_p - low_p

    buy_ratio = ((close_p - low_p) / candle_range * 100.0) if candle_range > 0 else 50.0
    in_zone, z_type = check_zone_touch(window_df, last_candle, en_demand, en_support)
    bounce_ok = (close_p > float(prev_candle['Close'])) if en_sb else True

    if in_zone and buy_ratio >= buy_pct_req and close_p > open_p and bounce_ok:
        sl_dist = float(last_candle['ATR']) * a_m
        if sl_dist > 0:
            return {
                "العملة": name,
                "الحالة": f"شراء مؤكد ({z_type})",
                "سعر الدخول": round(close_p, 4),
                "الهدف (TP)": round(close_p + (sl_dist * rr), 4),
                "وقف الخسارة (SL)": round(close_p - sl_dist, 4),
                "نسبة الشراء": f"{buy_ratio:.0f}%"
            }, None

    support_lvl = float(np.min(window_df['Low'].values))
    dist_to_support = ((close_p - support_lvl) / support_lvl) * 100.0
    if 0 <= dist_to_support <= 1.5:
        sl_dist = float(last_candle['ATR']) * a_m
        return None, {
            "العملة": name,
            "السعر الحالي": round(close_p, 4),
            "منطقة الشراء (الدعم)": round(support_lvl, 4),
            "البعد عن الدعم": f"{dist_to_support:.2f}%",
            "الهدف المتوقع": round(support_lvl + (sl_dist * rr), 4)
        }
    return None, None

tot_w, tot_l, tot_o, tot_p, details = 0, 0, 0, 0.0, []
live_buys, watchlist = [], []
weekly_stats = {w_label: {"ناجحة": 0, "خاسرة": 0, "مفتوحة": 0, "الربح الصافي ($)": 0.0, "الفترة": f"{ws.strftime('%m-%d')} إلى {we.strftime('%m-%d')}"} for w_label, ws, we in month_weeks}

with st.spinner("جاري فحص العملات الـ 22 وتطبيق ميزات الحماية..."):
    for ticker, name in HALAL_COINS.items():
        try:
            df_m = fetch_data(ticker, timeframe)
            if not df_m.empty:
                w, l, o, p = run_backtest(
                    df_m.copy(), start_window, end_window, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support,
                    use_breakeven, use_circuit_breaker, use_soft_bounce
                )
                tot_w += w
                tot_l += l
                tot_o += o
                tot_p += p
                if (w + l + o) > 0:
                    details.append({"العملة": name, "ناجحة": w, "خاسرة": l, "مفتوحة": o, "الربح الصافي ($)": round(p, 2)})

                sig, watch = check_live_signals(
                    df_m.copy(), name, int(min_buy_ratio), int(zone_lookback),
                    int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support, use_soft_bounce
                )
                if sig:
                    live_buys.append(sig)
                if watch:
                    watchlist.append(watch)

                for w_label, ws, we in month_weeks:
                    ww, wl, wo, wp = run_backtest(
                        df_m.copy(), ws, we, int(min_buy_ratio), int(zone_lookback),
                        int(atr_len), float(atr_mult), float(rr_ratio), use_demand, use_support,
                        use_breakeven, use_circuit_breaker, use_soft_bounce
                    )
                    weekly_stats[w_label]["ناجحة"] += ww
                    weekly_stats[w_label]["خاسرة"] += wl
                    weekly_stats[w_label]["مفتوحة"] += wo
                    weekly_stats[w_label]["الربح الصافي ($)"] = round(weekly_stats[w_label]["الربح الصافي ($)"] + wp, 2)
        except Exception:
            pass

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
    st.success("إشارات شراء جاهزة الآن:")
    st.dataframe(pd.DataFrame(live_buys), use_container_width=True, hide_index=True)
else:
    st.caption("لا توجد إشارة دخول مكتملة في هذه اللحظة؛ راقب القائمة أدناه:")

if watchlist:
    st.markdown("**عملات تقترب من مناطق الشراء (قائمة المراقبة):**")
    st.dataframe(pd.DataFrame(watchlist), use_container_width=True, hide_index=True)
elif not live_buys:
    st.info("جميع العملات تتحرك حالياً بعيداً عن مستويات الدعم الرئيسية.")

st.divider()
st.subheader(f"📊 السجل الأسبوعي للشهر الحالي ({now_ma.strftime('%B %Y')})")
weekly_rows = []
total_month_profit = 0.0
for w_label, stats in weekly_stats.items():
    total_month_profit += stats["الربح الصافي ($)"]
    weekly_rows.append({
        "الأسبوع": w_label,
        "الفترة (UTC)": stats["الفترة"],
        "ناجحة": stats["ناجحة"],
        "خاسرة": stats["خاسرة"],
        "مفتوحة": stats["مفتوحة"],
