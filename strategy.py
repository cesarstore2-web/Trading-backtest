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
    # جلب 45 يوماً من فريم الساعة لضمان استقرار EMA 50 على فريم 4 ساعات طوال الشهر السابق
    df_1h = fetch_data(symbol_usdt, "1h", period="45d")
    if df_1h.empty:
        return pd.Series(dtype=str)
    df_4h = df_1h.resample('4h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    df_4h['EMA_50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()
    df_4h['Trend'] = np.where(df_4h['Close'] > df_4h['EMA_50'], "صاعد 🟢", "هابط 🔴")
    return df_4h['Trend']

def run_backtest(df, trend_series, atr_sl_mult, rr_ratio, use_4h_filter):
    wins, losses = 0, 0
    total_profit_pct, total_loss_pct = 0.0, 0.0
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

        close_p = df['Close'].iloc[i]
        high_p = df['High'].iloc[i]
        low_p = df['Low'].iloc[i]
        atr_val = df['ATR'].iloc[i]

        e5_curr, e13_curr, e34_curr = df['EMA_5'].iloc[i], df['EMA_13'].iloc[i], df['EMA_34'].iloc[i]
        e5_prev, e13_prev, e34_prev = df['EMA_5'].iloc[i-1], df['EMA_13'].iloc[i-1], df['EMA_34'].iloc[i-1]

        if pd.isna(atr_val) or atr_val == 0:
            continue

        if in_trade:
            if trade_type == "BUY":
                if low_p <= sl:
                    losses += 1
                    total_loss_pct += abs((sl - entry) / entry) * 100
                    in_trade = False
                elif high_p >= tp:
                    wins += 1
                    total_profit_pct += abs((tp - entry) / entry) * 100
                    in_trade = False
            elif trade_type == "SELL":
                if high_p >= sl:
                    losses += 1
                    total_loss_pct += abs((sl - entry) / entry) * 100
                    in_trade = False
                elif low_p <= tp:
                    wins += 1
                    total_profit_pct += abs((tp - entry) / entry) * 100
                    in_trade = False
        else:
            bullish_cross = (e5_curr > e13_curr > e34_curr) and not (e5_prev > e13_prev > e34_prev)
            bearish_cross = (e5_curr < e13_curr < e34_curr) and not (e5_prev < e13_prev < e34_prev)

            allow_buy = (not use_4h_filter) or ("صاعد" in current_trend)
            allow_sell = (not use_4h_filter) or ("هابط" in current_trend)

            if allow_buy and bullish_cross:
                in_trade = True
                trade_type = "BUY"
                entry = close_p
                sl = entry - (atr_val * atr_sl_mult)
                tp = entry + ((entry - sl) * rr_ratio)

            elif allow_sell and bearish_cross:
                in_trade = True
                trade_type = "SELL"
                entry = close_p
                sl = entry + (atr_val * atr_sl_mult)
                tp = entry - ((sl - entry) * rr_ratio)

    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    net_profit = total_profit_pct - total_loss_pct

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_profit": total_profit_pct,
        "gross_loss": total_loss_pct,
        "net_profit": net_profit
    }

def run_analysis(symbol_usdt, tf_code, atr_sl_mult, rr_ratio, use_4h_filter=True):
    # جلب بيانات شهر كامل (30 يوماً) لتقييم الاستراتيجية
    df = fetch_data(symbol_usdt, tf_code, period="30d")
    if df.empty:
        return None
        
    df = calculate_indicators(df)
    trend_series = get_4h_trend_series(symbol_usdt) if use_4h_filter else pd.Series(dtype=str)
    trend_4h = trend_series.iloc[-1] if (use_4h_filter and not trend_series.empty) else "معطّل ⚪"
    
    stats = run_backtest(df, trend_series, atr_sl_mult, rr_ratio, use_4h_filter)
    
    atr_val = df['ATR'].iloc[-1]
    e5, e13, e34 = df['EMA_5'].iloc[-1], df['EMA_13'].iloc[-1], df['EMA_34'].iloc[-1]
    e5_prev, e13_prev, e34_prev = df['EMA_5'].iloc[-2], df['EMA_13'].iloc[-2], df['EMA_34'].iloc[-2]
    current_price = df['Close'].iloc[-1]
    
    signal = "انتظار ⏳"
    entry, sl, tp = 0.0, 0.0, 0.0
    reason = "لا يوجد تقاطع جديد حالياً."

    bullish_cross = (e5 > e13 > e34) and not (e5_prev > e13_prev > e34_prev)
    bearish_cross = (e5 < e13 < e34) and not (e5_prev < e13_prev < e34_prev)

    allow_buy = (not use_4h_filter) or ("صاعد" in trend_4h)
    allow_sell = (not use_4h_filter) or ("هابط" in trend_4h)

    if allow_buy and bullish_cross:
        signal = "شراء (BUY) 🚀"
        entry = current_price
        sl = entry - (atr_val * atr_sl_mult)
        tp = entry + ((entry - sl) * rr_ratio)
        reason = "تحقق تقاطع صاعد للمتوسطات (EMA 5 > 13 > 34)."

    elif allow_sell and bearish_cross:
        signal = "بيع (SELL) 📉"
        entry = current_price
        sl = entry + (atr_val * atr_sl_mult)
        tp = entry - ((sl - entry) * rr_ratio)
        reason = "تحقق تقاطع هابط للمتوسطات (EMA 5 < 13 < 34)."
    elif bullish_cross and not allow_buy:
        reason = "يوجد تقاطع صاعد لكن فلتر 4 ساعات هابط (تم حجب الصفقة)."
    elif bearish_cross and not allow_sell:
        reason = "يوجد تقاطع هابط لكن فلتر 4 ساعات صاعد (تم حجب الصفقة)."
    elif e5 > e13 > e34:
        reason = "المتوسطات مرتبة صعودياً (5 > 13 > 34) حالياً."
    elif e5 < e13 < e34:
        reason = "المتوسطات مرتبة هبوطياً (5 < 13 < 34) حالياً."

    return {
        "coin": symbol_usdt,
        "signal": signal, "entry": entry, "sl": sl, "tp": tp,
        "ema_5": e5, "ema_13": e13, "ema_34": e34,
        "trend_4h": trend_4h, "current_price": current_price,
        "reason": reason, "stats": stats
    }

def scan_all_coins(coins_list, tf_code, atr_sl_mult, rr_ratio, use_4h_filter):
    results = []
    for coin in coins_list:
        res = run_analysis(coin, tf_code, atr_sl_mult, rr_ratio, use_4h_filter)
        if res:
            results.append({
                "العملة": coin,
                "السعر": f"{res['current_price']:.4f}",
                "التوصية": res['signal'],
                "اتجاه 4H": res['trend_4h'],
                "الدخول": f"{res['entry']:.4f}" if res['entry'] > 0 else "-",
                "الهدف (TP)": f"{res['tp']:.4f}" if res['tp'] > 0 else "-",
                "الوقف (SL)": f"{res['sl']:.4f}" if res['sl'] > 0 else "-",
                "الناجحة": res['stats']['wins'],
                "الخاسرة": res['stats']['losses'],
                "نسبة النجاح": f"{res['stats']['win_rate']:.1f}%",
                "صافي الربح (شهر)": f"{res['stats']['net_profit']:+.2f}%"
            })
    return pd.DataFrame(results)
