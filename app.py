import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="FIBONACCI SPOT SNIPER | 0.382 & 0.50", layout="wide")

st.markdown("<style>.stApp{background-color:#0b0e14;color:#fff;font-family:monospace}.hdr{border:2px solid #00ffcc;border-radius:10px;padding:12px;text-align:center;background:#0d1b2a;margin-bottom:15px}table{width:100%;border-collapse:collapse;background:#131926;border:1px solid #00ffcc;margin-top:10px}th{background:#0d1b2a;color:#00ffcc;padding:10px;border-bottom:2px solid #00ffcc;font-size:12px}td{padding:8px;border-bottom:1px solid #233044;text-align:center;font-weight:bold;font-size:12px}.buy{color:#00ff66;border:1px solid #00ff66;padding:3px 8px;border-radius:4px;background:rgba(0,255,102,0.12)}.pend{color:#00ccff;border:1px solid #00ccff;padding:3px 8px;border-radius:4px;background:rgba(0,204,255,0.12)}.wait{color:#888;border:1px solid #444;padding:3px 8px;border-radius:4px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}.pcard{background:#131926;border:1px solid #00ffcc;border-radius:8px;padding:12px;text-align:center;box-shadow:0 0 10px rgba(0,255,204,0.15)}</style>", unsafe_allow_html=True)

st.markdown("<div class='hdr'><h2 style='margin:0;color:#00ffcc'>📐 FIBONACCI RETRACEMENT SPOT SNIPER (0.382 & 0.50) 📐</h2><p style='margin:0;color:#aaa;font-size:12px'>تداول فوري (Spot) شراء فقط • اقتناص تصحيح الموجات الصاعدة • 100$ للصفقة</p></div>", unsafe_allow_html=True)

pairs = {"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","XRPUSDT":"XRP-USD","ADAUSDT":"ADA-USD","XLMUSDT":"XLM-USD","HBARUSDT":"HBAR-USD","LTCUSDT":"LTC-USD","ZECUSDT":"ZEC-USD","PAXGUSDT":"PAXG-USD"}

with st.sidebar:
    st.header("⚙️ إعدادات الفيبوناتشي (Spot)")
    swing_lookback = st.slider("طول الموجة بالساعات (Swing Window):", 24, 72, 48, 6)
    fib_entry_choice = st.radio("مستوى الدخول المفضل:", ["0.50 (الذهبي المتوازن)", "0.382 (التصحيح السريع)"])
    min_wave_pct = st.slider("أقل حجم للموجة الصاعدة (%):", 1.5, 6.0, 2.5, 0.5)
    st.info("📐 **قواعد الفيبوناتشي في الكود:**\n\n1. التأكد أن الموجة صاعدة (القاع قبل القمة).\n\n2. الشراء عند لمس 0.382 أو 0.50 مع شمعة ارتداد خضراء.\n\n3. وقف الخسارة أسفل 0.65 والهدف القمة 0.0.")

c1, c2 = st.columns([2.5, 1.0])
mode = c1.selectbox("اختر العرض:", ["📐 ALL COINS (مستويات الفيبوناتشي الفورية والمستقبلية)"] + list(pairs.keys()), label_visibility="collapsed")
if c2.button("🔄 تحديث المستويات", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

def fmt(p):
    return f"{p:.5f}" if p < 1 else (f"{p:.4f}" if p < 50 else f"{p:.2f}")

@st.cache_data(ttl=120, show_spinner=False)
def fetch_data_60d(tickers_list):
    raw = yf.download(tickers_list, period="60d", interval="1h", group_by="ticker", progress=False)
    out = {}
    for tk in tickers_list:
        try:
            df = raw[tk].dropna() if len(tickers_list) > 1 else raw.dropna()
            out[tk] = df
        except Exception:
            out[tk] = pd.DataFrame()
    return out

def calc_fib_levels(sub_df):
    low_idx = sub_df['Low'].idxmin()
    high_idx = sub_df['High'].idxmax()
    swing_low = float(sub_df.loc[low_idx, 'Low'])
    swing_high = float(sub_df.loc[high_idx, 'High'])
    
    # يجب أن يكون القاع قد حدث قبل القمة (موجة صاعدة) وحجم الموجة كافٍ
    wave_pct = ((swing_high - swing_low) / max(swing_low, 1e-9)) * 100
    is_bull_impulse = (low_idx < high_idx) and (wave_pct >= min_wave_pct)
    
    diff = swing_high - swing_low
    f_382 = swing_high - (0.382 * diff)
    f_500 = swing_high - (0.500 * diff)
    f_618 = swing_high - (0.618 * diff)
    sl_lvl = swing_high - (0.680 * diff) # وقف الخسارة أسفل الكسر الذهبي 0.618
    
    return is_bull_impulse, swing_low, swing_high, f_382, f_500, f_618, sl_lvl

def simulate_fib(df, hours_back):
    if len(df) < swing_lookback + 20: return 0, 0, 0.0
    start_i = max(swing_lookback + 1, len(df) - hours_back)
    wins, losses, net = 0, 0, 0.0
    in_pos, ep, slp, tpp = False, 0.0, 0.0, 0.0
    trade_cap = 100.0
    fee = 0.10
    use_50 = fib_entry_choice.startswith("0.50")

    for i in range(start_i, len(df) - 1):
        bar = df.iloc[i]
        if in_pos:
            if bar['Low'] <= slp:
                losses += 1
                net -= trade_cap * ((ep - slp) / ep) + fee
                in_pos = False
            elif bar['High'] >= tpp:
                wins += 1
                net += trade_cap * ((tpp - ep) / ep) - fee
                in_pos = False
            continue

        window_df = df.iloc[i - swing_lookback : i]
        is_bull, s_low, s_high, f382, f500, f618, sl_lvl = calc_fib_levels(window_df)
        target_entry = f500 if use_50 else f382

        # شرط الدخول: موجة صاعدة + السعر يلمس مستوى فيبوناتشي + إغلاق شمعة ارتداد خضراء فوق المستوى
        if is_bull and (bar['Low'] <= target_entry) and (bar['Close'] > target_entry) and (bar['Close'] > bar['Open']):
            in_pos = True
            ep = float(bar['Close'])
            slp = sl_lvl
            tpp = s_high # الهدف العودة لقمة الموجة 0.0 Fib

    return wins, losses, net

def process_coin(df1h):
    if df1h.empty or len(df1h) < swing_lookback + 10: return None
    df = df1h.copy()
    last, curr = df.iloc[-2], df.iloc[-1]
    price = float(curr['Close'])
    
    window_now = df.iloc[-swing_lookback-1 : -1]
    is_bull, s_low, s_high, f382, f500, f618, sl_lvl = calc_fib_levels(window_now)
    chosen_fib = f500 if fib_entry_choice.startswith("0.50") else f382

    if is_bull and (last['Low'] <= chosen_fib) and (last['Close'] > chosen_fib) and (last['Close'] > last['Open']):
        status = "BUY FIB NOW"
        entry = price
    elif is_bull and price > chosen_fib:
        status = "FIB BUY LIMIT"
        entry = chosen_fib
    else:
        status = "NO BULL WAVE"
        entry = f500

    w1, l1, n1 = simulate_fib(df, 24)
    w7, l7, n7 = simulate_fib(df, 168)
    w30, l30, n30 = simulate_fib(df, 720)

    return {
        "price": price, "is_bull": is_bull, "status": status,
        "f382": f382, "f500": f500, "entry": entry, "sl": sl_lvl, "tp": s_high,
        "1d": (w1, l1, n1), "1w": (w7, l7, n7), "1m": (w30, l30, n30)
    }

tickers = list(pairs.values())
with st.spinner("📐 جاري رسم مستويات الفيبوناتشي (0.382 / 0.50) على الموجات الصاعدة..."):
    all_data = fetch_data_60d(tickers)

if mode == "📐 ALL COINS (مستويات الفيبوناتشي الفورية والمستقبلية)":
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

            if res['status'] == "BUY FIB NOW":
                badge = "<span class='buy'>🟢 BUY NOW</span>"
            elif res['status'] == "FIB BUY LIMIT":
                badge = "<span class='pend'>🔵 BUY LIMIT</span>"
            else:
                badge = "<span class='wait'>⏳ DOWN WAVE</span>"

            c_1m = "#00ff66" if n30 >= 0 else "#ff0055"
            rows += f"<tr><td style='color:#00ffcc'>{name}</td><td>{fmt(res['price'])}</td><td>{badge}</td><td style='color:#00ccff'>{fmt(res['f382'])}</td><td style='color:#00ccff'>{fmt(res['f500'])}</td><td style='color:#ff0055'>{fmt(res['sl'])}</td><td style='color:#00ff66'>{fmt(res['tp'])}</td><td style='color:{c_1m}'>${n30:+.2f}</td></tr>"

    if rows:
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم (24H)', tw1, tl1, tn1)}{render_card('📅 أداء 1 أسبوع (7D)', tw7, tl7, tn7)}{render_card('📅 أداء 1 شهر (30D)', tw30, tl30, tn30)}</div>", unsafe_allow_html=True)
        st.markdown(f"<table><thead><tr><th>العملة</th><th>السعر</th><th>الحالة</th><th>Fib 0.382</th><th>Fib 0.50</th><th>وقف (0.68)</th><th>هدف (0.0)</th><th>ربح 30D</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    else:
        st.warning("تعذر جلب البيانات حالياً، اضغط تحديث المستويات.")
else:
    res = process_coin(all_data.get(pairs[mode], pd.DataFrame()))
    if res:
        w1, l1, n1 = res['1d']; w7, l7, n7 = res['1w']; w30, l30, n30 = res['1m']
        def render_card(title, w, l, net):
            wr = (w / (w + l) * 100) if (w + l) > 0 else 0.0
            nc = "#00ff66" if net >= 0 else "#ff0055"
            return f"<div class='pcard'><div style='color:#00ffcc;font-weight:bold;margin-bottom:6px'>{title}</div><div style='font-size:13px'>ناجحة: <b style='color:#00ff66'>{w}</b> &nbsp;|&nbsp; خاسرة: <b style='color:#ff0055'>{l}</b></div><div style='font-size:12px;color:#aaa;margin:4px 0'>نسبة النجاح: <b>{wr:.1f}%</b></div><div style='font-size:18px;font-weight:bold;color:{nc}'>الربح الصافي: ${net:+.2f}</div></div>"

        st.markdown(f"<div class='grid3'>{render_card('📅 أداء 1 يوم', w1, l1, n1)}{render_card('📅 أداء 1 أسبوع', w7, l7, n7)}{render_card('📅 أداء 1 شهر', w30, l30, n30)}</div>", unsafe_allow_html=True)
        b_col = "#00ff66" if res['status']=="BUY FIB NOW" else ("#00ccff" if res['status']=="FIB BUY LIMIT" else "#ffcc00")
