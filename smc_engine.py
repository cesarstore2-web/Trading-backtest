import yfinance as yf
import pandas as pd
import numpy as np

ASSETS_MAP = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "XRPUSDT": "XRP-USD",
    "XLMUSDT": "XLM-USD",
    "ZECUSDT": "ZEC-USD",
    "HBARUSDT": "HBAR-USD",
    "ADAUSDT": "ADA-USD",
    "LTCUSDT": "LTC-USD",
    "PAXGUSDT": "PAXG-USD",
    "XAUUSDT (الذهب)": "GC=F"
}

def fetch_data(ticker, interval="1h", period="60d"):
    """جلب بيانات الشموع وتنظيفها"""
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty:
            return pd.DataFrame()
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.reset_index()
        df.rename(columns={
            'Datetime': 'timestamp', 'Date': 'timestamp',
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume'
        }, inplace=True)
        
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].dropna()
    except Exception:
        return pd.DataFrame()

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.0, start_hour=0, end_hour=23, capital=1000.0, risk_pct=1.0):
    """
    نسخة احترافية عالية الدقة من استراتيجية SMC:
    1. التداول حصرياً مع الاتجاه المؤسسي العام (EMA 100) لمنع الصفقات المعاكسة
    2. سحب سيولة قوي (Liquidity Sweep) لقاع/قمة 20 شمعة على الفريم الكبير
    3. تأكيد CHoCH + شمعة انعكاسية عند إعادة اختبار Order Block على الفريم الصغير
    4. نظام تأمين الصفقة (Break-Even) عند تحقيق 1:1 لحماية رأس المال
    """
    if df_htf.empty or df_ltf.empty or len(df_htf) < 105:
        return pd.DataFrame()

    df_htf = df_htf.copy()
    
    # حساب ATR لحماية وقف الخسارة
    df_htf['tr'] = np.maximum(
        df_htf['high'] - df_htf['low'],
        np.maximum(abs(df_htf['high'] - df_htf['close'].shift(1)), abs(df_htf['low'] - df_htf['close'].shift(1)))
    )
    df_htf['atr'] = df_htf['tr'].rolling(14).mean()
    
    # المتوسط المؤسسي لتحديد الاتجاه العام الصحيح
    df_htf['ema100'] = df_htf['close'].ewm(span=100, adjust=False).mean()

    risk_usd = capital * (risk_pct / 100.0)
    reward_usd = risk_usd * rr_ratio

    signals = []
    for i in range(100, len(df_htf) - 2):
        row = df_htf.iloc[i]
        atr = float(row['atr']) if not pd.isna(row['atr']) else (float(row['high']) - float(row['low']))
        ema100 = float(row['ema100'])
        
        past_window = df_htf.iloc[i-20:i]
        major_low = float(past_window['low'].min())
        major_high = float(past_window['high'].max())

        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        candle_range = float(row['high']) - float(row['low'])
        if candle_range == 0:
            continue

        # ==========================================
        # 1. صفقة الشراء (BUY): فقط في الاتجاه الصاعد (فوق EMA 100)
        # ==========================================
        lower_wick = min(float(row['open']), float(row['close'])) - float(row['low'])
        is_bullish_sweep = (
            (float(row['close']) > ema100) and
            (float(row['low']) < major_low) and
            (float(row['close']) > major_low) and
            (lower_wick >= candle_range * 0.40)
        )

        if is_bullish_sweep:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] > row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 6:
                continue

            sub_high = float(ltf_window['high'].head(3).max())
            choch_break = ltf_window[ltf_window['close'] > sub_high]

            if not choch_break.empty:
                choch_time = choch_break.head(1).squeeze()['timestamp']
                ob_zone = (sub_high + float(row['low'])) / 2.0
                
                # انتظار إعادة الاختبار + إغلاق شمعة صاعدة تؤكد الارتداد
                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                valid_entries = retest_window[(retest_window['low'] <= ob_zone) & (retest_window['close'] > retest_window['open'])]

                if not valid_entries.empty:
                    entry_candle = valid_entries.head(1).squeeze()
                    entry = float(entry_candle['close'])
                    sl = float(row['low']) - (atr * 0.4)
                    risk = entry - sl
                    if risk <= 0:
                        continue
                    tp = entry + (risk * rr_ratio)

                    ai_score = compute_ai_quality(df_htf, i, lower_wick / candle_range)
                    status, pnl_usd = evaluate_trade_with_be(df_ltf, entry_candle['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)

                    signals.append({
                        'timestamp': entry_candle['timestamp'],
                        'type': 'شراء (BUY)',
                        'entry': round(entry, 4),
                        'sl': round(sl, 4),
                        'tp': round(tp, 4),
                        'ai_score': ai_score,
                        'status': status,
                        'pnl_usd': round(pnl_usd, 2)
                    })

        # ==========================================
        # 2. صفقة البيع (SELL): فقط في الاتجاه الهابط (تحت EMA 100)
        # ==========================================
        upper_wick = float(row['high']) - max(float(row['open']), float(row['close']))
        is_bearish_sweep = (
            (float(row['close']) < ema100) and
            (float(row['high']) > major_high) and
            (float(row['close']) < major_high) and
            (upper_wick >= candle_range * 0.40)
        )

        if is_bearish_sweep:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] > row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 6:
                continue

            sub_low = float(ltf_window['low'].head(3).min())
            choch_break = ltf_window[ltf_window['close'] < sub_low]

            if not choch_break.empty:
                choch_time = choch_break.head(1).squeeze()['timestamp']
                ob_zone = (sub_low + float(row['high'])) / 2.0

                # انتظار إعادة الاختبار + إغلاق شمعة هابطة تؤكد الارتداد
                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                valid_entries = retest_window[(retest_window['high'] >= ob_zone) & (retest_window['close'] < retest_window['open'])]

                if not valid_entries.empty:
                    entry_candle = valid_entries.head(1).squeeze()
                    entry = float(entry_candle['close'])
                    sl = float(row['high']) + (atr * 0.4)
                    risk = sl - entry
                    if risk <= 0:
                        continue
                    tp = entry - (risk * rr_ratio)

                    ai_score = compute_ai_quality(df_htf, i, upper_wick / candle_range)
                    status, pnl_usd = evaluate_trade_with_be(df_ltf, entry_candle['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)

                    signals.append({
                        'timestamp': entry_candle['timestamp'],
                        'type': 'بيع (SELL)',
                        'entry': round(entry, 4),
                        'sl': round(sl, 4),
                        'tp': round(tp, 4),
                        'ai_score': ai_score,
                        'status': status,
                        'pnl_usd': round(pnl_usd, 2)
                    })

    if not signals:
        return pd.DataFrame()

    return pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type'])

def compute_ai_quality(df_htf, idx, wick_ratio):
    """تقييم الذكاء الاصطناعي بناءً على زخم السيولة وقوة الرفض السعري"""
    row = df_htf.iloc[idx]
    start_idx = max(0, idx - 15)
    avg_vol = df_htf['volume'].iloc[start_idx:idx].mean()
    vol_ratio = (float(row['volume']) / (float(avg_vol) + 1e-9)) if avg_vol > 0 else 1.0
    vol_score = min(vol_ratio, 2.5) / 2.5 * 45.0
    wick_score = min(wick_ratio, 0.85) / 0.85 * 50.0
    return round(min(max(vol_score + wick_score + 15.0, 65.0), 99.0), 1)

def evaluate_trade_with_be(df_ltf, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    """تقييم الصفقة مع ميزة تأمين الدخول (Break-Even) عند تحقيق 1:1 لحماية الأرباح"""
    future = df_ltf[df_ltf['timestamp'] > entry_time].head(250)
    current_sl = sl
    risk_dist = abs(entry - sl)

    for _, bar in future.iterrows():
        if direction == "BUY":
            # تأمين الصفقة على نقطة الدخول إذا حققت ربح 1:1
            if float(bar['high']) >= entry + risk_dist:
                current_sl = entry
            if float(bar['low']) <= current_sl:
                return ("مؤمّنة (0$)", 0.0) if current_sl == entry else ("خاسرة", -risk_usd)
            if float(bar['high']) >= tp:
                return "رابحة", reward_usd
        else:
            if float(bar['low']) <= entry - risk_dist:
                current_sl = entry
            if float(bar['high']) >= current_sl:
                return ("مؤمّنة (0$)", 0.0) if current_sl == entry else ("خاسرة", -risk_usd)
            if float(bar['low']) <= tp:
                return "رابحة", reward_usd
                
    return "جارية", 0.0
