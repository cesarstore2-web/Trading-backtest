import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="W.D. Gann Strategy - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=4)
gann_deg = st.selectbox("زاوية هدف مربع جان (Square of 9):", ["90° (ربع دورة - سريع)", "135° (متوسط)", "180° (نصف دورة - بعيد)"], index=0)

deg_map = {"90° (ربع دورة - سريع)": 0.50, "135° (متوسط)": 0.75, "180° (نصف دورة - بعيد)": 1.00}
deg_step = deg_map[gann_deg]

SYMBOLS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD",
    "DOT/USD", "LINK/USD", "ATOM/USD", "NEAR/USD", "ALGO/USD",
    "SUI/USD", "APT/USD", "SEI/USD", "INJ/USD", "TIA/USD",
    "RENDER/USD", "FET/USD", "ARB/USD", "OP/USD", "POL/USD",
    "FIL/USD", "ICP/USD", "STX/USD", "RUNE/USD", "GRT/USD"
]
POS_USD = 100.0

@st.cache_data(ttl=60, show_spinner=False)
def get_data(syms, timeframe):
    ex = ccxt.kraken({'enableRateLimit': False})
    def fetch(s):
        try:
            d = ex.fetch_ohlcv(s, timeframe=timeframe, limit=300)
            if d and len(d) > 60:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms') + timedelta(hours=1)
                tr = pd.concat([df['h']-df['l'], (df['h']-df['c'].shift()).abs(), (df['l']-df['c'].shift()).abs()], axis=1).max(axis=1)
                df['atr'] = tr.rolling(14).mean()
                df['vol_ma'] = df['v'].rolling(10).mean()
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=15) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

def scan_gann_strategy(df, step_val):
    o, h, l, c, v, t, atr, vma = df['o'].values, df['h'].values, df['l'].values, df['c'].values, df['v'].values, df['t'].values, df['atr'].values, df['vol_ma'].values
    sigs = []
    last_low_price = -1.0

    for i in range(40, len(df) - 1):
        if np.isnan(atr[i]) or atr[i] == 0: continue

        # 1. تحديد قاع الارتكاز الهندسي (Gann Pivot Low) في آخر 30 شمعة
        win_low = l[i-30:i]
        rel_idx = int(np.argmin(win_low))
        p_idx = (i - 30) + rel_idx
        p_low = float(l[p_idx])

        bars_elapsed = i - p_idx
        if not (3 <= bars_elapsed <= 18): continue
        if abs(p_low - last_low_price) / p_low < 0.002: continue

        # 2. حساب مستويات مربع التسعة لجان (Square of 9) من قاع الارتكاز
        sqrt_low = np.sqrt(p_low)
        gann_45_confirm = (sqrt_low + 0.25) ** 2   # زاوية 45 درجة للتأكيد
        gann_target = (sqrt_low + step_val) ** 2    # زاوية الهدف المختارة (90 / 135 / 180)

        # 3. حساب زاوية جان الزمنية السعرية (Gann 1x1 Angle = 1 وحدة ATR لكل شمعة زمنية)
        gann_1x1_line = p_low + (bars_elapsed * 0.45 * float(atr[p_idx]))
        gann_1x1_prev = p_low + ((bars_elapsed - 1) * 0.45 * float(atr[p_idx]))

        # 4. شروط الدخول الدقيقة: اختراق زاوية 1x1 + تجاوز مستوى 45 درجة + شمعة خضراء بسيولة
        broke_1x1 = (c[i] > gann_1x1_line) and (c[i-1] <= gann_1x1_prev or c[i] >= gann_45_confirm)
        bull_candle = (c[i] > o[i]) and (c[i] > c[i-1])
        vol_ok = True if np.isnan(vma[i]) else (v[i] >= vma[i] * 0.8)

        if broke_1x1 and bull_candle and vol_ok:
            entry = float(c[i])
            sl = p_low - (0.3 * float(atr[i])) # الستوب أسفل قاع دورة جان
            tp = float(gann_target)

            # التأكد من أن الهدف أعلى من الدخول وأن نسبة العائد للمخاطرة منطقية
            if tp > entry * 1.005 and (tp - entry) >= (entry - sl) * 1.1:
                last_low_price = p_low
                lbl = f"جان Sq9 ({gann_deg[:4]}) + 1x1"
                sigs.append((i, pd.Timestamp(t[i]), lbl, entry, sl, tp))

    return sigs

data = get_data(SYMBOLS, tf)
st.caption(f"حالة الاتصال: متصل بـ {len(data)} عملة رقمية نقية | التوقيت: المغرب (UTC+1)")

trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
now_ma = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
cut = now_ma - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, pat_lbl, ent, sl, tp in scan_gann_strategy(df, deg_step):
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
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, "شراء (Gann Spot)", pat_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت (المغرب)', 'العملة', 'الاستراتيجية', 'زاوية جان', 'الحالة', 'الربح ($)'])
if not df_t.empty:
    df_t = df_t.sort_values('الوقت (المغرب)', ascending=False).reset_index(drop=True)
    cl = df_t[df_t['الحالة'] != 'مفتوحة ⏳']
    w, l, op = len(cl[cl['الحالة']=='ناجحة']), len(cl[cl['الحالة']=='خاسرة']), len(df_t[df_t['الحالة']=='مفتوحة ⏳'])
    wr = (w / len(cl) * 100) if len(cl) > 0 else 0.0
    net = cl['الربح ($)'].sum()
else:
    w, l, op, wr, net = 0, 0, 0, 0.0, 0.0

st.markdown("---")
c1, c2 = st.columns(2)
c1.metric(f"الربح الصافي سبوت ({period_label} | {tf})", f"{net:.2f} $")
c2.metric("نسبة النجاح (Gann)", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث مستويات جان الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# جدول الربح الصافي لكل يوم على حدة
st.subheader(f"📅 الربح الصافي لكل يوم على حدة (آخر {period_label})")
if not df_t.empty:
    df_closed = df_t[df_t['الحالة'] != 'مفتوحة ⏳'].copy()
    if not df_closed.empty:
        df_closed['اليوم'] = df_closed['الوقت (المغرب)'].str[:10]
        daily_pnl = df_closed.groupby('اليوم', as_index=False).agg(
            عدد_الصفقات=('الربح ($)', 'count'),
            الناجحة=('الحالة', lambda x: (x == 'ناجحة').sum()),
            الخاسرة=('الحالة', lambda x: (x == 'خاسرة').sum()),
            الربح_الصافي=('الربح ($)', 'sum')
        ).sort_values('اليوم', ascending=False)
        daily_pnl['الربح_الصافي'] = daily_pnl['الربح_الصافي'].round(2)
        st.dataframe(daily_pnl, use_container_width=True, hide_index=True)
    else:
        st.info("لا توجد صفقات مغلقة لحساب التوزيع اليومي بعد.")
else:
    st.info("لا توجد صفقات مسجلة لحساب التوزيع اليومي.")

st.subheader("🎯 توصيات مربع وزوايا جان اللحظية (Spot)")
for coin, pat_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | {pat_lbl} ({tm})</b><br>🔹 دخول (1x1): <code>{ent:.{dec}f}</code> | 🎯 هدف ({gann_deg[:4]}): <code>{tp:.{dec}f}</code> | 🛑 وقف (قاع جان): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد إشارة اختراق لزاوية جان في آخر شمعتين حالياً.")

st.subheader(f"📋 سجل صفقات جان آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
