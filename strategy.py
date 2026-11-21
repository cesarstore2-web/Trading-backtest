import yfinance as yf
import pandas as pd
import numpy as np

# ربط رموز USDT بمصادر البيانات الحية
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

def fetch_data(symbol_usdt, interval, period="7d"):
    yf_symbol = TICKER_MAP.get(symbol_usdt, "BTC-USD")
    df = yf.download(yf_symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df, ema_len, atr_len=14):
    df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(atr_len).mean()
    return df

def get_4h_trend_series(symbol_usdt):
    df_1h = fetch_data(symbol_usdt, "1h", period="30d")
    if df_1h.empty:
        return pd.Series(dtype=str)
    df_4h = df_1h.resample('4h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    df_4h['EMA_50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()
    df_4h['Trend'] = np.where(df_4h['Close'] > df_4h['EMA_50'], "صاعد 🟢", "هابط 🔴")
    return df_4h['Trend']

def run_backtest(df, trend_series, atr_sl_mult, rr_ratio):
    wins, losses = 0, 0
    total_profit_pct, total_loss_pct = 0.0, 0.0
    in_trade = False
    trade_type = ""
    entry, sl, tp = 0.0, 0.0, 0.0

    for i in range(25, len(df)):
        current_time = df.index[i]
        # مطابقة اتجاه 4 ساعات في الخلفية
        past_trends = trend_series[trend_series.index <= current_time]
        current_trend = past_trends.iloc[-1] if not past_trends.empty else "صاعد 🟢"

        close_p = df['Close'].iloc[i]
        open_p = df['Open'].iloc[i]
        high_p = df['High'].iloc[i]
        low_p = df['Low'].iloc[i]
        atr_val = df['ATR'].iloc[i]

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
            demand_bottom = df['Low'].iloc[i-20:i-1].min()
            demand_top = demand_bottom + (atr_val * 0.5)
            supply_top = df['High'].iloc[i-20:i-1].max()
            supply_bottom = supply_top - (atr_val * 0.5)

            # شرط الشراء
            if "صاعد" in current_trend and close_p > open_p and close_p > demand_top and df['Low'].iloc[i-1] <= demand_top:
                in_trade = True
                trade_type = "BUY"
                entry = close_p
                sl = entry - (atr_val * atr_sl_mult)
                tp = entry + ((entry - sl) * rr_ratio)

            # شرط البيع
            elif "هابط" in current_trend and close_p < open_p and close_p < supply_bottom and df['High'].iloc[i-1] >= supply_bottom:
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

def run_analysis(symbol_usdt, tf_code, ema_period, atr_sl_mult, rr_ratio):
    df = fetch_data(symbol_usdt, tf_code, period="10d")
    df_5m = fetch_data(symbol_usdt, "5m", period="2d")
    
    if df.empty or df_5m.empty:
        return None
        
    df = calculate_indicators(df, ema_period)
    trend_series = get_4h_trend_series(symbol_usdt)
    trend_4h = trend_series.iloc[-1] if not trend_series.empty else "غير محدد"
    
    # حساب سجل الأداء التاريخي
    stats = run_backtest(df, trend_series, atr_sl_mult, rr_ratio)
    
    atr_val = df['ATR'].iloc[-1]
    ema_val = df['EMA'].iloc[-1]
    
    demand_bottom = df['Low'].iloc[-20:-2].min()
    demand_top = demand_bottom + (atr_val * 0.5)
    
    supply_top = df['High'].iloc[-20:-2].max()
    supply_bottom = supply_top - (atr_val * 0.5)
    
    last_5m_close = df_5m['Close'].iloc[-1]
    last_5m_open = df_5m['Open'].iloc[-1]
    prev_5m_high = df_5m['High'].iloc[-2]
    prev_5m_low = df_5m['Low'].iloc[-2]
    
    signal = "انتظار (لا توجد فرصة مكتملة)"
    entry, sl, tp = 0.0, 0.0, 0.0
    reason = "السعر لم يخترق المنطقة بشمعة 5 دقائق متوافقة مع اتجاه 4 ساعات."

    # صفقة شراء
    if "صاعد" in trend_4h and last_5m_close > last_5m_open and last_5m_close > demand_top and last_5m_close > prev_5m_high:
        signal = "توصية شراء (BUY) 🚀"
        entry = last_5m_close
        sl = entry - (atr_val * atr_sl_mult)
        tp = entry + ((entry - sl) * rr_ratio)
        reason = f"اختراق منطقة الطلب بشمعة 5 دقائق صاعدة مع دعم اتجاه 4 ساعات."

    # صفقة بيع
    elif "هابط" in trend_4h and last_5m_close < last_5m_open and last_5m_close < supply_bottom and last_5m_close < prev_5m_low:
        signal = "توصية بيع (SELL) 📉"
        entry = last_5m_close
        sl = entry + (atr_val * atr_sl_mult)
        tp = entry - ((sl - entry) * rr_ratio)
        reason = f"كسر منطقة العرض بشمعة 5 دقائق هابطة مع دعم اتجاه 4 ساعات."

    return {
        "signal": signal, "entry": entry, "sl": sl, "tp": tp,
        "demand_bottom": demand_bottom, "demand_top": demand_top,
        "supply_bottom": supply_bottom, "supply_top": supply_top,
        "ema": ema_val, "trend_4h": trend_4h,
        "current_price": last_5m_close, "reason": reason,
        "stats": stats
    }
