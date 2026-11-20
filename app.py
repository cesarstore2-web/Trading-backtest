import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Supertrend Multi-TP & EMA 200", page_icon="⚡", layout="centered")

st.markdown("""
<style>
@import url('https://googleapis.com');
html, body, [class*="css"] { font-family: 'Cairo', sans-serif; }
.stApp { background: radial-gradient(circle at top, #1e1338 0%, #09090f 100%); color: #ffffff; direction: rtl; text-align: right; }
.stat-card { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 15px; margin-bottom: 12px; text-align: center; }
.card-green { border-color: rgba(16, 185, 129, 0.45); background: rgba(16, 185, 129, 0.07); }
.card-red { border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.07); }
.card-signal { border-color: rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.12); text-align: right; padding: 18px; line-height: 1.8; }
.card-title { font-size: 13px; color: #a1a1aa; margin-bottom: 4px; }
.card-value { font-size: 23px; font-weight: 800; }
.green-text { color: #10b981; }
.red-text { color: #ef4444; }
.purple-text { color: #a855f7; }
div.stButton > button { width: 100%; border-radius: 12px; background: linear-gradient(90deg, #7c3aed 0%, #9333ea 100%); color: white; font-weight: 700; border: none; padding: 14px; font-size: 16px; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

ASSETS = {
    "العملات الرقمية": {
        "currency": "USDT",
        "is_cse": False,
        "items": {
            "XLMUSDT": "XLM-USD",
            "ZECUSDT": "ZEC-USD",
            "XRPUSDT": "XRP-USD",
            "HBARUSDT": "HBAR-USD",
            "ADAUSDT": "ADA-USD",
            "LTCUSDT": "LTC-USD",
            "BTCUSDT": "BTC-USD",
            "ETHUSDT": "ETH-USD"
        }
    },
    "الذهب": {
        "currency": "USDT",
        "is_cse": False,
        "items": {
            "XAUUSDT (الذهب)": "GC=F",
            "PAXGUSDT": "PAXG-USD"
        }
    },
    "بورصة الدار البيضاء": {
        "currency": "MAD",
        "is_cse": True,
        "items": {
            "ATW - التجاري وفا بنك": "ATW.CS",
            "BCP - البنك الشعبي": "BCP.CS",
            "AKT - أكديطال": "AKT.CS",
            "MNG - مناجم": "MNG.CS",
            "TGC - TGCC": "TGC.CS",
            "ADH - الضحى": "ADH.CS",
            "JET - جيت كونتراكترز": "JET.CS",
            "MSA - مرسى المغرب": "MSA.CS",
            "CMA - إسمنت المغرب": "CMA.CS",
            "LHM - لافارج هولسيم": "LHM.CS",
            "ATL - أطلنطا سند": "ATL.CS",
            "DHO - دلتا هولدينغ": "DHO.CS"
        }
    }
}

def calculate_atr(df, length=14):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(length).mean()

def apply_supertrend_ema200(df, st_len=10, st_fac=3.0, use_ema200=True):
    atr = calculate_atr(df, st_len)
    hl2 = (df['High'] + df['Low']) / 2
    upper = hl2 + (st_fac * atr)
    lower = hl2 - (st_fac * atr)
    uptrend = [True for _ in range(len(df))]
    
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
    df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    st_buy = df['st_up'] & (~df['st_up'].shift(1).fillna(False))
    st_sell = (~df['st_up']) & (df['st_up'].shift(1).fillna(True))
    
    if use_ema200:
        df['buy_sig'] = st_buy & (df['Close'] > df['ema200'])
        df['sell_sig'] = st_sell & (df['Close'] < df['ema200'])
    else:
        df['buy_sig'] = st_buy
        df['sell_sig'] = st_sell
    return df

def run_strategy(ticker, is_cse, timeframe, period_days, st_len, st_fac, use_ema200, atr_len, sl_mult, tp1_m, tp2_m, tp3_m, capital, leverage, is_spot, use_session):
    actual_days = min(period_days, 7) if timeframe in ["3m", "5m"] else period_days
    df = yf.download(ticker, period=f"{actual_days}d", interval=timeframe, progress=False)
    
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Africa/Casablanca')

    df = apply_supertrend_ema200(df, st_len, st_fac, use_ema200)
    df['atr'] = calculate_atr(df, atr_len)

    fee_rate = 0.002 if (is_spot or is_cse) else 0.001
    pos_size = capital * (1 if (is_spot or is_cse) else leverage)
    part_size = pos_size / 3.0

    trades_pnl = []
    trades_history = []
    in_trade, t_type, entry, sl, tp1, tp2, tp3, entry_time = False, None, 0, 0, 0, 0, 0, ""
    hit_tp1, hit_tp2, current_trade_pnl = False, False, 0.0

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = df.index[i]
        c_time = ts.strftime("%Y-%m-%d %H:%M")
        if pd.isna(row['atr']):
            continue

        if in_trade:
            if t_type == "BUY":
                if row['Low'] <= sl:
                    rem_parts = 3 - (1 if hit_tp1 else 0) - (1 if hit_tp2 else 0)
                    pnl_close = (part_size * rem_parts) * ((sl - entry) / entry) - ((part_size * rem_parts) * fee_rate)
                    total_trade_pnl = current_trade_pnl + pnl_close
                    trades_pnl.append(total_trade_pnl)
                    
                    close_reason = "تأمين الدخول (BE)" if hit_tp1 else "وقف الخسارة (SL)"
                    trades_history.append({
                        "النوع": "شراء 🟢",
                        "وقت الدخول": entry_time,
                        "وقت الخروج": c_time,
                        "سعر الدخول": round(entry, 4),
                        "سعر الخروج": round(sl, 4),
                        "الحالة": close_reason,
                        "الربح/الخسارة": round(total_trade_pnl, 2)
                    })
                    in_trade = False
                else:
                    if not hit_tp1 and row['High'] >= tp1:
                        hit_tp1 = True
                        current_trade_pnl += part_size * ((tp1 - entry) / entry) - (part_size * fee_rate)
                        sl = entry
                    if not hit_tp2 and row['High'] >= tp2:
                        hit_tp2 = True
                        current_trade_pnl += part_size * ((tp2 - entry) / entry) - (part_size * fee_rate)
                    if row['High'] >= tp3:
                        current_trade_pnl += part_size * ((tp3 - entry) / entry) - (part_size * fee_rate)
                        trades_pnl.append(current_trade_pnl)
                        trades_history.append({
                            "النوع": "شراء 🟢",
                            "وقت الدخول": entry_time,
                            "وقت الخروج": c_time,
                            "سعر الدخول": round(entry, 4),
                            "سعر الخروج": round(tp3, 4),
                            "الحالة": "هدف كامل (TP3) 🎯",
                            "الربح/الخسارة": round(current_trade_pnl, 2)
                        })
                        in_trade = False

            elif t_type == "SELL":
                if row['High'] >= sl:
                    rem_parts = 3 - (1 if hit_tp1 else 0) - (1 if hit_tp2 else 0)
                    pnl_close = (part_size * rem_parts) * ((entry - sl) / entry) - ((part_size * rem_parts) * fee_rate)
                    total_trade_pnl = current_trade_pnl + pnl_close
                    trades_pnl.append(total_trade_pnl)
                    
                    close_reason = "تأمين الدخول (BE)" if hit_tp1 else "وقف الخسارة (SL)"
                    trades_history.append({
                        "النوع": "بيع 🔴",
                        "وقت الدخول": entry_time,
                        "وقت الخروج": c_time,
                        "سعر الدخول": round(entry, 4),
                        "سعر الخروج": round(sl, 4),
                        "الحالة": close_reason,
                        "الربح/الخسارة": round(total_trade_pnl, 2)
                    })
                    in_trade = False
                else:
                    if not hit_tp1 and row['Low'] <= tp1:
                        hit_tp1 = True
                        current_trade_pnl += part_size * ((entry - tp1) / entry) - (part_size * fee_rate)
                        sl = entry
                    if not hit_tp2 and row['Low'] <= tp2:
                        hit_tp2 = True
                        current_trade_pnl += part_size * ((entry - tp2) / entry) - (part_size * fee_rate)
                    if row['Low'] <= tp3:
                        current_trade_pnl += part_size * ((entry - tp3) / entry) - (part_size * fee_rate)
                        trades_pnl.append(current_trade_pnl)
                        trades_history.append({
                            "النوع": "بيع 🔴",
                            "وقت الدخول": entry_time,
                            "وقت الخروج": c_time,
                            "سعر الدخول": round(entry, 4),
                            "سعر الخروج": round(tp3, 4),
                            "الحالة": "هدف كامل (TP3) 🎯",
                            "الربح/الخسارة": round(current_trade_pnl, 2)
                        })
                        in_trade = False

        in_session = True
        if is_cse:
            in_session = (ts.hour > 9 or (ts.hour == 9 and ts.minute >= 30)) and (ts.hour < 15 or (ts.hour == 15 and ts.minute <= 30))
        elif use_session:
    total_trades = len(trades_pnl)
    winning_trades = len([p for p in trades_pnl if p > 0])
    losing_trades = len([p for p in trades_pnl if p <= 0])
    net_profit = sum(trades_pnl)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "net_profit": net_profit,
        "win_rate": win_rate,
        "in_trade": in_trade,
        "t_type": t_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "entry_time": entry_time,
        "history": trades_history
    }

# --- واجهة المستخدم ---
st.title("⚡ نظام Supertrend Multi-TP & EMA 200")

col1, col2 = st.columns(2)
with col1:
    category = st.selectbox("اختر السوق", list(ASSETS.keys()))
    asset_name = st.selectbox("اختر الأصل", list(ASSETS[category]["items"].keys()))
    ticker = ASSETS[category]["items"][asset_name]
    is_cse = ASSETS[category]["is_cse"]
    currency = ASSETS[category]["currency"]

with col2:
    period_options = {
        "7 أيام (أسبوع)": 7,
        "14 يوماً (أسبوعين)": 14,
        "30 يوماً (شهر)": 30,
        "90 يوماً (3 أشهر)": 90,
        "180 يوماً (6 أشهر)": 180,
        "365 يوماً (سنة)": 365
    }
    selected_period_label = st.selectbox("فترة الاختبار", list(period_options.keys()), index=2)
    period_days = period_options[selected_period_label]
    
    available_tf = ["5m", "15m", "30m", "1h", "4h", "1d"]
    if period_days > 7:
        available_tf.remove("5m")
    if period_days > 60:
        available_tf = ["1h", "4h", "1d"]
        
    timeframe = st.selectbox("الإطار الزمني", available_tf, index=min(2, len(available_tf)-1))
    capital = st.number_input(f"رأس المال ({currency})", min_value=10.0, value=1000.0, step=100.0)

with st.expander("⚙️ إعدادات المؤشرات وإدارة المخاطر"):
    c1, c2, c3 = st.columns(3)
    st_len = c1.number_input("طول Supertrend", value=10)
    st_fac = c2.number_input("معامل Supertrend", value=3.0)
    use_ema200 = c3.checkbox("تفعيل فلتر EMA 200", value=True)
    
    c4, c5, c6, c7 = st.columns(4)
    sl_mult = c4.number_input("مضاعف الوقف SL", value=1.5)
    tp1_m = c5.number_input("هدف 1 (ATR)", value=1.0)
    tp2_m = c6.number_input("هدف 2 (ATR)", value=2.0)
    tp3_m = c7.number_input("هدف 3 (ATR)", value=3.0)
    
    leverage = st.slider("الرافعة المالية (للعملات والذهب)", 1, 20, 1)
    is_spot = st.checkbox("تداول فوري (Spot - شراء فقط)", value=True)
    use_session = st.checkbox("تقييد التداول بجلسة العمل", value=False)

st.button("🔄 تحديث البيانات الآن")

with st.spinner(f"جاري حساب النتائج لفترة {selected_period_label}..."):
    res = run_strategy(ticker, is_cse, timeframe, period_days, st_len, st_fac, use_ema200, 14, sl_mult, tp1_m, tp2_m, tp3_m, capital, leverage, is_spot, use_session)
    
    if res is None:
        st.error("⚠️ تعذر جلب بيانات كافية لهذه الفترة أو الإطار الزمني. جرب تكبير الإطار الزمني (مثلاً 1h أو 4h).")
    else:
        roi_pct = (res["net_profit"] / capital) * 100
        profit_class = "card-green" if res["net_profit"] >= 0 else "card-red"
        profit_text_class = "green-text" if res["net_profit"] >= 0 else "red-text"
        sign = "+" if res["net_profit"] > 0 else ""
        
        r1, r2 = st.columns(2)
        with r1:
            st.markdown(f"""
            <div class="stat-card {profit_class}">
                <div class="card-title">الربح الصافي ({selected_period_label})</div>
                <div class="card-value {profit_text_class}">{sign}{res['net_profit']:.2f} {currency} ({sign}{roi_pct:.1f}%)</div>
            </div>
            """, unsafe_allow_html=True)
        with r2:
            st.markdown(f"""
            <div class="stat-card">
                <div class="card-title">نسبة النجاح (Win Rate)</div>
                <div class="card-value purple-text">{res['win_rate']:.1f}% ({res['total_trades']} صفقة)</div>
            </div>
            """, unsafe_allow_html=True)

        r3, r4 = st.columns(2)
        with r3:
            st.markdown(f"""
            <div class="stat-card card-green">
                <div class="card-title">الصفقات الناجحة</div>
                <div class="card-value green-text">{res['winning_trades']}</div>
            </div>
            """, unsafe_allow_html=True)
        with r4:
            st.markdown(f"""
            <div class="stat-card card-red">
                <div class="card-title">الصفقات الخاسرة</div>
                <div class="card-value red-text">{res['losing_trades']}</div>
            </div>
            """, unsafe_allow_html=True)

        if res["in_trade"]:
            st.markdown(f"""
            <div class="stat-card card-signal">
                <strong class="purple-text">🔔 توجد صفقة مفتوحة حالياً ({res['t_type']})</strong><br>
                • وقت الدخول: {res['entry_time']}<br>
                • سعر الدخول: <b>{res['entry']:.4f}</b><br>
                • وقف الخسارة (SL): <span class="red-text">{res['sl']:.4f}</span><br>
                • الأهداف: TP1: <b>{res['tp1']:.4f}</b> | TP2: <b>{res['tp2']:.4f}</b> | TP3: <b>{res['tp3']:.4f}</b>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 📋 سجل الصفقات التاريخية")
        if res["history"]:
            df_history = pd.DataFrame(res["history"]).iloc[::-1].reset_index(drop=True)
            
            def color_pnl(val):
                color = '#10b981' if val > 0 else ('#ef4444' if val < 0 else '#a1a1aa')
                return f'color: {color}; font-weight: bold;'

            try:
                styled_df = df_history.style.map(color_pnl, subset=['الربح/الخسارة'])
            except AttributeError:
                styled_df = df_history.style.applymap(color_pnl, subset=['الربح/الخسارة'])
                
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"لم يتم إغلاق أي صفقات خلال فترة ({selected_period_label}).")
