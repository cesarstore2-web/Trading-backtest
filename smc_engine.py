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
    """جلب وتنظيف بيانات السوق"""
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

def compute_rsi(series, period=14):
    """حساب مؤشر القوة النسبية لتجنب الدخول في القمم والقيعان المتشبعة"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def detect_fvg(df_ltf, direction):
    """اكتشاف فجوة القيمة العادلة (Fair Value Gap) كدليل على دخول سيولة الحيتان"""
    if len(df_ltf) < 4:
        return False, 0.0
    
    for idx in range(2, len(df_ltf)):
        c1 = df_ltf.iloc[idx - 2]
        c3 = df_ltf.iloc[idx]
        if direction == "BUY":
            if float(c3['low']) > float(c1['high']):
                fvg_mid = (float(c3['low']) + float(c1['high'])) / 2.0
                return True, fvg_mid
        else:
            if float(c3['high']) < float(c1['low']):
                fvg_mid = (float(c3['high']) + float(c1['low'])) / 2.0
                return True, fvg_mid
    return False, 0.0

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.0, start_hour=0, end_hour=23, capital=1000.0, risk_pct=1.0):
    """
    محرك التداول المؤسسي المتكامل (Whale Footprint + SMC + FVG + AI)
    """
    if df_htf.empty or df_ltf.empty or len(df_htf) < 105:
        return pd.DataFrame()

    df_htf = df_htf.copy()
    
    df_htf['tr'] = np.maximum(
        df_htf['high'] - df_htf['low'],
        np.maximum(abs(df_htf['high'] - df_htf['close'].shift(1)), abs(df_htf['low'] - df_htf['close'].shift(1)))
    )
    df_htf['atr'] = df_htf['tr'].rolling(14).mean()
    df_htf['ema100'] = df_htf['close'].ewm(span=100, adjust=False).mean()
    df_htf['rsi'] = compute_rsi(df_htf['close'], 14)
    df_htf['vol_ma30'] = df_htf['volume'].rolling(30).mean()

    risk_usd = capital * (risk_pct / 100.0)
    reward_usd = risk_usd * rr_ratio

    signals = []
    for i in range(100, len(df_htf) - 2):
        row = df_htf.iloc[i]
        atr = float(row['atr']) if not pd.isna(row['atr']) else (float(row['high']) - float(row['low']))
        ema100 = float(row['ema100'])
        rsi = float(row['rsi']) if not pd.isna(row['rsi']) else 50.0
        vol_ma = float(row['vol_ma30']) if not pd.isna(row['vol_ma30']) else 1.0
        
        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        vol_ratio = float(row['volume']) / (vol_ma + 1e-9)
        if vol_ratio < 1.1:
            continue

        past_window = df_htf.iloc[i-20:i]
        major_low = float(past_window['low'].min())
        major_high = float(past_window['high'].max())

        candle_range = float(row['high']) - float(row['low'])
        if candle_range == 0:
            continue

        # ==========================================
        # 1. صفقة الشراء المؤسسية (BUY)
        # ==========================================
        lower_wick = min(float(row['open']), float(row['close'])) - float(row['low'])
        is_bullish_sweep = (
            (float(row['close']) > ema100) and
            (rsi < 68) and
            (float(row['low']) < major_low) and
            (float(row['close']) > major_low) and
            (lower_wick >= candle_range * 0.38)
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
                has_fvg, fvg_level = detect_fvg(ltf_window.head(8), "BUY")
                
                entry_zone = fvg_level if has_fvg else ((sub_high + float(row['low'])) / 2.0)
                
                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                valid_entries = retest_window[(retest_window['low'] <= entry_zone) & (retest_window['close'] > retest_window['open'])]

                if not valid_entries.empty:
                    entry_candle = valid_entries.head(1).squeeze()
                    entry = float(entry_candle['close'])
                    sl = float(row['low']) - (atr * 0.35)
                    risk = entry - sl
                    if risk <= 0:
                        continue
                    tp = entry + (risk * rr_ratio)

                    ai_score = compute_whale_ai_score(vol_ratio, lower_wick / candle_range, has_fvg)
                    status, pnl_usd = evaluate_trade_pro(df_ltf, entry_candle['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)

                    signals.append({
                        'timestamp': entry_candle['timestamp'],
                        'type': 'شراء (BUY)',
                        'entry': round(entry, 4),
                        'sl': round(sl, 4),
                        'tp': round(tp, 4),
                        'fvg_tag': "نعم (FVG مؤكد)" if has_fvg else "Order Block",
                        'ai_score': ai_score,
                        'status': status,
                        'pnl_usd': round(pnl_usd, 2)
                    })

        # ==========================================
        # 2. صفقة البيع المؤسسية (SELL)
        # ==========================================
        upper_wick = float(row['high']) - max(float(row['open']), float(row['close']))
        is_bearish_sweep = (
            (float(row['close']) < ema100) and
            (rsi > 32) and
            (float(row['high']) > major_high) and
            (float(row['close']) < major_high) and
            (upper_wick >= candle_range * 0.38)
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
                has_fvg, fvg_level = detect_fvg(ltf_window.head(8), "SELL")
                
                entry_zone = fvg_level if has_fvg else ((sub_low + float(row['high'])) / 2.0)

                retest_window = ltf_window[ltf_window['timestamp'] > choch_time]
                valid_entries = retest_window[(retest_window['high'] >= entry_zone) & (retest_window['close'] < retest_window['open'])]

                if not valid_entries.empty:
                    entry_candle = valid_entries.head(1).squeeze()
                    entry = float(entry_candle['close'])
                    sl = float(row['high']) + (atr * 0.35)
                    risk = sl - entry
                    if risk <= 0:
                        continue
                    tp = entry - (risk * rr_ratio)

                    ai_score = compute_whale_ai_score(vol_ratio, upper_wick / candle_range, has_fvg)
                    status, pnl_usd = evaluate_trade_pro(df_ltf, entry_candle['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)

                    signals.append({
                        'timestamp': entry_candle['timestamp'],
                        'type': 'بيع (SELL)',
                        'entry': round(entry, 4),
                        'sl': round(sl, 4),
                        'tp': round(tp, 4),
                        'fvg_tag': "نعم (FVG مؤكد)" if has_fvg else "Order Block",
                        'ai_score': ai_score,
                        'status': status,
                        'pnl_usd': round(pnl_usd, 2)
                    })

    if not signals:
        return pd.DataFrame()

    return pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type'])

def compute_whale_ai_score(vol_ratio, wick_ratio, has_fvg):
    """نموذج الذكاء الاصطناعي لقياس بصمة الحيتان (0 - 100%)"""
    vol_score = min(vol_ratio, 3.0) / 3.0 * 35.0
    wick_score = min(wick_ratio, 0.85) / 0.85 * 35.0
    fvg_bonus = 22.0 if has_fvg else 8.0
    return round(min(max(vol_score + wick_score + fvg_bonus + 8.0, 68.0), 99.2), 1)

def evaluate_trade_pro(df_ltf, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    """إدارة الصفقة باحترافية: تأمين الدخول عند 1:1 + جني الأرباح عند الهدف"""
    future = df_ltf[df_ltf['timestamp'] > entry_time].head(280)
    current_sl = sl
    risk_dist = abs(entry - sl)

    for _, bar in future.iterrows():
        if direction == "BUY":
            if float(bar['high']) >= entry + (risk_dist * 1.1):
                current_sl = entry
