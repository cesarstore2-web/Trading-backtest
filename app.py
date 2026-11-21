import streamlit as st
import ccxt
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from lightgbm import LGBMClassifier

st.set_page_config(page_title="ماسح AI والمحفظتين: USDT & MAD", layout="wide")

MOROCCO_TZ = ZoneInfo("Africa/Casablanca")
now_ma = datetime.now(MOROCCO_TZ)

is_weekday = now_ma.weekday() < 5
market_open_time = now_ma.replace(hour=9, minute=30, second=0, microsecond=0)
market_close_time = now_ma.replace(hour=15, minute=30, second=0, microsecond=0)
is_casa_open = is_weekday and (market_open_time <= now_ma <= market_close_time)

st.title("🤖 ماسح AI والمحفظة المالية (USDT للكريبتو & MAD للبورصة)")
st.caption("استراتيجية: كسر ترند RSI | تقييم الذكاء الاصطناعي: +55% | فصل كامل بين محفظة USDT ومحفظة MAD")

st.info(
    f"🇲🇦 التوقيت الحالي في المغرب: **{now_ma.strftime('%Y-%m-%d %H:%M')}** | "
    f"بورصة الدار البيضاء: **{'🟢 مفتوحة' if is_casa_open else '🔴 مغلقة'}**"
)

CRYPTO_GOLD_ASSETS = [
    ("BTC/USDT", "البيتكوين (BTC)", "USDT"),
    ("ETH/USDT", "إيثيريوم (ETH)", "USDT"),
    ("SOL/USDT", "سولانا (SOL)", "USDT"),
    ("XRP/USDT", "ريبل (XRP)", "USDT"),
    ("ADA/USDT", "كاردانو (ADA)", "USDT"),
    ("LTC/USDT", "لايتكوين (LTC)", "USDT"),
    ("PAXG/USDT", "الذهب الرقمي (PAXG)", "USDT"),
    ("XAUT/USDT", "الذهب (Tether Gold)", "USDT")
]

CASABLANCA_STOCKS = [
    ("IAM", "اتصالات المغرب (IAM)", "MAD"),
    ("ATW", "التجاري وفا بنك (ATW)", "MAD"),
    ("MSA", "مرسى المغرب (MSA)", "MAD"),
    ("AKT", "أكديطال (AKT)", "MAD"),
    ("MNG", "مناجم (MNG)", "MAD"),
    ("BCP", "البنك الشعبي المركزي (BCP)", "MAD"),
    ("BOA", "بنك أفريقيا (BOA)", "MAD")
]

@st.cache_data(ttl=900)
def fetch_crypto_gold(symbol, timeframe='1h', limit=750):
    exchange_ids = ['kraken', 'gate', 'kucoin', 'okx', 'coinbase']
    for ex_id in exchange_ids:
        try:
            if not hasattr(ccxt, ex_id):
                continue
            exchange = getattr(ccxt, ex_id)({'enableRateLimit': True})
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if bars and len(bars) > 200:
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert(MOROCCO_TZ)
                return df
        except Exception:
            continue
    return None

@st.cache_data(ttl=1800)
def fetch_casablanca_stock(ticker, market_is_open):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    suffixes = ['.CS', '.PA'] if ticker == 'IAM' else ['.CS']
    for suf in suffixes:
        try:
            hist_url = f"https://yahoo.com{ticker}{suf}?interval=1d&range=3y"
            hr = requests.get(hist_url, headers=headers, timeout=8)
            if hr.status_code == 200:
                hjson = hr.json()
                res = hjson['chart']['result'][0]
                quote = res['indicators']['quote'][0]
                df = pd.DataFrame({
                    'timestamp': pd.to_datetime(res['timestamp'], unit='s', utc=True).dt.tz_convert(MOROCCO_TZ),
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'close': quote['close'],
                    'volume': quote['volume']
                }).dropna()
                if len(df) > 200:
                    last_candle_date = df['timestamp'].iloc[-1].date()
                    if market_is_open and last_candle_date == now_ma.date():
                        df = df.iloc[:-1]
                    return df
        except Exception:
            continue
    return None

def detect_rsi_trendline_strategy(df):
    df = df.copy().reset_index(drop=True)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['dist_ema20'] = (df['close'] - df['ema_20']) / df['ema_20']
    df['dist_ema50'] = (df['close'] - df['ema_50']) / df['ema_50']
    df['rsi_slope'] = df['rsi'].diff(3)
    df['vol_ratio'] = df['volume'] / (df['volume'].rolling(20).mean() + 1e-9)
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    df['volatility'] = df['atr'] / df['close']

    df['swing_low'] = df['low'][(df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))]
    df['swing_high'] = df['high'][(df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))]

    signals = np.zeros(len(df))
    stop_losses = np.full(len(df), np.nan)
    take_profits = np.full(len(df), np.nan)
    targets = np.full(len(df), np.nan)
    pct_returns = np.full(len(df), 0.0)
    lookback = 20

    for i in range(lookback + 15, len(df)):
        window = df.iloc[i - lookback : i]
        curr_close = df.loc[i, 'close']
        prev_close = df.loc[i - 1, 'close']
        curr_rsi = df.loc[i, 'rsi']
        prev_rsi = df.loc[i - 1, 'rsi']
        atr = df.loc[i, 'atr']

        s_lows = window.dropna(subset=['swing_low'])
        if len(s_lows) >= 2:
            p1, p2 = s_lows.iloc[-2], s_lows.iloc[-1]
            if p2['low'] > p1['low'] and p2['rsi'] > p1['rsi']:
                slope_p = (p2['low'] - p1['low']) / (p2.name - p1.name)
                trend_p_curr = p2['low'] + slope_p * (i - p2.name)
                trend_p_prev = p2['low'] + slope_p * ((i - 1) - p2.name)
                slope_r = (p2['rsi'] - p1['rsi']) / (p2.name - p1.name)
                trend_r_curr = p2['rsi'] + slope_r * (i - p2.name)
                trend_r_prev = p2['rsi'] + slope_r * ((i - 1) - p2.name)

                if window['rsi'].max() >= 63 and (prev_rsi >= trend_r_prev) and (curr_rsi < trend_r_curr) and (prev_close >= trend_p_prev) and (curr_close < trend_p_curr):
                    recent_high = df.iloc[i - 10 : i + 1]['high'].max()
                    sl = recent_high + (0.2 * atr)
                    risk = sl - curr_close
                    if risk > 0:
                        signals[i] = -1
                        stop_losses[i] = sl
                        take_profits[i] = curr_close - (2.0 * risk)

        if signals[i] == 0:
            s_highs = window.dropna(subset=['swing_high'])
            if len(s_highs) >= 2:
                p1, p2 = s_highs.iloc[-2], s_highs.iloc[-1]
                if p2['high'] < p1['high'] and p2['rsi'] < p1['rsi']:
                    slope_p = (p2['high'] - p1['high']) / (p2.name - p1.name)
                    trend_p_curr = p2['high'] + slope_p * (i - p2.name)
                    trend_p_prev = p2['high'] + slope_p * ((i - 1) - p2.name)
                    slope_r = (p2['rsi'] - p1['rsi']) / (p2.name - p1.name)
                    trend_r_curr = p2['rsi'] + slope_r * (i - p2.name)
                    trend_r_prev = p2['rsi'] + slope_r * ((i - 1) - p2.name)

                    if window['rsi'].min() <= 37 and (prev_rsi <= trend_r_prev) and (curr_rsi > trend_r_curr) and (prev_close <= trend_p_prev) and (curr_close > trend_p_curr):
                        recent_low = df.iloc[i - 10 : i + 1]['low'].min()
                        sl = recent_low - (0.2 * atr)
                        risk = curr_close - sl
                        if risk > 0:
                            signals[i] = 1
                            stop_losses[i] = sl
                            take_profits[i] = curr_close + (2.0 * risk)

        if signals[i] != 0 and i < len(df) - 1:
            future = df.iloc[i + 1 : min(i + 18, len(df))]
            sl, tp = stop_losses[i], take_profits[i]
            entry = df.loc[i, 'close']
            outcome = np.nan
            ret = 0.0
            for _, f_row in future.iterrows():
                if signals[i] == -1:
                    if f_row['high'] >= sl:
                        outcome = 0
                        ret = -((sl - entry) / entry)
                        break
                    if f_row['low'] <= tp:
                        outcome = 1
                        ret = ((entry - tp) / entry)
                        break
                elif signals[i] == 1:
                    if f_row['low'] <= sl:
                        outcome = 0
                        ret = -((entry - sl) / entry)
                        break
                    if f_row['high'] >= tp:
                        outcome = 1
                        ret = ((tp - entry) / entry)
                        break
            targets[i] = outcome
            pct_returns[i] = ret

    df['signal'] = signals
    df['stop_loss'] = stop_losses
    df['take_profit'] = take_profits
    df['target'] = targets
    df['pct_return'] = pct_returns
    return df
def analyze_asset_with_portfolio(df, symbol, label, currency, tf_label, trade_mode, leverage, min_conf=55.0):
    df = detect_rsi_trendline_strategy(df)
    features = ['signal', 'rsi', 'rsi_slope', 'dist_ema20', 'dist_ema50', 'vol_ratio', 'volatility']
    
    if trade_mode == "سبوت (Spot - شراء فقط)":
        valid_hist = df.iloc[:-1][(df['signal'] == 1)].dropna(subset=['target'] + features)
    else:
        valid_hist = df.iloc[:-1][(df['signal'] != 0)].dropna(subset=['target'] + features)

    if len(valid_hist) < 10:
        return None

    one_month_ago = now_ma - timedelta(days=30)
    train_df = valid_hist[valid_hist['timestamp'] < one_month_ago]
    month_df = valid_hist[valid_hist['timestamp'] >= one_month_ago]

    if len(train_df) < 8:
        split_idx = max(6, int(len(valid_hist) * 0.7))
        train_df = valid_hist.iloc[:split_idx]
        month_df = valid_hist.iloc[split_idx:]

    model = LGBMClassifier(n_estimators=80, learning_rate=0.05, max_depth=3, random_state=42, verbose=-1)
    model.fit(train_df[features], train_df['target'].astype(int))

    month_trades = []
    if len(month_df) > 0:
        probs = model.predict_proba(month_df[features])[:, 1] * 100
        for idx_m, (_, row) in enumerate(month_df.iterrows()):
            if probs[idx_m] >= min_conf:
                eff_lev = 1 if trade_mode == "سبوت (Spot - شراء فقط)" else leverage
                leveraged_ret = max(-1.0, row['pct_return'] * eff_lev)
                month_trades.append({
                    "won": int(row['target']) == 1,
                    "leveraged_ret": leveraged_ret,
                    "currency": currency
                })

    curr = df.iloc[-1]
    sig = int(curr['signal'])
    future_opp = None
    allowed_signal = (sig == 1) if trade_mode == "سبوت (Spot - شراء فقط)" else (sig != 0)

    if allowed_signal:
        curr_X = df.iloc[-1:][features]
        ai_conf = float(model.predict_proba(curr_X)[0][1]) * 100
        if ai_conf >= min_conf:
            entry_price = float(curr['close'])
            decimals = 2 if entry_price >= 10 else (4 if entry_price >= 0.1 else 5)
            direction = "بيع (SHORT) 🔴" if sig == -1 else "شراء (LONG) 🟢"
            eff_lev = 1 if trade_mode == "سبوت (Spot - شراء فقط)" else leverage
            
            future_opp = {
                "الأصل": label,
                "الرمز": symbol,
                "الفريم": tf_label,
                "النظام": f"Futures {eff_lev}x" if eff_lev > 1 else "Spot 1x",
                "الاتجاه": direction,
                "تقييم AI (%)": round(ai_conf, 1),
                "سعر الدخول": round(entry_price, decimals),
                "وقف الخسارة": round(float(curr['stop_loss']), decimals),
                "جني الأرباح (1:2)": round(float(curr['take_profit']), decimals),
                "العملة": currency
            }

    return {"month_trades": month_trades, "future_opp": future_opp}

def render_portfolio_dashboard(title, trades_list, capital, alloc_pct, currency_code):
    st.subheader(title)
    total_trades = len(trades_list)
    winning_trades = sum(1 for t in trades_list if t["won"])
    losing_trades = total_trades - winning_trades
    win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0

    trade_size = capital * (alloc_pct / 100.0)
    gross_profit = sum(trade_size * t["leveraged_ret"] for t in trades_list if t["leveraged_ret"] > 0)
    gross_loss = sum(trade_size * t["leveraged_ret"] for t in trades_list if t["leveraged_ret"] < 0)
    net_profit = gross_profit + gross_loss
    final_balance = capital + net_profit

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("نسبة النجاح", f"{win_rate}%")
    m2.metric("عدد الصفقات", f"{total_trades} صفقة")
    m3.metric("الصفقات الرابحة", f"✅ {winning_trades}")
    m4.metric("الصفقات الخاسرة", f"❌ {losing_trades}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("إجمالي الأرباح", f"+{round(gross_profit, 2)} {currency_code}")
    p2.metric("إجمالي الخسائر", f"{round(gross_loss, 2)} {currency_code}")
    p3.metric("صافي في الأرباح", f"{'+' if net_profit >= 0 else ''}{round(net_profit, 2)} {currency_code}")
    p4.metric("الرصيد النهائي للمحفظة", f"{round(final_balance, 2)} {currency_code}")

scope = st.radio(
    "اختر نطاق المسح التلقائي:",
    [
        "الكل (كريبتو + ذهب بـ USDT & بورصة الدار البيضاء بـ MAD)",
        "العملات الرقمية والذهب فقط (USDT)",
        "بورصة الدار البيضاء فقط (MAD)"
    ],
    horizontal=True
)

col_usdt, col_mad = st.columns(2)

with col_usdt:
    st.markdown("### 💵 محفظة الكريبتو والذهب (USDT)")
    trade_mode_usdt = st.selectbox(
        "نظام التداول (USDT):",
        ["عقود آجلة (Futures - شراء وبيع)", "سبوت (Spot - شراء فقط)"]
    )
    if trade_mode_usdt == "سبوت (Spot - شراء فقط)":
        leverage_usdt = 1
        st.number_input("الرافعة المالية (USDT):", value=1, disabled=True)
    else:
        leverage_usdt = st.slider("الرافعة المالية (USDT):", min_value=2, max_value=20, value=5)
    capital_usdt = st.number_input("رأس المال (USDT):", min_value=100.0, value=1000.0, step=100.0)
    alloc_pct_usdt = st.slider("حجم الصفقة (% من محفظة USDT):", min_value=5, max_value=50, value=10)

with col_mad:
    st.markdown("### 🇲🇦 محفظة بورصة الدار البيضاء (MAD)")
    st.selectbox("نظام التداول (MAD):", ["سبوت (Spot - شراء فقط بدون رافعة)"], disabled=True)
    st.number_input("الرافعة المالية (MAD):", value=1, disabled=True)
    capital_mad = st.number_input("رأس المال (MAD):", min_value=1000.0, value=10000.0, step=1000.0)
    alloc_pct_mad = st.slider("حجم الصفقة (% من محفظة MAD):", min_value=5, max_value=50, value=15)

MIN_CONFIDENCE = 55.0

if st.button("تشغيل المسح وحساب الأرباح والخسائر (USDT و MAD) 🚀", type="primary"):
    usdt_month_trades = []
    mad_month_trades = []
    future_opportunities = []
    
    scan_tasks = []
    if "الرقمية" in scope or "الكل" in scope:
        for sym, lbl, cur in CRYPTO_GOLD_ASSETS:
            for tf in ['15m', '30m', '1h', '4h']:
                scan_tasks.append((sym, lbl, cur, tf, False))
                
    if "الدار البيضاء" in scope or "الكل" in scope:
        for sym, lbl, cur in CASABLANCA_STOCKS:
            scan_tasks.append((sym, lbl, cur, '1d', True))

    progress = st.progress(0)
    status = st.empty()

    for idx, (sym, lbl, cur, tf, is_stock) in enumerate(scan_tasks):
        status.text(f"⏳ جاري مسح {lbl} على فريم {tf.upper()}...")
        
        if is_stock:
            df = fetch_casablanca_stock(sym, is_casa_open)
            mode_for_asset = "سبوت (Spot - شراء فقط)"
            lev_for_asset = 1
        else:
            df = fetch_crypto_gold(sym, timeframe=tf)
            mode_for_asset = trade_mode_usdt
            lev_for_asset = leverage_usdt

        if df is not None:
            res = analyze_asset_with_portfolio(
                df, sym, lbl, cur, tf.upper(), mode_for_asset, lev_for_asset, min_conf=MIN_CONFIDENCE
            )
            if res:
                if is_stock:
                    mad_month_trades.extend(res["month_trades"])
                else:
                    usdt_month_trades.extend(res["month_trades"])
                    
                if res["future_opp"]:
                    future_opportunities.append(res["future_opp"])

        progress.progress((idx + 1) / len(scan_tasks))

    status.empty()
    st.divider()

    if "الرقمية" in scope or "الكل" in scope:
        render_portfolio_dashboard(
            "📊 سجل أداء الكريبتو والذهب (آخر 30 يوماً بالدولار الرقمي USDT)",
            usdt_month_trades, capital_usdt, alloc_pct_usdt, "USDT"
        )
        st.divider()

    if "الدار البيضاء" in scope or "الكل" in scope:
        render_portfolio_dashboard(
            "📊 سجل أداء بورصة الدار البيضاء (آخر 30 يوماً بالدرهم المغربي MAD)",
            mad_month_trades, capital_mad, alloc_pct_mad, "MAD"
        )
        st.divider()

    st.subheader("🎯 التوصيات المستقبلية النشطة الآن (مرتبة من الأعلى تقييماً +55%)")
    if future_opportunities:
        df_opps = pd.DataFrame(future_opportunities).sort_values(by="تقييم AI (%)", ascending=False).reset_index(drop=True)
        st.success(f"تم رصد {len(df_opps)} فرصة نشطة بتقييم 55% أو أكثر:")
        st.dataframe(df_opps, use_container_width=True)
    else:
        st.warning("⏳ لا توجد توصيات مستقبلية تستوفي شروط كسر ترند RSI وتقييم +55% في هذه اللحظة.")
