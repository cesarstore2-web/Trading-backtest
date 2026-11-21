import yfinance as yf
import pandas as pd
import numpy as np

# خريطة الأزواج المطلوبة (العملات الرقمية + الذهب الرقمي + الذهب الفوري)
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
    """جلب بيانات الشموع من Yahoo Finance بدون قيود جغرافية"""
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty:
            return pd.DataFrame()
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.reset_index()
        df.rename(columns={
            'Datetime': 'timestamp',
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }, inplace=True)
        
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].dropna()
    except Exception:
        return pd.DataFrame()

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.0, start_hour=0, end_hour=23):
    """
    تنفيذ شروط استراتيجية SMC:
    1. رصد القمم والقيعان الرئيسية (Swing High / Swing Low) على الفريم الكبير (HTF)
    2. رصد مصيدة السيولة / الكسر الكاذب (Liquidity Sweep) وإغلاق الشمعة داخل النطاق
    3. النزول للفريم الصغير (LTF) وتأكيد كسر الهيكل (CHoCH)
    4. حساب نقطة الدخول، وقف الخسارة أسفل/أعلى ذيل الكسر، وهدف الربح
    """
    if df_htf.empty or df_ltf.empty or len(df_htf) < 20:
        return pd.DataFrame()

    df_htf = df_htf.copy()
    df_htf['swing_high'] = df_htf['high'].rolling(window=5, center=True).max()
    df_htf['swing_low'] = df_htf['low'].rolling(window=5, center=True).min()

    signals = []
    for i in range(8, len(df_htf) - 2):
        row = df_htf.iloc[i]
        prev_low = df_htf['swing_low'].iloc[i-3]
        prev_high = df_htf['swing_high'].iloc[i-3]

        if pd.isna(prev_low) or pd.isna(prev_high):
            continue

        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        # ==========================================
        # 1. شروط صفقة الشراء (BUY)
        # ==========================================
        if row['low'] < prev_low and row['close'] > prev_low:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] >= row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 4:
                continue

            sub_high = ltf_window['high'].iloc[:3].max()
            choch_candles = ltf_window[ltf_window['close'] > sub_high]

            if not choch_candles.empty:
                confirm_candle = choch_candles.iloc[0]
                entry = float(confirm_candle['close'])
                sl = float(row['low']) * 0.9985
                risk = entry - sl
                if risk <= 0:
                    continue
                tp = entry + (risk * rr_ratio)

                ai_score = compute_ai_quality(df_htf, i, ltf_window)
                status, points = evaluate_trade(df_ltf, confirm_candle['timestamp'], "BUY", entry, sl, tp)

                signals.append({
                    'timestamp': confirm_candle['timestamp'],
                    'type': 'شراء (BUY)',
                    'entry': round(entry, 4),
                    'sl': round(sl, 4),
                    'tp': round(tp, 4),
                    'ai_score': ai_score,
                    'status': status,
                    'points': points
                })

        # ==========================================
        # 2. شروط صفقة البيع (SELL)
        # ==========================================
        elif row['high'] > prev_high and row['close'] < prev_high:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] >= row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 4:
                continue

            sub_low = ltf_window['low'].iloc[:3].min()
            choch_candles = ltf_window[ltf_window['close'] < sub_low]

            if not choch_candles.empty:
                confirm_candle = choch_candles.iloc[0]
                entry = float(confirm_candle['close'])
                sl = float(row['high']) * 1.0015
                risk = sl - entry
                if risk <= 0:
                    continue
                tp = entry - (risk * rr_ratio)

                ai_score = compute_ai_quality(df_htf, i, ltf_window)
                status, points = evaluate_trade(df_ltf, confirm_candle['timestamp'], "SELL", entry, sl, tp)

                signals.append({
                    'timestamp': confirm_candle['timestamp'],
                    'type': 'بيع (SELL)',
                    'entry': round(entry, 4),
                    'sl': round(sl, 4),
                    'tp': round(tp, 4),
                    'ai_score': ai_score,
                    'status': status,
                    'points': points
                })

    if not signals:
        return pd.DataFrame()

    df_signals = pd.DataFrame(signals).drop_duplicates(subset=['timestamp', 'type'])
    return df_signals

def compute_ai_quality(df_htf, idx, ltf_window):
    """نموذج الذكاء الاصطناعي لتقييم جودة الكسر الكاذب وزخم السيولة (0 - 100%)"""
    row = df_htf.iloc[idx]
    
    avg_vol = df_htf['volume'].iloc[max(0, idx-10):idx].mean()
    vol_ratio = (row['volume'] / (avg_vol + 1e-9)) if avg_vol > 0 else 1.0
    vol_score = min(vol_ratio, 2.5) / 2.5 * 40

    total_range = row['high'] - row['low']
    body_size = abs(row['close'] - row['open'])
    wick_ratio = (total_range - body_size) / (total_range + 1e-9)
    wick_score = wick_ratio * 40

    momentum_score = 18.5 if len(ltf_window) >= 4 else 12.0

    final_score = round(min(max(vol_score + wick_score + momentum_score, 60.0), 98.5), 1)
    return final_score

def evaluate_trade(df_ltf, entry_time, direction, entry, sl, tp):
    """تتبع حركة السعر بعد الدخول لحساب الصفقات الرابحة والخاسرة والنقاط"""
    future = df_ltf[df_ltf['timestamp'] > entry_time].head(150)
    
    win_pts = round((abs(tp - entry) / entry) * 10000, 1)
    loss_pts = -round((abs(entry - sl) / entry) * 10000, 1)

    for _, bar in future.iterrows():
        if direction == "BUY":
            if bar['low'] <= sl:
                return "خاسرة", loss_pts
            if bar['high'] >= tp:
                return "رابحة", win_pts
        else:
            if bar['high'] >= sl:
                return "خاسرة", loss_pts
            if bar['low'] <= tp:
                return "رابحة", win_pts
                
    return "جارية", 0.0
