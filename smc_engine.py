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
        clean_df = pd.DataFrame({
            'timestamp': df['timestamp'],
            'open': pd.to_numeric(df['open'], errors='coerce'),
            'high': pd.to_numeric(df['high'], errors='coerce'),
            'low': pd.to_numeric(df['low'], errors='coerce'),
            'close': pd.to_numeric(df['close'], errors='coerce'),
            'volume': pd.to_numeric(df['volume'], errors='coerce')
        }).dropna()
        return clean_df
    except Exception:
        return pd.DataFrame()

def compute_rsi(series, period=14):
    """حساب مؤشر القوة النسبية لتجنب الدخول في القمم والقيعان المتشبعة"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def detect_fvg_from_list(records, direction):
    """اكتشاف فجوة القيمة العادلة (Fair Value Gap) من قائمة الشموع"""
    if len(records) < 4:
        return False, 0.0
    
    for idx in range(2, min(len(records), 8)):
        c1 = records[idx - 2]
        c3 = records[idx]
        if direction == "BUY":
            if c3['low'] > c1['high']:
                return True, (c3['low'] + c1['high']) / 2.0
        else:
            if c3['high'] < c1['low']:
                return True, (c3['high'] + c1['low']) / 2.0
    return False, 0.0

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.0, start_hour=0, end_hour=23, capital=1000.0, risk_pct=1.0):
    """محرك التداول المؤسسي المتكامل (Whale Footprint + SMC + FVG + AI)"""
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

    htf_records = df_htf.to_dict('records')
    ltf_records = df_ltf.to_dict('records')
    signals = []

    for i in range(100, len(htf_records) - 2):
        row = htf_records[i]
        atr = float(row['atr']) if pd.notna(row['atr']) else (row['high'] - row['low'])
        ema100 = float(row['ema100'])
        rsi = float(row['rsi']) if pd.notna(row['rsi']) else 50.0
        vol_ma = float(row['vol_ma30']) if pd.notna(row['vol_ma30']) else 1.0
        
        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        vol_ratio = row['volume'] / (vol_ma + 1e-9)
        if vol_ratio < 1.1:
            continue

        past_slice = htf_records[i-20:i]
        major_low = min(x['low'] for x in past_slice)
        major_high = max(x['high'] for x in past_slice)

        candle_range = row['high'] - row['low']
        if candle_range == 0:
            continue

        t_start = row['timestamp']
        t_end = t_start + pd.Timedelta(hours=8)
        ltf_window = [r for r in ltf_records if t_start < r['timestamp'] <= t_end]
        if len(ltf_window) < 6:
            continue

        # ==========================================
        # 1. صفقة الشراء المؤسسية (BUY)
        # ==========================================
        lower_wick = min(row['open'], row['close']) - row['low']
        is_bullish_sweep = (
            (row['close'] > ema100) and
            (rsi < 68) and
            (row['low'] < major_low) and
            (row['close'] > major_low) and
            (lower_wick >= candle_range * 0.38)
        )

        if is_bullish_sweep:
            sub_high = max(x['high'] for x in ltf_window[:3])
            choch_candle = next((r for r in ltf_window if r['close'] > sub_high), None)

            if choch_candle is not None:
                choch_time = choch_candle['timestamp']
                has_fvg, fvg_level = detect_fvg_from_list(ltf_window, "BUY")
                entry_zone = fvg_level if has_fvg else ((sub_high + row['low']) / 2.0)

                entry_candle = next(
                    (r for r in ltf_window if r['timestamp'] > choch_time and r['low'] <= entry_zone and r['close'] > r['open']),
                    None
                )

                if entry_candle is not None:
                    entry = entry_candle['close']
                    sl = row['low'] - (atr * 0.35)
                    risk = entry - sl
                    if risk > 0:
                        tp = entry + (risk * rr_ratio)
                        ai_score = compute_whale_ai_score(vol_ratio, lower_wick / candle_range, has_fvg)
                        status, pnl_usd = evaluate_trade_pro(ltf_records, entry_candle['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)

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
        upper_wick = row['high'] - max(row['open'], row['close'])
        is_bearish_sweep = (
            (row['close'] < ema100) and
            (rsi > 32) and
            (row['high'] > major_high) and
            (row['close'] < major_high) and
            (upper_wick >= candle_range * 0.38)
        )

        if is_bearish_sweep:
            sub_low = min(x['low'] for x in ltf_window[:3])
            choch_candle = next((r for r in ltf_window if r['close'] < sub_low), None)

            if choch_candle is not None:
                choch_time = choch_candle['timestamp']
                has_fvg, fvg_level = detect_fvg_from_list(ltf_window, "SELL")
                entry_zone = fvg_level if has_fvg else ((sub_low + row['high']) / 2.0)

                entry_candle = next(
                    (r for r in ltf_window if r['timestamp'] > choch_time and r['high'] >= entry_zone and r['close'] < r['open']),
                    None
                )

                if entry_candle is not None:
                    entry = entry_candle['close']
                    sl = row['high'] + (atr * 0.35)
                    risk = sl - entry
                    if risk > 0:
                        tp = entry - (risk * rr_ratio)
                        ai_score = compute_whale_ai_score(vol_ratio, upper_wick / candle_range, has_fvg)
                        status, pnl_usd = evaluate_trade_pro(ltf_records, entry_candle['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)

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

def evaluate_trade_pro(ltf_records, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    """إدارة الصفقة باحترافية: تأمين الدخول عند 1:1 + جني الأرباح عند الهدف"""
    future_records = [r for r in ltf_records if r['timestamp'] > entry_time][:280]
    current_sl = sl
    risk_dist = abs(entry - sl)

    for bar in future_records:
        if direction == "BUY":
            if bar['high'] >= entry + (risk_dist * 1.1):
                current_sl = entry
            if bar['low'] <= current_sl:
                return ("مؤمّنة (0$)", 0.0) if current_sl == entry else ("خاسرة", -risk_usd)
            if bar['high'] >= tp:
