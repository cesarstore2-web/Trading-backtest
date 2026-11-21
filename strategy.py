import yfinance as yf
import pandas as pd
import numpy as np

def fetch_data(symbol, interval, period="5d"):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df, ema_len, atr_len):
    df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(atr_len).mean()
    return df

def get_4h_trend(symbol):
    # فحص الاتجاه العام في الخفاء على فريم 4 ساعات
    df_1h = fetch_data(symbol, "1h", period="30d")
    if df_1h.empty:
        return "غير محدد"
    df_4h = df_1h.resample('4h').agg({
        'Open': 'first', 
        'High': 'max', 
        'Low': 'min', 
        'Close': 'last'
    }).dropna()
    
    df_4h['EMA_50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()
    last_close = df_4h['Close'].iloc[-1]
    last_ema = df_4h['EMA_50'].iloc[-1]
    
    return "صاعد 🟢" if last_close > last_ema else "هابط 🔴"

def run_analysis(ticker, tf_code, ema_period, atr_period, rr_ratio):
    df = fetch_data(ticker, tf_code, period="10d")
    df_5m = fetch_data(ticker, "5m", period="2d")
    
    if df.empty or df_5m.empty:
        return None
        
    df = calculate_indicators(df, ema_period, atr_period)
    trend_4h = get_4h_trend(ticker)
    
    atr_val = df['ATR'].iloc[-1]
    ema_val = df['EMA'].iloc[-1]
    
    # تحديد مناطق العرض والطلب على الفريم المختار (آخر 20 شمعة)
    demand_bottom = df['Low'].iloc[-20:-2].min()
    demand_top = demand_bottom + (atr_val * 0.5)
    
    supply_top = df['High'].iloc[-20:-2].max()
    supply_bottom = supply_top - (atr_val * 0.5)
    
    # بيانات شمعة الـ 5 دقائق للتأكيد
    last_5m_close = df_5m['Close'].iloc[-1]
    last_5m_open = df_5m['Open'].iloc[-1]
    prev_5m_high = df_5m['High'].iloc[-2]
    prev_5m_low = df_5m['Low'].iloc[-2]
    
    signal = "انتظار (لا توجد فرصة مكتملة حالياً)"
    entry, sl, tp = 0.0, 0.0, 0.0
    reason = "ننتظر وصول السعر للمنطقة وحدوث اختراق بشمعة 5 دقائق متوافقة مع اتجاه 4 ساعات."

    # 1. صفقة شراء: اتجاه 4 ساعات صاعد + شمعة 5 دقائق صاعدة تخترق منطقة الطلب
    if "صاعد" in trend_4h and last_5m_close > last_5m_open and last_5m_close > demand_top and last_5m_close > prev_5m_high:
        signal = "توصية شراء (BUY) 🚀"
        entry = last_5m_close
        sl = demand_bottom - (atr_val * 0.5)
        tp = entry + ((entry - sl) * rr_ratio)
        reason = f"تم اختراق منطقة الطلب ({demand_top:.2f}) بشمعة 5 دقائق صاعدة مع دعم الاتجاه العام (4 ساعات)."

    # 2. صفقة بيع: اتجاه 4 ساعات هابط + شمعة 5 دقائق هابطة تكسر منطقة العرض
    elif "هابط" in trend_4h and last_5m_close < last_5m_open and last_5m_close < supply_bottom and last_5m_close < prev_5m_low:
        signal = "توصية بيع (SELL) 📉"
        entry = last_5m_close
        sl = supply_top + (atr_val * 0.5)
        tp = entry - ((sl - entry) * rr_ratio)
        reason = f"تم كسر منطقة العرض ({supply_bottom:.2f}) بشمعة 5 دقائق هابطة مع دعم الاتجاه العام (4 ساعات)."

    return {
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "demand_bottom": demand_bottom,
        "demand_top": demand_top,
        "supply_bottom": supply_bottom,
        "supply_top": supply_top,
        "atr": atr_val,
        "ema": ema_val,
        "trend_4h": trend_4h,
        "current_price": last_5m_close,
        "reason": reason
    }
