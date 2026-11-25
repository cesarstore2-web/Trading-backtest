import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="RSI Trendline Breakout - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

# 1. الإعدادات الافتراضية الجديدة: فريم 4h افتراضي، R:R = 1.50، وبدون فلتر
tf = st.selectbox("الإطار الزمني:", ["5m", "15m", "30m", "1h", "4h"], index=4)
rr_ratio = st.number_input("نسبة العائد للمخاطرة (R:R):", 1.0, 6.0, 1.50, 0.1)

# 25 عملة رقمية ذات مشاريع تقنية حقيقية وقوية التذبذب (متوفرة على Kraken)
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
                # توقيت المغرب (UTC+1)
                df['t'] = pd.to_datetime(df['t'], unit='ms') + timedelta(hours=1)
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
    with ThreadPoolExecutor(max_workers=15) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

def scan_rsi_trendline_breakout(df, rr):
    h, l, c, t, rsi = df['h'].values, df['l'].values, df['c'].values, df['t'].values, df['rsi'].values
    sigs = []
    last_sig_idx = -8

    for i in range(40, len(df) - 1):
        if i - last_sig_idx < 6 or np.isnan(rsi[i]): continue

        # 1. التحقق من تشبع بيعي حديث (Oversold Zone) قبل كسر الترند
        recent_rsi = rsi[i-25:i]
        if np.min(recent_rsi) > 38: continue

        # 2. رسم خط ترند هابط على RSI وعلى السعر
        win_rsi = rsi[i-25:i]
        win_high = h[i-25:i]
        
        p1_rel = int(np.argmax(win_rsi[:12]))
        p2_rel = 12 + int(np.argmax(win_rsi[12:-1]))
        
        r1, r2 = win_rsi[p1_rel], win_rsi[p2_rel]
        h1, h2 = win_high[p1_rel], win_high[p2_rel]

        if r2 >= r1 or h2 >= h1 or (p2_rel - p1_rel) < 4:
            continue

        idx1, idx2 = (i - 25) + p1_rel, (i - 25) + p2_rel
        rsi_slope = (r2 - r1) / (idx2 - idx1)
        price_slope = (h2 - h1) / (idx2 - idx1)

        rsi_trend_now = r1 + rsi_slope * (i - idx1)
        rsi_trend_prev = r1 + rsi_slope * (i - 1 - idx1)
        price_trend_now = h1 + price_slope * (i - idx1)

        # 3. الاختراق المزدوج (RSI + السعر) صعوداً
        rsi_breakout = (rsi[i] > rsi_trend_now) and (rsi[i-1] <= rsi_trend_prev)
        price_breakout = c[i] > price_trend_now

        if rsi_breakout and price_breakout:
            entry = float(c[i])
            recent_swing_low = float(np.min(l[idx1:i+1]))
            sl = recent_swing_low * 0.997
            risk = entry - sl
            if risk <= 0: continue

            tp = entry + (risk * rr)
            last_sig_idx = i
            lbl = f"اختراق ترند RSI ({int(rsi[i])})"
            sigs.append((i, pd.Timestamp(t[i]), lbl, entry, sl, tp))

    return sigs

data = get_data(SYMBOLS, tf)
st.caption(f"حالة الاتصال: متصل بـ {len(data)} عملة قوية التذبذب | التوقيت: المغرب (UTC+1)")

trades, recs = [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
now_ma = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
cut = now_ma - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    for idx, ts, pat_lbl, ent, sl, tp in scan_rsi_trendline_breakout(df, rr_ratio):
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
            trades.append([ts.strftime('%Y-%m-%d %H:%M'), coin, "شراء (RSI Breakout)", pat_lbl, out, round(pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت (المغرب)', 'العملة', 'الاستراتيجية', 'الإشارة', 'الحالة', 'الربح ($)'])
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
c2.metric("نسبة النجاح", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث اختراقات RSI الآن", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.subheader("🎯 توصيات RSI Trendline Breakout اللحظية (Spot)")
for coin, pat_lbl, tm, ent, sl, tp in recs:
    dec = 4 if ent < 10 else 2
    st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🟢 {coin} | {pat_lbl} ({tm})</b><br>🔹 دخول (Breakout): <code>{ent:.{dec}f}</code> | 🎯 هدف (1.5R): <code>{tp:.{dec}f}</code> | 🛑 وقف (تحت القاع): <code>{sl:.{dec}f}</code></div>", unsafe_allow_html=True)
if not recs: st.info("لا يوجد كسر ترند RSI صاعد في آخر شمعتين حالياً.")

st.subheader(f"📋 سجل صفقات آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
