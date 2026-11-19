import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

# 1. إعدادات الصفحة والتصميم البصري الداكن (Dark Glassmorphism UI)
st.set_page_config(page_title="مُقيّم الاستراتيجيات الذكي", page_icon="📈", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
* { font-family: 'Cairo', sans-serif !important; direction: rtl; text-align: right; }
.stApp { background: radial-gradient(circle at top, #1e1338 0%, #09090f 100%); color: #ffffff; }
.stat-card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
    backdrop-filter: blur(10px);
    text-align: center;
}
.card-green { border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.06); }
.card-red { border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.06); }
.card-title { font-size: 13px; color: #a1a1aa; margin-bottom: 4px; }
.card-value { font-size: 24px; font-weight: 800; }
.green-text { color: #10b981; }
.red-text { color: #ef4444; }
.purple-text { color: #a855f7; }
div.stButton > button {
    width: 100%; border-radius: 12px;
    background: linear-gradient(90deg, #7c3aed 0%, #9333ea 100%);
    color: white; font-weight: 700; border: none; padding: 12px;
}
</style>
""", unsafe_allow_html=True)

# 2. قاعدة بيانات الأصول (العملات الرقمية، الذهب، بورصة الدار البيضاء)
ASSETS = {
    "العملات الرقمية": {
        "currency": "USDT", "is_cse": False,
        "items": {
            "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "XRPUSDT": "XRP-USD",
            "ADAUSDT": "ADA-USD", "SOLUSDT": "SOL-USD", "XLMUSDT": "XLM-USD",
            "ZECUSDT": "ZEC-USD", "HBARUSDT": "HBAR-USD", "LTCUSDT": "LTC-USD"
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

# 3. دوال الحساب الفني (ATR & Supertrend & Backtesting على إطار 15 دقيقة)
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

def run_strategy(ticker, is_cse, period_days, st_len, st_fac, risk_atr_len, sl_mult, rr_ratio):
    # جلب بيانات إطار 15 دقيقة (أقصى مدة متاحة في yfinance لإطار 15m هي 60 يوماً)
    df = yf.download(ticker, period=f"{period_days}d", interval="15m", progress=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    # ضبط التوقيت بتوقيت المغرب (Africa/Casablanca)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')
    
    # فلترة ساعات التداول لبورصة الدار البيضاء (09:30 إلى 15:30)
    if is_cse:
        df = df.between_time('09:30', '15:30')
        
    df = calculate_supertrend(df, st_len, st_fac)
    df['risk_atr'] = calculate_atr(df, risk_atr_len)
    
    trades, equity = [], [0]
    in_trade, t_type, entry, sl, tp = False, None, 0, 0, 0
    
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        if pd.isna(row['risk_atr']):
            continue
        if in_trade:
            if t_type == "BUY":
                if row['Low'] <= sl:
                    pnl = sl - entry
                    trades.append(pnl); equity.append(equity[-1] + pnl); in_trade = False
                elif row['High'] >= tp:
                    pnl = tp - entry
                    trades.append(pnl); equity.append(equity[-1] + pnl); in_trade = False
            elif t_type == "SELL":
                if row['High'] >= sl:
                    pnl = entry - sl
                    trades.append(pnl); equity.append(equity[-1] + pnl); in_trade = False
                elif row['Low'] <= tp:
                    pnl = entry - tp
                    trades.append(pnl); equity.append(equity[-1] + pnl); in_trade = False
                    
        if not in_trade:
            # إشارة الدخول شراء (Supertrend Flip Up)
            if row['st_up'] and not prev['st_up']:
                entry = float(row['Close'])
                dist = float(row['risk_atr']) * sl_mult
                sl, tp, t_type, in_trade = entry - dist, entry + (dist * rr_ratio), "BUY", True
            # إشارة الدخول بيع (للعملات والذهب فقط)
            elif not is_cse and not row['st_up'] and prev['st_up']:
                entry = float(row['Close'])
                dist = float(row['risk_atr']) * sl_mult
                sl, tp, t_type, in_trade = entry + dist, entry - (dist * rr_ratio), "SELL", True
                
    return trades, equity

# 4. واجهة التطبيق (Frontend UI)
st.markdown("<h2 style='text-align:center; margin-bottom:0;'>⚡ تقييم الاستراتيجية (15m)</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#a1a1aa; font-size:13px;'>توقيت المغرب (Africa/Casablanca) • مؤشر Supertrend</p>", unsafe_allow_html=True)

# اختيار الفترة والفيئة والأصل
col_t, col_c = st.columns(2)
with col_t:
    tf_choice = st.selectbox("فترة الاختبار", ["يومي (آخر 5 أيام)", "أسبوعي (آخر 14 يوم)", "شهري (آخر 30 يوم)", "أقصى مدة (60 يوم)"], index=2)
    days_map = {"يومي (آخر 5 أيام)": 5, "أسبوعي (آخر 14 يوم)": 14, "شهري (آخر 30 يوم)": 30, "أقصى مدة (60 يوم)": 60}
with col_c:
    cat_choice = st.selectbox("السوق", list(ASSETS.keys()))

asset_name = st.selectbox("اختر الأصل المالي", list(ASSETS[cat_choice]["items"].keys()))
ticker = ASSETS[cat_choice]["items"][asset_name]
currency = ASSETS[cat_choice]["currency"]
is_cse = ASSETS[cat_choice]["is_cse"]

# مربع إدخال بالذكاء الاصطناعي + إعدادات الصورتين (Supertrend & ATR/RR)
ai_prompt = st.text_input("✨ وصف سريع للاستراتيجية (اختياري)", placeholder="مثال: سوبرتريند 10 و 1 مع وقف خسارة 2 ATR وهدف 1:2")

with st.expander("⚙️ إعدادات المؤشر وإدارة المخاطر (Supertrend & ATR/RR)", expanded=False):
    st.markdown("**1. SUPERTREND (ENTRY)**")
    c1, c2 = st.columns(2)
    st_len = c1.number_input("ATR Length", value=10, min_value=1)
    st_fac = c2.number_input("Factor", value=1.0, min_value=0.1, step=0.5)
    
    st.markdown("**2B. RISK MANAGEMENT (ATR / RR)**")
    c3, c4, c5 = st.columns(3)
    risk_atr = c3.number_input("ATR Length (Risk)", value=14, min_value=1)
    sl_mult = c4.number_input("ATR Multiplier (SL)", value=2.0, min_value=0.1, step=0.5)
    rr_ratio = c5.number_input("Risk-to-Reward (1:X)", value=2.0, min_value=0.5, step=0.5)

# زر التشغيل وعرض لوحة النتائج
if st.button("🚀 تشغيل التقييم الآن"):
    with st.spinner("جاري تحليل شموع 15 دقيقة بتوقيت المغرب..."):
        res = run_strategy(ticker, is_cse, days_map[tf_choice], st_len, st_fac, risk_atr, sl_mult, rr_ratio)
        
    if res is None:
        st.warning("⚠️ تعذر جلب بيانات 15 دقيقة لهذا السهم حالياً (بعض أسهم بورصة الدار البيضاء تتوفر على Yahoo Finance بالفريم اليومي فقط، جرب العملات الرقمية أو الذهب أو سهم ATW).")
    else:
        trades, equity = res
        total = len(trades)
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = round((len(wins) / total) * 100, 1) if total > 0 else 0
        tot_profit = round(sum(wins), 2)
        tot_loss = round(abs(sum(losses)), 2)
        net_profit = round(sum(trades), 2)

        # بطاقة نسبة النجاح
        st.markdown(f"""
        <div class="stat-card">
            <div class="card-title">نسبة النجاح (Win Rate) — إطار 15 دقيقة</div>
            <div class="card-value purple-text">{win_rate}%</div>
        </div>
        """, unsafe_allow_html=True)

        # شبكة البطاقات (مطابقة لتصميم صورتك)
        r1c1, r1c2 = st.columns(2)
        r1c1.markdown(f'<div class="stat-card"><div class="card-title">عدد الصفقات</div><div class="card-value">{total}</div></div>', unsafe_allow_html=True)
        r1c2.markdown(f'<div class="stat-card card-green"><div class="card-title">الصفقات الرابحة</div><div class="card-value green-text">{len(wins)}</div></div>', unsafe_allow_html=True)

        r2c1, r2c2 = st.columns(2)
        r2c1.markdown(f'<div class="stat-card card-red"><div class="card-title">الصفقات الخاسرة</div><div class="card-value red-text">{len(losses)}</div></div>', unsafe_allow_html=True)
        r2c2.markdown(f'<div class="stat-card card-green"><div class="card-title">إجمالي الأرباح</div><div class="card-value green-text">+{tot_profit} {currency}</div></div>', unsafe_allow_html=True)

        r3c1, r3c2 = st.columns(2)
