import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="مطابقة الأنماط + الدعوم والمقاومات", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=1)
min_corr = st.slider("دقة تطابق النمط التاريخي (%):", 55, 95, 70) / 100.0
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
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=10) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

# دالة حساب التطابق المباشرة (تُرجع رقماً واحداً نظيفاً دون مصفوفات)
def fast_corr(x, y):
    xm = x - np.mean(x)
    ym = y - np.mean(y)
    denom = np.sqrt(np.sum(xm**2) * np.sum(ym**2))
    return float(np.sum(xm * ym) / denom) if denom > 0 else 0.0

def scan_pattern_with_sr(df, corr_thresh, ema_on):
    c, h, l, t, ema = df['c'].values, df['h'].values, df['l'].values, df['t'].values, df['ema100'].values
    win = 14   # طول النمط (14 شمعة)
    fwd = 12   # مدى التوقع المستقبلي (12 شمعة)
    sigs = []
    last_sig_idx = -8

    for i in range(105, len(df) - 1):
        if i - last_sig_idx < 6: continue
        if ema_on and c[i] < ema[i]: continue

        # 1. استخراج الدعوم والمقاومات المحورية
        low_win = l[max(0, i-70):i]
        high_win = h[max(0, i-70):i]
        sup = float(np.min(low_win[-35:]))
        res = float(np.max(high_win[:-3]))

        # احترام الدعم: السعر قريب من منطقة الدعم (ضمن 3.5%) وفوقها
        if c[i] <= sup or ((c[i] - sup) / sup) > 0.035:
            continue

        # 2. مطابقة النمط التاريخي
        curr_pat = c[i - win + 1 : i + 1]
        best_corr = -1.0
        best_j = -1

        for j in range(win, i - win - fwd):
            hist_pat = c[j - win + 1 : j + 1]
            cv = fast_corr(curr_pat, hist_pat)
            if cv > best_corr:
                best_corr = cv
                best_j = j

        # 3. التحقق من التطابق واحترام المقاومة والدعم
        if best_corr >= corr_thresh and best_j != -1:
            hist_entry = c[best_j]
            fut_high = float(np.max(h[best_j + 1 : best_j + fwd + 1]))
            up_pct = (fut_high - hist_entry) / hist_entry

            if up_pct >= 0.004:
                entry = float(c[i])
                proj_tp = entry * (1 + up_pct)
                # الهدف يحترم المقاومة
                tp = min(proj_tp, res) if res > entry * 1.004 else proj_tp
                # الستوب لوس يحترم الدعم (أسفل الدعم بقليل)
                sl = sup * 0.996

                if tp > entry > sl:
                    last_sig_idx = i
                    lbl = f"تطابق {int(best_corr*100)}% (دعم/مقاومة)"
                    sigs.append((i, pd.Timestamp(t[i]), lbl, entry, sl, tp))

    return sigs

data = get_data(SYMBOLS, tf)
st.caption(f"حالة الاتصال بالسوق: تم جلب بيانات {len(data)} من أصل {len(SYMBOLS)} عملات بنجاح")

trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, pat_lbl, ent, sl, tp in scan_pattern_with_sr(df, min_corr, use_ema):
        if idx >= len(df) - 3:
            recs.append((coin, pat_lbl, ts.strftime('%Y-%m-%d %H:%M'), ent, sl, tp))

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
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, "شراء (Spot)", pat_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'النوع', 'التطابق', 'الحالة', 'الربح ($)'])
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

if st.button("🔄 تحديث الفرص الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات الشراء المستقبلية (تطابق + دعوم ومقاومات)")
for coin, pat_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | {pat_lbl} ({tm} UTC)</b><br>🔹 دخول: <code>{ent:.{dec}f}</code> | 🎯 هدف (مقاومة): <code>{tp:.{dec}f}</code> | 🛑 وقف (تحت الدعم): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد إشارة مطابقة عند الدعم في آخر شمعتين حالياً.")

st.subheader(f"📋 سجل صفقات آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
