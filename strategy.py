import yfinance as yf
import pandas as pd
import numpy as np

TICKER_MAP = {
    "XLMUSDT": "XLM-USD",
    "ZECUSDT": "ZEC-USD",
    "XRPUSDT": "XRP-USD",
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "ADAUSDT": "ADA-USD",
    "LTCUSDT": "LTC-USD",
    "HBARUSDT": "HBAR-USD",
    "XAUUSDT": "GC=F",
    "PAXGUSDT": "PAXG-USD"
}

def fetch_data(symbol_usdt, interval, period="30d"):
    yf_symbol = TICKER_MAP.get(symbol_usdt, "BTC-USD")
    df = yf.download(yf_symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df, atr_len=14):
    df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA_13'] = df['Close'].ewm(span=13, adjust=False).mean()
    df['EMA_34'] = df['Close'].ewm(span=34, adjust=False).mean()
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(atr_len).mean()
    return df

def get_4h_trend_series(symbol_usdt):
    df_1h = fetch_data(symbol_usdt, "1h", period="45d")
    if df_1h.empty:
        return pd.Series(dtype=str)
    df_4h = df_1h.resample('4h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    df_4h['EMA_50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()
    df_4h['Trend'] = np.where(df_4h['Close'] > df_4h['EMA_50'], "صاعد 🟢", "هابط 🔴")
    return df_4h['Trend']

def run_backtest(df, trend_series, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd):
    wins, losses = 0, 0
    net_profit_usd = 0.0
    in_trade = False
    trade_type = ""
    entry, sl, tp = 0.0, 0.0, 0.0

    for i in range(36, len(df)):
        current_time = df.index[i]
        if use_4h_filter and not trend_series.empty:
            past_trends = trend_series[trend_series.index <= current_time]
            current_trend = past_trends.iloc[-1] if not past_trends.empty else "صاعد 🟢"
        else:
            current_trend = "ALL"

        open_p = df['Open'].iloc[i]
        close_p = df['Close'].iloc[i]
        high_p = df['High'].iloc[i]
        low_p = df['Low'].iloc[i]
        
        prev_high = df['High'].iloc[i-1]
        prev_low = df['Low'].iloc[i-1]
        atr_val = df['ATR'].iloc[i]

        e5_curr, e13_curr, e34_curr = df['EMA_5'].iloc[i], df['EMA_13'].iloc[i], df['EMA_34'].iloc[i]

        if pd.isna(atr_val) or atr_val == 0:
            continue

        if in_trade:
            if trade_type == "BUY":
                if low_p <= sl:
                    losses += 1
                    loss_pct = abs((sl - entry) / entry)
                    net_profit_usd -= (trade_size_usd * loss_pct)
                    in_trade = False
                elif high_p >= tp:
                    wins += 1
                    win_pct = abs((tp - entry) / entry)
                    net_profit_usd += (trade_size_usd * win_pct)
                    in_trade = False
            elif trade_type == "SELL":
                if high_p >= sl:
                    losses += 1
                    loss_pct = abs((sl - entry) / entry)
                    net_profit_usd -= (trade_size_usd * loss_pct)
                    in_trade = False
                elif low_p <= tp:
                    wins += 1
                    win_pct = abs((tp - entry) / entry)
                    net_profit_usd += (trade_size_usd * win_pct)
                    in_trade = False
        else:
            # شرط اختراق شمعة مع ترتيب المتوسطات (5 > 13 > 34)
            bullish_breakout = (e5_curr > e13_curr > e34_curr) and (close_p > open_p) and (close_p > prev_high) and (df['Close'].iloc[i-1] <= df['High'].iloc[i-2])
            # شرط كسر شمعة مع ترتيب المتوسطات (5 < 13 < 34)
            bearish_breakout = (e5_curr < e13_curr < e34_curr) and (close_p < open_p) and (close_p < prev_low) and (df['Close'].iloc[i-1] >= df['Low'].iloc[i-2])

            allow_buy = (not use_4h_filter) or ("صاعد" in current_trend)
            allow_sell = (not use_4h_filter) or ("هابط" in current_trend)

            if allow_buy and bullish_breakout:
                in_trade = True
                trade_type = "BUY"
                entry = close_p
                sl = entry - (atr_val * atr_sl_mult)
                tp = entry + ((entry - sl) * rr_ratio)

            elif allow_sell and bearish_breakout:
                in_trade = True
                trade_type = "SELL"
                entry = close_p
                sl = entry + (atr_val * atr_sl_mult)
                tp = entry - ((sl - entry) * rr_ratio)

    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_profit_usd": net_profit_usd
    }

def run_analysis(symbol_usdt, tf_code, atr_sl_mult, rr_ratio, use_4h_filter=True, trade_size_usd=100.0):
    df = fetch_data(symbol_usdt, tf_code, period="30d")
    if df.empty or len(df) < 40:
        return None
        
    df = calculate_indicators(df)
    trend_series = get_4h_trend_series(symbol_usdt) if use_4h_filter else pd.Series(dtype=str)
    trend_4h = trend_series.iloc[-1] if (use_4h_filter and not trend_series.empty) else "معطّل ⚪"
    
    stats = run_backtest(df, trend_series, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
    
    atr_val = df['ATR'].iloc[-1]
    e5, e13, e34 = df['EMA_5'].iloc[-1], df['EMA_13'].iloc[-1], df['EMA_34'].iloc[-1]
    
    current_open = df['Open'].iloc[-1]
    current_price = df['Close'].iloc[-1]
    prev_high = df['High'].iloc[-2]
    prev_low = df['Low'].iloc[-2]
    
    signal = "انتظار ⏳"
    entry, sl, tp = 0.0, 0.0, 0.0
    reason = "بانتظار إغلاق شمعة اختراق مؤكدة مع ترتيب المتوسطات (5, 13, 34)."

    # شرط اختراق الشمعة الحالية لقمة/قاع الشمعة السابقة
    bullish_breakout = (e5 > e13 > e34) and (current_price > current_open) and (current_price > prev_high)
    bearish_breakout = (e5 < e13 < e34) and (current_price < current_open) and (current_price < prev_low)

    allow_buy = (not use_4h_filter) or ("صاعد" in trend_4h)
    allow_sell = (not use_4h_filter) or ("هابط" in trend_4h)

    if allow_buy and bullish_breakout:
        signal = "شراء (BUY) 🚀"
        entry = current_price
        sl = entry - (atr_val * atr_sl_mult)
        tp = entry + ((entry - sl) * rr_ratio)
        reason = f"تم اختراق قمة الشمعة السابقة ({prev_high:.4f}) بشمعة صاعدة مع توافق EMA 5 > 13 > 34."

    elif allow_sell and bearish_breakout:
        signal = "بيع (SELL) 📉"
        entry = current_price
        sl = entry + (atr_val * atr_sl_mult)
        tp = entry - ((sl - entry) * rr_ratio)
        reason = f"تم كسر قاع الشمعة السابقة ({prev_low:.4f}) بشمعة هابطة مع توافق EMA 5 < 13 < 34."

    # حساب درجة التقييم لاختيار أفضل 3 توصيات
    score = (stats['net_profit_usd'] * 0.6) + (stats['win_rate'] * 0.4)
    if "شراء" in signal or "بيع" in signal:
        score += 50  # أولوية للعملات التي أعطت إشارة اختراق حالية

    return {
        "coin": symbol_usdt,
        "signal": signal, "entry": entry, "sl": sl, "tp": tp,
        "ema_5": e5, "ema_13": e13, "ema_34": e34,
        "trend_4h": trend_4h, "current_price": current_price,
        "reason": reason, "stats": stats, "score": score
    }

def scan_all_coins(coins_list, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd):
    all_data = []
    table_rows = []
    
    for coin in coins_list:
        res = run_analysis(coin, tf_code, atr_sl_mult, rr_ratio, use_4h_filter, trade_size_usd)
        if res:
            all_data.append(res)
            table_rows.append({
                "العملة": coin,
                "السعر": f"{res['current_price']:.4f}",
                "التوصية": res['signal'],
                "الدخول": f"{res['entry']:.4f}" if res['entry'] > 0 else "-",
                "الهدف (TP)": f"{res['tp']:.4f}" if res['tp'] > 0 else "-",
                "الوقف (SL)": f"{res['sl']:.4f}" if res['sl'] > 0 else "-",
                "الناجحة": res['stats']['wins'],
                "الخاسرة": res['stats']['losses'],
                "الربح الصافي ($)": f"{res['stats']['net_profit_usd']:+.2f}$"
            })
            
    # ترتيب العملات لاستخراج أفضل 3 توصيات دقة وتقييماً
    top_3 = sorted(all_data, key=lambda x: x['score'], reverse=True)[:3]
    return pd.DataFrame(table_rows), top_3
