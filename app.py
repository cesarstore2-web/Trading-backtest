import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="موجات إليوت Wave 0 إلى Wave 5 - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=1)
fib_mult = st.selectbox("معامل امتداد الموجة الخامسة (Wave 5 Fib):", [1.618, 2.0, 2.618], index=1)
use_ema = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 100)", value=False)

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD", "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"]
POS_USD = 100.0

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=450)
            if d and len(d) > 120:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms')
                df['ema100'] = df['c'].ewm(span=100, adjust=False).mean()
                delta = df['c'].diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                df['rsi'] = 100 - (100 / (1 + rs))
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=10) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

def scan_elliott_wave0_to_5(df, w5_fib, ema_on):
    o, h, l, c, t, ema, rsi = df['o'].values, df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['ema100'].values, df['rsi'].values
    sigs = []
    last_w0_price = -1.0

    for i in range(105, len(df) - 1):
        if np.isnan(rsi[i]): continue
        if ema_on and c[i] < ema[i]: continue

        # 1. البحث عن أدنى قاع محوري حديث يمثل بداية الموجة الأم (Wave 0)
        lookback_lows = l[i-25:i]
        w0_idx_rel = int(np.argmin(lookback_lows))
        w0_idx = (i - 25) + w0_idx_rel
        w0_price = float(l[w0_idx])

        # يجب أن يكون قاع Wave 0 قد تشكل منذ 2 إلى 6 شموع فقط (بداية الانطلاقة)
        bars_since_w0 = i - w0_idx
        if not (2 <= bars_since_w0 <= 6): continue
        if abs(w0_price - last_w0_price) / w0_price < 0.002: continue

        # 2. التحقق من أن Wave 0 جاء بعد تشبع بيعي وانعكاس حقيقي لبداية Wave 1
        min_rsi_at_w0 = np.min(rsi[max(0, w0_idx-2):w0_idx+2])
        if min_rsi_at_w0 > 42: continue

        # شمعة تأكيد صاعدة تؤكد انطلاق الموجة 1 من قاع Wave 0
        bull_wave1 = (c[i] > o[i]) and (c[i] > np.max(h[w0_idx:i]))
        if not bull_wave1: continue

        # 3. حساب طول الموجة التأسيسية الأولى والتنبؤ بهدف Wave 5
        entry = float(c[i])
        wave1_len = entry - w0_price
        if wave1_len <= 0: continue

        # التنبؤ بسعر Wave 5 بناءً على امتداد فيبوناتشي + آخر مقاومة كبرى
        fib_w5_target = w0_price + (wave1_len * w5_fib)
        last_major_res = float(np.max(h[max(0, i-100):w0_idx]))

        # اختيار الهدف بين امتداد Wave 5 المتوقع وآخر مقاومة كبرى
        if last_major_res > entry * 1.008:
            tp = max(fib_w5_target, last_major_res) if fib_w5_target <= last_major_res * 1.03 else last_major_res
        else:
            tp = fib_w5_target

        # 4. قاعدة إليوت: كسر Wave 0 يلغي الترقيم (الستوب لوس أسفل Wave 0 مباشرة)
        sl = w0_price * 0.996

        if tp > entry > sl and (tp - entry) >= (entry - sl) * 1.5:
            last_w0_price = w0_price
            lbl = f"Wave 0 ({w0_price:.2f}) → هدف W5"
            sigs.append((i, pd.Timestamp(t[i]), lbl, entry, sl, tp))

    return sigs

data = get_data(SYMBOLS, tf)
st.caption(f"حالة الاتصال بالسوق: متصل بـ {len(data)} عملات رقمية نقية")

trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, wave_lbl, ent, sl, tp in scan_elliott_wave0_to_5(df, fib_mult, use_ema):
        if idx >= len(df) - 3:
            recs.append((coin, wave_lbl, ts.strftime('%Y-%m-%d %H:%M'), ent, sl, tp))

        if ts >= cut:
            out, pnl = "مفتوحة ⏳", 0.0
            for j in range(idx + 1, len(df)):
                fh, fl = float(df['h'].iloc[j]), float(df['l'].iloc[j])
                if fl <= sl:
                    out, pnl = "خاسرة", -POS_USD * ((ent - sl) / ent)
                    break
                if fh >= tp:
                    out, pnl = "ناجحة", POS_USD * ((tp - ent) / ent)
                    break
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, "شراء إليوت (W0→W5)", wave_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'الاستراتيجية', 'تفاصيل الموجة', 'الحالة', 'الربح ($)'])
if not df_t.empty:
    df_t = df_t.sort_values('الوقت', ascending=False).reset_index(drop=True)
    cl = df_t[df_t['الحالة'] != 'مفتوحة ⏳']
    w, l, op = len(cl[cl['الحالة']=='ناجحة']), len(cl[cl['الحالة']=='خاسرة']), len(df_t[df_t['الحالة']=='مفتوحة ⏳'])
    wr = (w / len(cl) * 100) if len(cl) > 0 else 0.0
    net = cl['الربح ($)'].sum()
else:
    w, l, op, wr, net = 0, 0, 0, 0.0, 0.0

st.markdown("---")
c1, c2 = st.columns(2)
c1.metric(f"الربح الصافي سبوت ({period_label} | {tf})", f"{net:.2f} $")
c2.metric("نسبة النجاح", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث موجات إليوت الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات موجات إليوت اللحظية (Wave 0 → Wave 5)")
for coin, wave_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | انطلاق من {wave_lbl} ({tm} UTC)</b><br>🔹 دخول (بداية W1): <code>{ent:.{dec}f}</code> | 🎯 هدف (مقاومة W5): <code>{tp:.{dec}f}</code> | 🛑 وقف (تحت W0): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد موجة Wave 0 جديدة مكتملة الانعكاس في آخر شمعتين حالياً.")

st.subheader(f"📋 سجل صفقات إليوت آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
