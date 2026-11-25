import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="الدعوم والمقاومات EMA 100 - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=1)
swing_len = st.slider("قوة الدعم والمقاومة (عدد الشموع):", 3, 10, 5)
use_ema100 = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 100)", value=True)

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD", "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD"]
POS_USD = 100.0

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=400)
            if d and len(d) > 110:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms')
                tr = pd.concat([df['h']-df['l'], (df['h']-df['c'].shift()).abs(), (df['l']-df['c'].shift()).abs()], axis=1).max(axis=1)
                df['atr'] = tr.rolling(14).mean()
                df['ema100'] = df['c'].ewm(span=100, adjust=False).mean()
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=10) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

def scan_support_resistance(df, lr, ema_on):
    o, h, l, c, t, atr, ema = df['o'].values, df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['atr'].values, df['ema100'].values
    sigs = []
    used_supports = set()

    for i in range(105, len(df) - 1):
        if np.isnan(atr[i]) or atr[i] == 0: continue

        # 1. فلتر الاتجاه العام EMA 100
        if ema_on and c[i] <= ema[i]:
            continue

        # 2. استخراج الدعوم (القيعان) والمقاومات (القمم) المؤكدة قبل الشمعة الحالية
        limit_idx = i - lr
        if limit_idx <= lr: continue

        supports = [l[k] for k in range(lr, limit_idx) if l[k] == np.min(l[k-lr:k+lr+1])]
        resistances = [h[k] for k in range(lr, limit_idx) if h[k] == np.max(h[k-lr:k+lr+1])]

        if not supports or not resistances: continue

        # اختيار أقرب دعم أسفل أو قريب من السعر الحالي
        valid_sup = [s for s in supports if s <= c[i] and (c[i] - s) / s <= 0.015]
        if not valid_sup: continue
        sup = max(valid_sup) # أقرب دعم

        # تجنب تكرار الدخول من نفس خط الدعم
        sup_key = round(sup, 4)
        if sup_key in used_supports: continue

        # 3. شرط ملامسة الدعم والارتداد بشمعة تأكيد خضراء
        touched_sup = (l[i] <= sup * 1.003) or (l[i-1] <= sup * 1.003)
        not_broken = (c[i] > sup) and (c[i-1] >= sup * 0.997)
        confirmed_bounce = (c[i] > o[i]) and (c[i] > c[i-1])

        if touched_sup and not_broken and confirmed_bounce:
            # 4. تحديد الهدف عند أقرب مقاومة أعلى سعر الدخول
            valid_res = [r for r in resistances if r > c[i] * 1.004]
            if not valid_res: continue
            res = min(valid_res) # أقرب مقاومة للهدف

            entry = c[i]
            sl = sup - (0.3 * atr[i]) # الستوب لوس تحت الدعم
            tp = res                   # الهدف عند المقاومة

            if tp > entry > sl and (tp - entry) >= (entry - sl):
                used_supports.add(sup_key)
                sigs.append((i, pd.Timestamp(t[i]), "شراء من الدعم", f"دعم {sup:.2f} ← مقاومة {res:.2f}", entry, sl, tp))

    return sigs

data = get_data(SYMBOLS, tf)
trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, d, sr_lbl, ent, sl, tp in scan_support_resistance(df, swing_len, use_ema100):
        if idx >= len(df) - 3:
            recs.append((coin, d, sr_lbl, ts.strftime('%Y-%m-%d %H:%M'), ent, sl, tp))

        if ts >= cut:
            out, pnl = "مفتوحة ⏳", 0.0
            for j in range(idx + 1, len(df)):
                fh, fl = df['h'].iloc[j], df['l'].iloc[j]
                if fl <= sl:
                    out, pnl = "خاسرة", -POS_USD * ((ent - sl) / ent)
                    break
                if fh >= tp:
                    out, pnl = "ناجحة", POS_USD * ((tp - ent) / ent)
                    break
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, d, sr_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'النوع', 'الدعم والمقاومة', 'الحالة', 'الربح ($)'])
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
c2.metric("نسبة النجاح (EMA 100)", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث الدعوم والمقاومات الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات الشراء من الدعم (الفرص اللحظية)")
for coin, d, sr_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | {sr_lbl} ({tm} UTC)</b><br>🔹 دخول (الدعم): <code>{ent:.{dec}f}</code> | 🎯 هدف (المقاومة): <code>{tp:.{dec}f}</code> | 🛑 وقف (تحت الدعم): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد فرصة ارتداد من الدعم فوق EMA 100 حالياً.")

st.subheader(f"📋 سجل صفقات آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
