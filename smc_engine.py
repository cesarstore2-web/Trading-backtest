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

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.5, start_hour=0, end_hour=23, capital=1000.0, risk_pct=1.0):
    """
    نسخة محسنة من استراتيجية SMC:
    1. قمم وقيعان رئيسية قوية (15 شمعة على HTF) بدون تداخل مستقبلي
    2. كسر كاذب واضح بذيل شمعة قوي (Liquidity Sweep)
    3. تأكيد CHoCH على LTF + انتظار إعادة اختبار منطقة الطلب/العرض (Order Block Retest)
    4. وقف خسارة محمي بـ ATR لمنع ضرب الستوب بالذبذبة
    """
    if df_htf.empty or df_ltf.empty or len(df_htf) < 40:
        return pd.DataFrame()

    df_htf = df_htf.copy()
    
    # حساب ATR لحماية وقف الخسارة من التذبذب العشوائي
    df_htf['tr'] = np.maximum(
        df_htf['high'] - df_htf['low'],
        np.maximum(abs(df_htf['high'] - df_htf['close'].shift(1)), abs(df_htf['low'] - df_htf['close'].shift(1)))
    )
    df_htf['atr'] = df_htf['tr'].rolling(14).mean()
    
    # فلتر الاتجاه العام (EMA 50)
    df_htf['ema50'] = df_htf['close'].ewm(span=50, adjust=False).mean()

    risk_usd = capital * (risk_pct / 100.0)
    reward_usd = risk_usd * rr_ratio

    signals = []
    # نبدأ من الشمعة 20 وننظر للخلف فقط (لمنع أي تداخل مستقبلي)
    for i in range(20, len(df_htf) - 2):
        row = df_htf.iloc[i]
        atr = float(row['atr']) if not pd.isna(row['atr']) else (float(row['high']) - float(row['low']))
        
        # تحديد أقوى قاع وقمة رئيسية في آخر 15 شمعة سابقة (بدون الشمعة الحالية)
        past_window = df_htf.iloc[i-15:i]
        major_low = float(past_window['low'].min())
        major_high = float(past_window['high'].max())

        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        candle_range = float(row['high']) - float(row['low'])
        if candle_range == 0:
            continue

        # ==========================================
        # 1. صفقة الشراء (BUY): سحب سيولة القاع + ذيل سفلي قوي
        # ==========================================
        lower_wick = min(float(row['open']), float(row['close'])) - float(row['low'])
        is_bullish_sweep = (float(row['low']) < major_low) and (float(row['close']) > major_low) and (lower_wick > candle_range * 0.35)

        if is_bullish_sweep:
            # البحث في الفريم الصغير خلال الـ 6 ساعات التالية
            ltf_window = df_ltf[
                (df_ltf['timestamp'] > row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=6))
            ]
            if len(ltf_window) < 6:
                continue

            # 1) تأكيد CHoCH: كسر قمة أول 3 شموع على الفريم الصغير
            sub_high = float(ltf_window['high'].head(3).max())
            choch_break = ltf_window[ltf_window['close'] > sub_high]

            if not choch_break.empty:
                choch_time = choch_break.head(1).squeeze()['timestamp']
                # تحديد منطقة Order Block (منتصف موجة الصعود)
                ob_entry_level = (sub_high + float(row['low'])) / 2.0
                
                # 2) انتظار إعادة الاختبار (Retest) بعد حدوث CHoCH
                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                retest_candles = retest_window[retest_window['low'] <= ob_entry_level]

                if not retest_candles.empty:
                    entry_candle = retest_candles.head(1).squeeze()
                    entry = ob_entry_level
                    sl = float(row['low']) - (atr * 0.3)  # حماية الوقف بـ 0.3 من ATR
                    risk = entry - sl
                    if risk <= 0:
                        continue
                    tp = entry + (risk * rr_ratio)

                    ai_score = compute_ai_quality(df_htf, i, lower_wick / candle_range, float(row['close']) > float(row['ema50']))
                    status, pnl_usd = evaluate_trade_usd(df_ltf, entry_candle['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)

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
        # 2. صفقة البيع (SELL): سحب سيولة القمة + ذيل علوي قوي
        # ==========================================
        upper_wick = float(row['high']) - max(float(row['open']), float(row['close']))
        is_bearish_sweep = (float(row['high']) > major_high) and (float(row['close']) < major_high) and (upper_wick > candle_range * 0.35)

        if is_bearish_sweep:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] > row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=6))
            ]
            if len(ltf_window) < 6:
                continue

            # 1) تأكيد CHoCH: كسر قاع أول 3 شموع على الفريم الصغير
            sub_low = float(ltf_window['low'].head(3).min())
            choch_break = ltf_window[ltf_window['close'] < sub_low]

            if not choch_break.empty:
                choch_time = choch_break.head(1).squeeze()['timestamp']
                ob_entry_level = (sub_low + float(row['high'])) / 2.0

                # 2) انتظار إعادة الاختبار (Retest)
                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                retest_candles = retest_window[retest_window['high'] >= ob_entry_level]

                if not retest_candles.empty:
                    entry_candle = retest_candles.head(1).squeeze()
                    entry = ob_entry_level
                    sl = float(row['high']) + (atr * 0.3)
                    risk = sl - entry
                    if risk <= 0:
                        continue
                    tp = entry - (risk * rr_ratio)

                    ai_score = compute_ai_quality(df_htf, i, upper_wick / candle_range, float(row['close']) < float(row['ema50']))
                    status, pnl_usd = evaluate_trade_usd(df_ltf, entry_candle['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)

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

    # منع تكرار الصفقات المتقاربة لنفس الاتجاه
    df_signals = pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type'])
    return df_signals

def compute_ai_quality(df_htf, idx, wick_ratio, with_trend):
    """نموذج تقييم ذكي يعتمد على حجم السيولة + قوة الذيل + توافق الاتجاه"""
    row = df_htf.iloc[idx]
    
    start_idx = max(0, idx - 12)
    avg_vol = df_htf['volume'].iloc[start_idx:idx].mean()
    vol_ratio = (float(row['volume']) / (float(avg_vol) + 1e-9)) if avg_vol > 0 else 1.0
    vol_score = min(vol_ratio, 2.5) / 2.5 * 35.0

    wick_score = min(wick_ratio, 0.8) / 0.8 * 40.0
    trend_bonus = 20.0 if with_trend else 5.0

    return round(min(max(vol_score + wick_score + trend_bonus, 55.0), 98.5), 1)

def evaluate_trade_usd(df_ltf, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    """تقييم دقيق للصفقة بعد تفعيل أمر إعادة الاختبار"""
    future = df_ltf[df_ltf['timestamp'] > entry_time].head(200)

    for _, bar in future.iterrows():
        if direction == "BUY":
            if float(bar['low']) <= sl:
                return "خاسرة", -risk_usd
            if float(bar['high']) >= tp:
                return "رابحة", reward_usd
        else:
            if float(bar['high']) >= sl:
                return "خاسرة", -risk_usd
            if float(bar['low']) <= tp:
                return "رابحة", reward_usd
                
    return "جارية", 0.0
