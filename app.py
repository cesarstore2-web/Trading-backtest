import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="ماسح النماذج - شراء سبوت", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h"], index=0)

if tf == "15m":
    d_atr, d_rr, d_ema = 1.90, 3.20, True
else:
    d_atr, d_rr, d_ema = 2.50, 2.70, False

atr_m = st.number_input("وقف الخسارة (ATR SL):", 0.5, 10.0, d_atr, 0.1, key=f"a_{tf}")
rr_r = st.number_input("نسبة العائد (R:R):", 0.5, 10.0, d_rr, 0.1, key=f"r_{tf}")
use_ema = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=d_ema, key=f"e_{tf}")

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD", "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"]
POS_USD = 100.0

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=500)
            if d and len(d) > 205:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms')
                tr = pd.concat([df['h']-df['l'], (df['h']-df['c'].shift()).abs(), (df['l']-df['c'].shift()).abs()], axis=1).max(axis=1)
                df['atr'] = tr.rolling(14).mean()
                df['ema'] = df['c'].ewm(span=200, adjust=False).mean()
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=10) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

def scan_spot_buy(df, ema_on):
    o, h, l, c, t, atr, ema = df['o'].values, df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['atr'].values, df['ema'].values
    sigs = []
    for i in range(200, len(df) - 1):
        if np.isnan(atr[i]) or atr[i] == 0: continue
        b0, b1, b2 = abs(c[i]-o[i]), abs(c[i-1]-o[i-1]), abs(c[i-2]-o[i-2])
        if b0 == 0 or b1 == 0 or b2 == 0: continue
        
        uw0 = h[i] - max(o[i], c[i])
        lw0 = min(o[i], c[i]) - l[i]
        bull0 = c[i] > o[i]
        bull1, bear1 = c[i-1] > o[i-1], c[i-1] < o[i-1]
        bull2 = c[i-2] > o[i-2]
        
        down_tr = c[i-1] < c[i-3]
        pat = None

        # النماذج الصاعدة فقط (شراء سبوت)
        if down_tr:
            if uw0 >= 1.5 * b0 and lw0 <= 0.5 * b0:
                pat = "المطرقة المقلوبة"
            elif bear1 and bull0 and o[i] <= c[i-1]*1.002 and c[i] > (o[i-1]+c[i-1])/2:
                pat = "خط الاختراق"
            elif bull2 and bull1 and bull0 and (c[i] > c[i-1] > c[i-2]):
                pat = "الجنود الثلاثة البيض"

        if pat:
            if ema_on and c[i] < ema[i]:
                continue
            sigs.append((i, pd.Timestamp(t[i]), "شراء (Spot)", pat, c[i], atr[i]))
    return sigs

data = get_data(SYMBOLS, tf)
trades, recs = [], []
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, d, pat, ent, a_val in scan_spot_buy(df, use_ema):
        sl_d = a_val * atr_m
        tp_d = sl_d * rr_r
        sl = ent - sl_d
        tp = ent + tp_d

        if idx >= len(df) - 3:
            recs.append((coin, d, pat, ts.strftime('%H:%M'), ent, sl, tp))

        if ts >= cut:
            out, pnl = "مفتوحة ⏳", 0.0
            for j in range(idx + 1, len(df)):
                fh, fl = df['h'].iloc[j], df['l'].iloc[j]
                if fl <= sl:
                    out, pnl = "خاسرة", -POS_USD * (sl_d / ent)
                    break
                if fh >= tp:
                    out, pnl = "ناجحة", POS_USD * (tp_d / ent)
                    break
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, d, pat, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'النوع', 'النموذج', 'الحالة', 'الربح ($)'])
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
c1.metric(f"الربح الصافي سبوت (24س | {tf})", f"{net:.2f} $")
c2.metric("نسبة النجاح", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث فرص الشراء الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات شراء سبوت المستقبلية (الفرص اللحظية)")
for coin, d, pat, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | {d} — {pat} ({tm} UTC)</b><br>🔹 دخول: <code>{ent:.{dec}f}</code> | 🎯 هدف: <code>{tp:.{dec}f}</code> | 🛑 وقف: <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد فرصة شراء مكتملة في آخر شمعتين حالياً.")

st.subheader("📋 سجل صفقات الشراء 24 ساعة (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info("لا توجد صفقات شراء مسجلة في آخر 24 ساعة.")
