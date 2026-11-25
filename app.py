import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="Infinity Trend - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

# 1. إعدادات واجهة المستخدم
tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h"], index=0)
c_set1, c_set2 = st.columns(2)
atr_mult = c_set1.number_input("معامل وقف الخسارة (SL):", 1.0, 6.0, 2.5, 0.1)
target_tp = c_set2.selectbox("الهدف المعتمد للحساب:", [f"TP{i}" for i in range(1, 11)], index=3)

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD", "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"]
POS_USD = 100.0
TP_MULTS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0] # 10 أهداف متدرجة

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=300)
            if d and len(d) > 50:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms')
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=10) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

# 2. خوارزمية Infinity Trend (شراء سبوت فقط)
def calc_infinity_trend(df, mult):
    h, l, c = df['h'].values, df['l'].values, df['c'].values
    n = len(df)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    tr = np.insert(tr, 0, h[0] - l[0])
    atr = pd.Series(tr).rolling(10).mean().values

    hl2 = (h + l) / 2.0
    up_band = hl2 + (mult * atr)
    dn_band = hl2 - (mult * atr)

    trend = np.ones(n)
    final_up = np.copy(up_band)
    final_dn = np.copy(dn_band)
    sigs = []

    for i in range(12, n - 1):
        if np.isnan(atr[i]): continue
        final_dn[i] = max(dn_band[i], final_dn[i-1]) if c[i-1] > final_dn[i-1] else dn_band[i]
        final_up[i] = min(up_band[i], final_up[i-1]) if c[i-1] < final_up[i-1] else up_band[i]

        if trend[i-1] == -1 and c[i] > final_up[i-1]:
            trend[i] = 1
            entry = c[i]
            sl = final_dn[i]
            risk = abs(entry - sl)
            if risk > 0:
                tps = [entry + (risk * m) for m in TP_MULTS]
                sigs.append((i, pd.Timestamp(df['t'].iloc[i]), entry, sl, tps))
        elif trend[i-1] == 1 and c[i] < final_dn[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
    return sigs

data = get_data(SYMBOLS, tf)
trades, recs = [], []
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
tp_idx = int(target_tp.replace("TP", "")) - 1

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, ent, sl, tps in calc_infinity_trend(df, atr_mult):
        chosen_tp = tps[tp_idx]
        if idx >= len(df) - 4:
            recs.append((coin, ts.strftime('%H:%M'), ent, sl, tps))
        if ts >= cut:
            out, pnl = "مفتوحة ⏳", 0.0
            for j in range(idx + 1, len(df)):
                fh, fl = df['h'].iloc[j], df['l'].iloc[j]
                if fl <= sl:
                    out, pnl = "خاسرة", -POS_USD * ((ent - sl) / ent)
                    break
                if fh >= chosen_tp:
                    out, pnl = f"ناجحة ({target_tp})", POS_USD * ((chosen_tp - ent) / ent)
                    break
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, "شراء (BUY)", out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'النوع', 'الحالة', 'الربح ($)'])
if not df_t.empty:
    df_t = df_t.sort_values('الوقت', ascending=False).reset_index(drop=True)
    cl = df_t[df_t['الحالة'] != 'مفتوحة ⏳']
    w = len(cl[cl['الحالة'].str.contains('ناجحة')])
    l = len(cl[cl['الحالة'] == 'خاسرة'])
    op = len(df_t[df_t['الحالة'] == 'مفتوحة ⏳'])
    wr = (w / len(cl) * 100) if len(cl) > 0 else 0.0
    net = cl['الربح ($)'].sum()
else:
    w, l, op, wr, net = 0, 0, 0, 0.0, 0.0

# 3. عرض الإحصائيات (24 ساعة | 100$ للصفقة)
st.markdown("---")
c1, c2 = st.columns(2)
c1.metric(f"الربح الصافي (24س | {target_tp})", f"{net:.2f} $")
c2.metric("نسبة النجاح", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث إشارات Infinity Trend", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# 4. عرض التوصيات المستقبلية مع الـ 10 أهداف تماماً مثل الصورة
st.markdown("---")
st.subheader("🎯 توصيات Infinity Trend اللحظية (SL + 10 أهداف)")
if recs:
    for coin, tm, ent, sl, tps in recs:
        dec = 4 if ent < 10 else 2
        tp_html = " | ".join([f"<span style='color:#00e676;'><b>TP{i+1}:</b> {tps[i]:.{dec}f}</span>" for i in range(10)])
        card = f"<div style='background:#12161f;border:1px solid #2b313e;border-right:5px solid #00e676;padding:14px;border-radius:8px;margin-bottom:12px;'>"
        card += f"<div style='font-size:1.15rem;margin-bottom:8px;'><span style='background:#00c853;color:#000;padding:2px 8px;border-radius:4px;font-weight:bold;'>BUY</span> <b style='color:#fff;'>{coin}/USD</b> <span style='color:#888;'>({tm} UTC)</span></div>"
        card += f"<div style='margin-bottom:8px;'><span style='background:#f0b90b;color:#000;padding:2px 6px;border-radius:4px;font-weight:bold;'>ENTRY: {ent:.{dec}f}</span> &nbsp; <span style='background:#ff4b4b;color:#fff;padding:2px 6px;border-radius:4px;font-weight:bold;'>SL: {sl:.{dec}f}</span></div>"
        card += f"<div style='font-size:0.92rem;line-height:1.7;background:#0b0e14;padding:8px;border-radius:6px;'>{tp_html}</div></div>"
        st.markdown(card, unsafe_allow_html=True)
else:
    st.info("لا توجد إشارة انعكاس BUY جديدة في آخر شموع حالياً.")

# 5. سجل صفقات آخر 24 ساعة
st.markdown("---")
st.subheader(f"📋 سجل صفقات 24 ساعة (100$ للصفقة | الهدف: {target_tp})")
if not df_t.empty:
    st.dataframe(df_t, use_container_width=True)
else:
    st.info("لا توجد صفقات مسجلة في آخر 24 ساعة.")
