import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="COINGLASS RSI HEATMAP | EMA50 SNIPER", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px;background:rgba(0,255,102,0.12)}.pend{color:#00ccff;border:1px solid #00ccff;padding:3px 8px;border-radius:4px;background:rgba(0,204,255,0.12)}.wait{color:#888;border:1px solid #444;padding:3px 8px;border-radius:4px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}.pcard{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:12px;text-align:center;box-shadow:0 0 10px rgba(0,255,204,0.15)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>🔥 RSI HEATMAP + EMA 50 TREND SNIPER (BUY ONLY) 🔥</h2><p style='margin:0;color:#aaa;font-size:12px'>شراء قيعان التصحيح (RSI 5m) بشرط صعود EMA 50 (15m) • رأس مال 100$ • خروج ذكي</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات القناص (Inputs)")
    ema_len = st.slider("طول متوسط الاتجاه (على فريم 15m):", 20, 100, 50, 5)
    os_level = st.slider("حد التشبع البيعي للشراء (RSI 5m <=):", 20, 40, 32)
    exit_rsi = st.slider("الخروج الذكي عند وصول RSI إلى:", 55, 75, 62)
    sl_mult = st.slider("وقف الخسارة الحامي (ATR x):", 1.5, 3.5, 2.2, 0.1)
    tp_mult = st.slider("الهدف الأقصى (ATR x):", 1.5, 4.0, 2.5, 0.1)
    st.info("💵 حجم الصفقة ثابت: **100$**\n\n📈 الفلتر: **السعر فوق EMA50 + ميل صاعد**")

c1, c2 = st.columns([2.5, 1.0])
mode = c1.selectbox("اختر العرض:", ["🔥 ALL COINS (التوصيات الفورية والمستقبلية)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث البيانات", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

def heat_style(v):
    if v <= 28: return "background:#00ff66;color:#000;"
    elif v <= 35: return "background:rgba(0,255,102,0.35);color:#00ff66;"
    elif v <= 45: return "background:rgba(0,204,255,0.2);color:#00ccff;"
    return "background:#1e2638;color:#a0aec0;"

@st.cache_data(ttl=60, show_spinner=False)
def fetch_data_30d(tickers_list):
    raw = yf.download(tickers_list, period="30d", interval="5m", group_by="ticker", progress=False)
    out = {}
    for tk in tickers_list:
        try:
            df = raw[tk].dropna() if len(tickers_list) > 1 else raw.dropna()
            out[tk] = df
        except Exception:
            out[tk] = pd.DataFrame()
    return out

def simulate_period(df, candles_back):
    if len(df) < 50: return 0, 0, 0.0
    sub = df.iloc[-min(candles_back, len(df)-2):]
    wins, losses, net = 0, 0, 0.0
    in_pos, ep, slp, tpp = False, 0.0, 0.0, 0.0
    trade_cap = 100.0
    fee = 0.10 # عمولة 0.1%

    for i in range(2, len(sub)):
        bar = sub.iloc[i]
        prev = sub.iloc[i-1]
        if in_pos:
            # 1. ضرب وقف الخسارة
            if bar['Low'] <= slp:
                losses += 1
                net -= trade_cap * ((ep - slp) / ep) + fee
                in_pos = False
            # 2. ضرب الهدف السعري الأقصى
            elif bar['High'] >= tpp:
                wins += 1
                net += trade_cap * ((tpp - ep) / ep) - fee
                in_pos = False
            # 3. الخروج الذكي عند ارتداد RSI لمنطقة التشبع الشرائي وتحقيق ربح
            elif bar['RSI'] >= exit_rsi and bar['Close'] > ep:
                wins += 1
                net += trade_cap * ((float(bar['Close']) - ep) / ep) - fee
                in_pos = False
            continue

        # شروط الشراء: اتجاه EMA50 صاعد + السعر فوقه + ارتداد RSI من التشبع البيعي + شمعة خضراء
        trend_ok = bar['Trend_Up']
        rsi_bounce = (prev['RSI'] <= os_level) and (bar['RSI'] > prev['RSI'])
        green_candle = bar['Close'] > bar['Open']

        if trend_ok and rsi_bounce and green_candle:
            in_pos = True
            ep = float(bar['Close'])
            atr = float(bar['ATR'])
            slp = ep - (sl_mult * atr)
            tpp = ep + (tp_mult * atr)

    return wins, losses, net

def process_coin(df5):
    if df5.empty or len(df5) < 100: return None
    df = df5.copy()
    
    # حساب EMA على فريم 15m (يعادل 3 أضعاف الطول على فريم 5m)
    ema_5m_equiv = ema_len * 3
    df['EMA_TREND'] = ta.trend.ema_indicator(df['Close'], window=ema_5m_equiv)
    # شرط الميل الصاعد: السعر فوق المتوسط + المتوسط الحالي أعلى من قيمته قبل 9 شموع (45 دقيقة)
    df['Trend_Up'] = (df['Close'] > df['EMA_TREND']) & (df['EMA_TREND'] > df['EMA_TREND'].shift(9))
    
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    df = df.dropna()
    if len(df) < 30: return None

    last, prev, curr = df.iloc[-2], df.iloc[-3], df.iloc[-1]
    r_now = float(last['RSI'])
    r_prev = float(prev['RSI'])
    price = float(curr['Close'])
    atr = float(last['ATR'])
    trend_up = bool(last['Trend_Up'])

    # 1. شراء فوري (تحقق الاتجاه الصاعد + ارتداد RSI + شمعة تأكيد خضراء)
    if trend_up and (r_now <= os_level or r_prev <= os_level) and (r_now > r_prev) and (last['Close'] > last['Open']):
        status = "BUY NOW"
        entry = price
        sl = entry - (sl_mult * atr)
        tp = entry + (tp_mult * atr)
    # 2. توصية شراء مستقبلية (الاتجاه صاعد والعملة تهبط للتصحيح نحو منطقة التشبع)
    elif trend_up and r_now <= (os_level + 14):
        status = "FUTURE BUY"
        dist_factor = max((r_now - os_level) / 14.0, 0.35)
        entry = max(price - (dist_factor * atr), float(last['EMA_TREND']))
        sl = entry - (sl_mult * atr)
        tp = entry + (tp_mult * atr)
    else:
        status = "WAIT (DOWNTREND)" if not trend_up else "WAIT"
        entry = float(last['EMA_TREND'])
        sl = entry - (sl_mult * atr)
        tp = entry + (tp_mult * atr)

    w1, l1, n1 = simulate_period(df, 288)
    w7, l7, n7 = simulate_period(df, 2016)
    w30, l30, n30 = simulate_period(df, 8640)

    return {
        "price": price, "rsi": r_now, "trend": trend_up, "status": status,
        "entry": entry, "sl": sl, "tp": tp,
        "1d": (w1, l1, n1), "1w": (w7, l7, n7), "1m": (w30, l30, n30)
    }

tickers = list(pairs.values())
with st.spinner("🔥 جاري تطبيق فلتر الاتجاه EMA 50 واستخراج التوصيات..."):
    all_data = fetch_data_30d(tickers)

if mode == "🔥 ALL COINS (التوصيات الفورية والمستقبلية)":
    rows = ""
    tw1, tl1, tn1 = 0, 0, 0.0
    tw7, tl7, tn7 = 0, 0, 0.0
    tw30, tl30, tn30 = 0, 0, 0.0

    for name, tk in pairs.items():
        res = process_coin(all_data.get(tk, pd.DataFrame()))
        if res:
            w1, l1, n1 = res['1d']; tw1 += w1; tl1 += l1; tn1 += n1
            w7, l7, n7 = res['1w']; tw7 += w7; tl7 += l7; tn7 += n7
            w30, l30, n30 = res['1m']; tw30 += w30; tl30 += l30; tn30 += n30

            t_badge = "<span class='buy'>UP ↗</span>" if res['trend'] else "<span class='wait'>DOWN ↘</span>"
            if res['status'] == "BUY NOW":
                badge = "<span class='buy'>🟢 BUY NOW</span>"
            elif res['status'] == "FUTURE BUY":
                badge = "<span class='pend'>🔵 FUTURE BUY</span>"
            else:
                badge = "<span class='wait'>⏳ WAIT</span>"

            c_1m = "#00ff66" if n30 >= 0 else "#ff0055"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['price'])}</td><td>{t_badge}</td><td style='{heat_style(res['rsi'])}'>{res['rsi']:.1f}</td><td>{badge}</td><td style='color:#00ccff'>{fmt(res['entry'])}</td><td style='color:#ff0055'>{fmt(res['sl'])}</td><td style='color:#00ff66'>{fmt(res['tp'])}</td><td style='color:{c_1m}'>${n30:+.2f}</td></tr>"

    if rows:
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم (24H)', tw1, tl1, tn1)}{render_card('📅 أداء 1 أسبوع (7D)', tw7, tl7, tn7)}{render_card('📅 أداء 1 شهر (30D)', tw30, tl30, tn30)}</div>", unsafe_allow_html=True)
        st.markdown(f"<table><thead><tr><th>العملة</th><th>السعر</th><th>EMA 50</th><th>RSI 5M</th><th>الحالة</th><th>دخول (Entry)</th><th>وقف (SL)</th><th>هدف (TP)</th><th>ربح 30D</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    else:
        st.warning("تعذر جلب البيانات حالياً، اضغط تحديث البيانات.")
else:
    res = process_coin(all_data.get(pairs[mode], pd.DataFrame()))
    if res:
        w1, l1, n1 = res['1d']; w7, l7, n7 = res['1w']; w30, l30, n30 = res['1m']
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
