import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

# 1. إعدادات الصفحة والتصميم البصري الداكن
st.set_page_config(page_title="مُقيّم الاستراتيجيات الذكي", page_icon="⚡", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.stApp { background: radial-gradient(circle at top, #1e1338 0%, #09090f 100%); color: #ffffff; direction: rtl; text-align: right; }
.stat-card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 15px;
    margin-bottom: 12px;
    backdrop-filter: blur(10px);
    text-align: center;
}
.card-green { border-color: rgba(16, 185, 129, 0.45); background: rgba(16, 185, 129, 0.07); }
.card-red { border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.07); }
.card-signal { border-color: rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.12); text-align: right; padding: 18px; }
.card-title { font-size: 13px; color: #a1a1aa; margin-bottom: 4px; }
.card-value { font-size: 23px; font-weight: 800; }
.green-text { color: #10b981; }
.red-text { color: #ef4444; }
.purple-text { color: #a855f7; }
div.stButton > button {
    width: 100%; border-radius: 12px;
    background: linear-gradient(90deg, #7c3aed 0%, #9333ea 100%);
    color: white; font-weight: 700; border: none; padding: 14px; font-size: 16px; margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)

# 2. قاعدة بيانات الأصول
ASSETS = {
    "العملات الرقمية": {
        "currency": "USDT", "is_cse": False,
        "items": {
            "XLMUSDT": "XLM-USD", "ZECUSDT": "ZEC-USD", "XRPUSDT": "XRP-USD",
            "HBARUSDT": "HBAR-USD", "ADAUSDT": "ADA-USD", "LTCUSDT": "LTC-USD",
            "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"
        }
    },
    "الذهب": {
        "currency": "USDT", "is_cse": False,
        "items": {"XAUUSDT (الذهب الفوري)": "GC=F", "PAXGUSDT": "PAXG-USD"}
    },
    "بورصة الدار البيضاء (CSEMA)": {
        "currency": "MAD", "is_cse": True,
        "items": {
            "ATW - التجاري وفا بنك": "ATW.CS", "BCP - البنك الشعبي": "BCP.CS",
            "AKT - أكديطال": "AKT.CS", "MNG - مناجم": "MNG.CS",
            "TGC - TGCC": "TGC.CS", "ADH - الضحى": "ADH.CS",
            "JET - جيت كونتراكترز": "JET.CS", "MSA - مرسى المغرب": "MSA.CS",
            "CMA - إسمنت المغرب": "CMA.CS", "LHM - لافارج هولسيم": "LHM.CS",
            "ATL - أطلنطا سند": "ATL.CS", "DHO - دلتا هولدينغ": "DHO.CS"
        }
    }
}

# 3. دوال الحساب الفني
def calculate_atr(df, length):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def calculate_supertrend(df, atr_len=10, factor=1.0):
    atr = calculate_atr(df, atr_len)
    hl2 = (df['High'] + df['Low']) / 2
    upper = hl2 + (factor * atr)
    lower = hl2 - (factor * atr)
    uptrend = [True] * len(df)
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > upper.iloc[i-1]:
            uptrend[i] = True
        elif df['Close'].iloc[i] < lower.iloc[i-1]:
            uptrend[i] = False
        else:
            uptrend[i] = uptrend[i-1]
            if uptrend[i] and lower.iloc[i] < lower.iloc[i-1]:
                lower.iloc[i] = lower.iloc[i-1]
            if not uptrend[i] and upper.iloc[i] > upper.iloc[i-1]:
                upper.iloc[i] = upper.iloc[i-1]
    df['st_up'] = uptrend
    return df

def run_strategy(ticker, is_cse, period_days, st_len, st_fac, risk_atr_len, sl_mult, rr_ratio, capital, leverage, is_spot):
    df = yf.download(ticker, period=f"{period_days}d", interval="15m", progress=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')
    
    if is_cse:
        df = df.between_time('09:30', '15:30')
        
    df = calculate_supertrend(df, st_len, st_fac)
    df['risk_atr'] = calculate_atr(df, risk_atr_len)
    
    fee_rate = 0.002 if (is_spot or is_cse) else 0.001
    position_size = capital * (1 if (is_spot or is_cse) else leverage)
    
    trades_pnl = []
    equity = [capital]
    trade_log = []
    in_trade, t_type, entry, sl, tp, entry_time = False, None, 0, 0, 0, ""
    
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        current_time = df.index[i].strftime("%Y-%m-%d %H:%M")
        if pd.isna(row['risk_atr']):
            continue
            
        if in_trade:
            if t_type == "BUY":
                if row['Low'] <= sl:
                    pct_change = (sl - entry) / entry
                    pnl = (position_size * pct_change) - (position_size * fee_rate)
                    trades_pnl.append(pnl)
                    equity.append(equity[-1] + pnl)
                    trade_log.append({"النوع": "شراء 🟢", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "خسارة ❌", "الربح/الخسارة": round(pnl, 2)})
                    in_trade = False
                elif row['High'] >= tp:
                    pct_change = (tp - entry) / entry
                    pnl = (position_size * pct_change) - (position_size * fee_rate)
                    trades_pnl.append(pnl)
                    equity.append(equity[-1] + pnl)
                    trade_log.append({"النوع": "شراء 🟢", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "ربح ✅", "الربح/الخسارة": round(pnl, 2)})
                    in_trade = False
            elif t_type == "SELL":
                if row['High'] >= sl:
                    pct_change = (entry - sl) / entry
                    pnl = (position_size * pct_change) - (position_size * fee_rate)
                    trades_pnl.append(pnl)
                    equity.append(equity[-1] + pnl)
                    trade_log.append({"النوع": "بيع 🔴", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "خسارة ❌", "الربح/الخسارة": round(pnl, 2)})
                    in_trade = False
                elif row['Low'] <= tp:
                    pct_change = (entry - tp) / entry
                    pnl = (position_size * pct_change) - (position_size * fee_rate)
                    trades_pnl.append(pnl)
                    equity.append(equity[-1] + pnl)
                    trade_log.append({"النوع": "بيع 🔴", "الوقت": entry_time, "الدخول": round(entry, 4), "الهدف": round(tp, 4), "ستوب لوس": round(sl, 4), "الحالة": "ربح ✅", "الربح/الخسارة": round(pnl, 2)})
                    in_trade = False
                    
        if not in_trade:
            if row['st_up'] and not prev['st_up']:
                entry = float(row['Close'])
                dist = float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry - dist, entry + (dist * rr_ratio), "BUY", current_time, True
            elif not (is_spot or is_cse) and not row['st_up'] and prev['st_up']:
                entry = float(row['Close'])
                dist = float(row['risk_atr']) * sl_mult
                sl, tp, t_type, entry_time, in_trade = entry + dist, entry - (dist * rr_ratio), "SELL", current_time, True

    last_row = df.iloc[-1]
    current_price = round(float(last_row['Close']), 4)
    current_trend = "صاعد 🟢" if last_row['st_up'] else "هابط 🔴"
    
    active_signal = None
    if in_trade:
        active_signal = {
            "type": "شراء (LONG) 🟢" if t_type == "BUY" else "بيع (SHORT) 🔴",
            "time": entry_time,
            "entry": round(entry, 4),
            "tp": round(tp, 4),
            "sl": round(sl, 4),
            "current": current_price
        }
                
    return trades_pnl, equity, trade_log, active_signal, current_trend, current_price

# 4. واجهة التطبيق
st.markdown("<h2 style='text-align:center; margin-bottom:0;'>⚡ مُقيّم الاستراتيجيات والصفقات</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#a1a1aa; font-size:13px;'>إطار 15 دقيقة • توقيت المغرب (Africa/Casablanca)</p>", unsafe_allow_html=True)

col_t, col_c = st.columns(2)
with col_t:
    tf_choice = st.selectbox("فترة الاختبار", ["يومي (5 أيام)", "أسبوعي (14 يوم)", "شهري (30 يوم)", "أقصى مدة (60 يوم)"], index=2)
    days_map = {"يومي (5 أيام)": 5, "أسبوعي (14 يوم)": 14, "شهري (30 يوم)": 30, "أقصى مدة (60 يوم)": 60}
with col_c:
    cat_choice = st.selectbox("السوق", list(ASSETS.keys()))

asset_name = st.selectbox("اختر الأصل المالي", list(ASSETS[cat_choice]["items"].keys()))
ticker = ASSETS[cat_choice]["items"][asset_name]
currency = ASSETS[cat_choice]["currency"]
is_cse = ASSETS[cat_choice]["is_cse"]

st.markdown("##### 💰 إدارة المحفظة ونوع التداول")
m1, m2, m3 = st.columns(3)
capital = m1.number_input(f"رأس المال ({currency})", value=100.0, min_value=10.0, step=50.0)
trade_mode = m2.selectbox("نوع التداول", ["سبوت (Spot)", "عقود آجلة (Futures)"]) if not is_cse else m2.selectbox("نوع التداول", ["أسهم (شراء فقط)"])
is_spot = True if ("سبوت" in trade_mode or is_cse) else False
leverage = m3.number_input("الرافعة المالية", value=1 if is_spot else 5, min_value=1, max_value=50, disabled=is_spot)

with st.expander("⚙️ إعدادات المؤشر وإدارة المخاطر", expanded=False):
    c1, c2 = st.columns(2)
    st_len = c1.number_input("ATR Length (Supertrend)", value=10, min_value=1)
    st_fac = c2.number_input("Factor (Supertrend)", value=1.0, min_value=0.1, step=0.5)
    c3, c4, c5 = st.columns(3)
    risk_atr = c3.number_input("ATR Length (Risk)", value=14, min_value=1)
