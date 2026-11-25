import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="مناطق العرض والطلب - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=1)
min_rr = st.number_input("أقل نسبة عائد للمخاطرة مقبولة (Min R:R):", 1.0, 5.0, 1.5, 0.1)
use_ema = st.checkbox("تفعيل فلتر الاتجاه العام (EMA 200)", value=(tf == "15m"), key=f"e_{tf}")

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

def scan_supply_demand(df, m_rr, ema_on):
    o, h, l, c, t, atr, ema = df['o'].values, df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['atr'].values, df['ema'].values
    demand_zones = [] # (idx, z_low, z_high, active)
    supply_zones = [] # (idx, s_low, s_high)
    sigs = []

    for i in range(20, len(df) - 1):
        if np.isnan(atr[i]) or atr[i] == 0: continue
        body = abs(c[i] - o[i])

        # 1. اكتشاف منطقة شراء جديدة (شمعة صاعدة قوية تبتلع أو تنطلق بقوة)
        if c[i] > o[i] and body >= 1.4 * atr[i]:
            z_low = min(l[i-1], l[i])
            z_high = max(o[i-1], c[i-1]) if c[i-1] < o[i-1] else (o[i] + body * 0.35)
            if z_high > z_low:
                demand_zones.append([i, z_low, z_high, True])

        # 2. اكتشاف منطقة بائعين جديدة (شمعة هابطة قوية تنطلق بقوة)
        if c[i] < o[i] and body >= 1.4 * atr[i]:
            s_high = max(h[i-1], h[i])
            s_low = min(o[i-1], c[i-1]) if c[i-1] > o[i-1] else (o[i] - body * 0.35)
            if s_high > s_low:
                supply_zones.append((i, s_low, s_high))

        # 3. فحص عودة السعر لمنطقة شراء سابقة + شمعة تأكيد خضراء
        if i < 200: continue
        for dz in demand_zones:
            d_idx, z_low, z_high, active = dz
            if not active or i <= d_idx + 2: continue

            # إبطال المنطقة إذا تم كسرها وإغلاق السعر تحتها
            if c[i] < z_low:
                dz[3] = False
                continue

            # ملامسة منطقة الشراء في الشمعة الحالية أو السابقة + إغلاق شمعة تأكيد خضراء فوق المنطقة
            touched = (l[i] <= z_high) or (l[i-1] <= z_high and l[i-1] >= z_low)
            confirmed = (c[i] > o[i]) and (c[i] > z_high) and (c[i] > c[i-1])

            if touched and confirmed:
                if ema_on and c[i] < ema[i]:
                    dz[3] = False
                    continue

                entry = c[i]
                sl = z_low - (0.2 * atr[i]) # الستوب لوس تحت منطقة الشراء

                # البحث عن أقرب منطقة بائعين (Supply Zone) أعلى سعر الدخول كـ هدف
                valid_supplies = [sz[1] for sz in supply_zones if sz[0] < i and sz[1] > entry + (entry - sl) * m_rr]
                if not valid_supplies:
                    # في حال عدم وجود منطقة بائعين قريبة، نأخذ أعلى قمة سابقة كمنطقة مقاومة/بيع
                    recent_high = np.max(h[max(0, i-60):i])
                    if recent_high > entry + (entry - sl) * m_rr:
                        tp = recent_high
                    else:
                        dz[3] = False
                        continue
                else:
                    tp = min(valid_supplies) # أول منطقة بائعين تواجه السعر

                dz[3] = False # استهلاك المنطقة بعد الدخول
                sigs.append((i, pd.Timestamp(t[i]), "شراء (Demand)", f"منطقة [{z_low:.2f}-{z_high:.2f}]", entry, sl, tp))
                break

    return sigs

data = get_data(SYMBOLS, tf)
trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
cut = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, d, zone_lbl, ent, sl, tp in scan_supply_demand(df, min_rr, use_ema):
        if idx >= len(df) - 3:
            recs.append((coin, d, zone_lbl, ts.strftime('%Y-%m-%d %H:%M'), ent, sl, tp))

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
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, d, zone_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت', 'العملة', 'النوع', 'منطقة الشراء', 'الحالة', 'الربح ($)'])
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

if st.button("🔄 تحديث مناطق الشراء والبيع الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات الشراء من مناطق الطلب (الفرص اللحظية)")
for coin, d, z_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | ارتداد مؤكد من {z_lbl} ({tm} UTC)</b><br>🔹 دخول: <code>{ent:.{dec}f}</code> | 🎯 هدف (منطقة البائعين): <code>{tp:.{dec}f}</code> | 🛑 وقف (تحت المنطقة): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا توجد فرصة دخول مؤكدة من منطقة شراء في آخر شمعتين حالياً.")

st.subheader(f"📋 سجل صفقات الشراء آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
