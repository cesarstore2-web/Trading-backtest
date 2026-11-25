import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="ماسح النماذج", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h"], index=1)
s_len = st.slider("حساسية القمم والقيعان:", 3, 10, 4)
use_ema = st.checkbox("فلتر الاتجاه العام (EMA 200)", value=False)

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD", "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"]
POS_USD = 100.0

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=500)
            if d and len(d) > 60:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms')
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

def scan(df, lr, ema_on):
    h, l, c, t, ema = df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['ema'].values
    ph = [(i, h[i]) for i in range(lr, len(df)-lr) if h[i] == np.max(h[i-lr:i+lr+1])]
    pl = [(i, l[i]) for i in range(lr, len(df)-lr) if l[i] == np.min(l[i-lr:i+lr+1])]
    sigs = []

    # 1 & 3: التنين + القاع المزدوج وكسر الترند (شراء)
    for k in range(1, len(pl)):
        i1, p1 = pl[k-1]
        i2, p2 = pl[k]
        if not (4 <= i2 - i1 <= 60) or abs(p2 - p1)/p1 > 0.015: continue
        mh = [x for x in ph if i1 < x[0] < i2]
        hh = [x for x in ph if x[0] < i1 and i1 - x[0] < 60]
        if not mh or not hh: continue
        ih, ph_p = max(mh, key=lambda x: x[1])
        id_h, hd_p = max(hh, key=lambda x: x[1])
        if hd_p <= ph_p or ph_p <= max(p1, p2): continue
        slope = (ph_p - hd_p) / (ih - id_h)
        for i in range(i2+1, min(i2+25, len(df)-1)):
            tr = hd_p + slope * (i - id_h)
            if c[i] > tr and c[i-1] <= (hd_p + slope * (i-1 - id_h)):
                if ema_on and c[i] < ema[i]: break
                pat = "قاع مزدوج + ترند (صورة 3)" if c[i] >= ph_p else "نموذج التنين (صورة 1)"
                sl, tp = min(p1, p2)*0.998, hd_p
                if tp > c[i] > sl:
                    sigs.append((i, pd.Timestamp(t[i]), "شراء (Long)", pat, c[i], sl, tp))
                break

    # 2: كسر الترند الصاعد + FVG (بيع)
    for k in range(1, len(ph)):
        i1, p1 = ph[k-1]
        i2, p2 = ph[k]
        if p2 <= p1 or not (5 <= i2 - i1 <= 50): continue
        lb = [x for x in pl if x[0] < i1 and i1 - x[0] < 40]
        ml = [x for x in pl if i1 < x[0] < i2]
        if not lb or not ml: continue
        il1, pl1 = min(lb, key=lambda x: x[1])
        il2, pl2 = min(ml, key=lambda x: x[1])
        if pl2 <= pl1: continue
        slope = (pl2 - pl1) / (il2 - il1)
        f_top, f_bot = None, None
        for i in range(i2+2, min(i2+25, len(df)-1)):
            tr = pl1 + slope * (i - il1)
            if f_top is None and l[i-2] > h[i] and c[i] < tr:
                f_top, f_bot = l[i-2], h[i]
                continue
            if f_top is not None:
                if h[i] >= f_bot and c[i] <= f_top:
                    if ema_on and c[i] > ema[i]: break
                    sl, tp = f_top*1.002, pl1
                    if sl > c[i] > tp:
                        sigs.append((i, pd.Timestamp(t[i]), "بيع (Short)", "كسر ترند + FVG (صورة 2)", c[i], sl, tp))
                    break
                elif h[i] > f_top*1.005: break
    return sigs

data = get_data(SYMBOLS, tf)
trades, recs = [], []
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, d, pat, ent, sl, tp in scan(df, s_len, use_ema):
        if idx >= len(df) - 5:
            recs.append((coin, d, pat, ts.strftime('%H:%M'), ent, sl, tp))
        if ts >= cut:
            is_l = "شراء" in d
            out, pnl = "مفتوحة ⏳", 0.0
            for j in range(idx+1, len(df)):
                fh, fl = df['h'].iloc[j], df['l'].iloc[j]
                if is_l:
                    if fl <= sl: out, pnl = "خاسرة", -POS_USD*(abs(ent-sl)/ent); break
                    if fh >= tp: out, pnl = "ناجحة", POS_USD*(abs(tp-ent)/ent); break
                else:
                    if fh >= sl: out, pnl = "خاسرة", -POS_USD*(abs(ent-sl)/ent); break
                    if fl <= tp: out, pnl = "ناجحة", POS_USD*(abs(tp-ent)/ent); break
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
c1.metric(f"الربح الصافي (24س | {tf})", f"{net:.2f} $")
c2.metric("نسبة النجاح", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات مستقبلية (الفرص اللحظية)")
for coin, d, pat, tm, ent, sl, tp in recs:
    ib = "شراء" in d
    col = "#00e676" if ib else "#ff5252"
    bg = "#00c85326" if ib else "#ff4b4b26"
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:{bg};border-right:5px solid {col};padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:{col};font-size:1.1rem;'>{'🟢' if ib else '🔴'} {coin} | {d} — {pat} ({tm})</b><br>🔹 دخول: <code>{ent:.{dec}f}</code> | 🎯 هدف: <code>{tp:.{dec}f}</code> | 🛑 وقف: <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد إشارة لحظية حالياً.")

st.subheader("📋 سجل صفقات 24 ساعة (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info("لا توجد صفقات مسجلة في آخر 24 ساعة.")
