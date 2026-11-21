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
    """جلب بيانات الشموع من Yahoo Finance"""
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

def analyze_smc_strategy(df_htf, df_ltf, rr_ratio=2.0, start_hour=0, end_hour=23, capital=1000.0, risk_pct=1.0):
    """تنفيذ شروط استراتيجية SMC وحساب الأرباح بالدولار الأمريكي"""
    if df_htf.empty or df_ltf.empty or len(df_htf) < 20:
        return pd.DataFrame()

    df_htf = df_htf.copy()
    df_htf['swing_high'] = df_htf['high'].rolling(window=5, center=True).max()
    df_htf['swing_low'] = df_htf['low'].rolling(window=5, center=True).min()

    # قيمة المخاطرة لكل صفقة بالدولار الأمريكي
    risk_usd = capital * (risk_pct / 100.0)
    reward_usd = risk_usd * rr_ratio

    signals = []
    for i in range(8, len(df_htf) - 2):
        row = df_htf.iloc[i]
        prev_low = df_htf['swing_low'].iloc[i-3]
        prev_high = df_htf['swing_high'].iloc[i-3]

        if pd.isna(prev_low) or pd.isna(prev_high):
            continue

        if not (start_hour <= row['timestamp'].hour <= end_hour):
            continue

        # --- 1. صفقة الشراء (BUY) ---
        if row['low'] < prev_low and row['close'] > prev_low:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] >= row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 4:
                continue

            sub_high = ltf_window['high'].head(3).max()
            choch_candles = ltf_window[ltf_window['close'] > sub_high]

            if not choch_candles.empty:
                confirm_row = choch_candles.head(1).squeeze()
                entry = float(confirm_row['close'])
                sl = float(row['low']) * 0.9985
                risk = entry - sl
                if risk <= 0:
                    continue
                tp = entry + (risk * rr_ratio)

                ai_score = compute_ai_quality(df_htf, i, len(ltf_window))
                status, pnl_usd = evaluate_trade_usd(df_ltf, confirm_row['timestamp'], "BUY", entry, sl, tp, risk_usd, reward_usd)

                signals.append({
                    'timestamp': confirm_row['timestamp'],
                    'type': 'شراء (BUY)',
                    'entry': round(entry, 4),
                    'sl': round(sl, 4),
                    'tp': round(tp, 4),
                    'ai_score': ai_score,
                    'status': status,
                    'pnl_usd': round(pnl_usd, 2)
                })

        # --- 2. صفقة البيع (SELL) ---
        elif row['high'] > prev_high and row['close'] < prev_high:
            ltf_window = df_ltf[
                (df_ltf['timestamp'] >= row['timestamp']) &
                (df_ltf['timestamp'] <= row['timestamp'] + pd.Timedelta(hours=8))
            ]
            if len(ltf_window) < 4:
                continue

            sub_low = ltf_window['low'].head(3).min()
            choch_candles = ltf_window[ltf_window['close'] < sub_low]

            if not choch_candles.empty:
                confirm_row = choch_candles.head(1).squeeze()
                entry = float(confirm_row['close'])
                sl = float(row['high']) * 1.0015
                risk = sl - entry
                if risk <= 0:
                    continue
                tp = entry - (risk * rr_ratio)

                ai_score = compute_ai_quality(df_htf, i, len(ltf_window))
                status, pnl_usd = evaluate_trade_usd(df_ltf, confirm_row['timestamp'], "SELL", entry, sl, tp, risk_usd, reward_usd)

                signals.append({
                    'timestamp': confirm_row['timestamp'],
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

def compute_ai_quality(df_htf, idx, window_len):
    """تقييم جودة الصفقة بالذكاء الاصطناعي (0 - 100%)"""
    row = df_htf.iloc[idx]
    
    start_idx = max(0, idx - 10)
    avg_vol = df_htf['volume'].iloc[start_idx:idx].mean()
    vol_ratio = (float(row['volume']) / (float(avg_vol) + 1e-9)) if avg_vol > 0 else 1.0
    vol_score = min(vol_ratio, 2.5) / 2.5 * 40.0

    total_range = float(row['high']) - float(row['low'])
    body_size = abs(float(row['close']) - float(row['open']))
    wick_ratio = (total_range - body_size) / (total_range + 1e-9)
    wick_score = wick_ratio * 40.0

    momentum_score = 18.5 if window_len >= 4 else 12.0
    return round(min(max(vol_score + wick_score + momentum_score, 60.0), 98.5), 1)

def evaluate_trade_usd(df_ltf, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    """حساب نتيجة الصفقة والربح أو الخسارة بالدولار الأمريكي"""
    future = df_ltf[df_ltf['timestamp'] > entry_time].head(150)

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
