import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="Quant Momentum - Spot", layout="centered")
st.markdown("<style>.stApp{direction:rtl;text-align:right;}</style>", unsafe_allow_html=True)

# 1. إعدادات الواجهة
tf = st.selectbox("الإطار الزمني:", ["15m", "30m", "1h", "4h"], index=3)
trail_mult = st.number_input("معامل الوقف المتحرك (ATR Trailing Stop):", 1.5, 5.0, 2.5, 0.1)
btc_filter = st.checkbox("تفعيل فلتر قيادة البيتكوين (BTC > EMA 200)", value=True)

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
            if d and len(d) > 205:
                df = pd.DataFrame(d, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                df['t'] = pd.to_datetime(df['t'], unit='ms') + timedelta(hours=1)
                tr = pd.concat([df['h']-df['l'], (df['h']-df['c'].shift()).abs(), (df['l']-df['c'].shift()).abs()], axis=1).max(axis=1)
                df['atr'] = tr.rolling(14).mean()
                df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
                df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
                df['roc'] = ((df['c'] - df['c'].shift(18)) / df['c'].shift(18)) * 100
                return s, df
        except Exception:
            pass
        return s, None
    res = {}
    with ThreadPoolExecutor(max_workers=15) as p:
        for s, df in p.map(fetch, syms):
            if df is not None: res[s] = df
    return res

data = get_data(SYMBOLS, tf)

# 2. فحص نظام السوق (Market Regime) عبر البيتكوين
btc_bullish = True
btc_status = "غير متوفر"
if "BTC/USD" in data:
    btc_df = data["BTC/USD"]
    last_btc_c = float(btc_df['c'].iloc[-1])
    last_btc_e200 = float(btc_df['ema200'].iloc[-1])
    btc_bullish = last_btc_c > last_btc_e200
    btc_status = f"صاعد 🟢 ({last_btc_c:.0f} > {last_btc_e200:.0f})" if btc_bullish else f"هابط 🔴 ({last_btc_c:.0f} < {last_btc_e200:.0f})"

st.info(f"حالة نظام السوق (BTC EMA 200): **{btc_status}** | متصل بـ {len(data)} عملة")

# 3. تشغيل استراتيجية الزخم الكمي والوقف المتحرك
trades, recs, momentum_rank = [], [], []
hours_back = 168 if tf == "4h" else 24
period_label = "7 أيام" if tf == "4h" else "24 ساعة"
now_ma = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
cut = now_ma - timedelta(hours=hours_back)

for sym, df in data.items():
    coin = sym.replace('/USD', '')
    c, h, l, t = df['c'].values, df['h'].values, df['l'].values, df['t'].values
    e50, e200, roc, atr = df['ema50'].values, df['ema200'].values, df['roc'].values, df['atr'].values

    # ترتيب أقوى العملات زخماً الآن
    if not np.isnan(roc[-1]):
        momentum_rank.append((coin, float(roc[-1]), float(c[-1]), float(atr[-1]), float(e50[-1]), float(e200[-1])))

    in_trade = False
    entry_p, entry_t, highest_p, entry_atr = 0.0, None, 0.0, 0.0

    for i in range(200, len(df)):
        if np.isnan(atr[i]) or np.isnan(roc[i]): continue

        # التحقق من فلتر البيتكوين في نفس اللحظة الزمنية
        market_ok = True
        if btc_filter and "BTC/USD" in data and i < len(data["BTC/USD"]):
            market_ok = data["BTC/USD"]['c'].iloc[i] > data["BTC/USD"]['ema200'].iloc[i]

        if not in_trade:
            # شرط الدخول الكمي: السعر فوق EMA50 و EMA200 + زخم إيجابي قوي (> 2.5%) + نظام السوق صاعد
            if market_ok and c[i] > e50[i] and c[i] > e200[i] and roc[i] > 2.5 and roc[i-1] <= 2.5:
                in_trade = True
                entry_p = float(c[i])
                entry_t = pd.Timestamp(t[i])
                highest_p = float(h[i])
                entry_atr = float(atr[i])

                if i >= len(df) - 3:
                    sl_init = entry_p - (trail_mult * entry_atr)
                    tp_est = entry_p + (trail_mult * 1.5 * entry_atr)
                    recs.append((coin, f"زخم +{roc[i]:.1f}%", entry_t.strftime('%Y-%m-%d %H:%M'), entry_p, sl_init, tp_est))
        else:
            if h[i] > highest_p:
                highest_p = float(h[i])
            trailing_sl = highest_p - (trail_mult * float(atr[i]))

            # الخروج بالوقف المتحرك لحجز الأرباح أو انعكاس نظام السوق
            if l[i] <= trailing_sl or (btc_filter and not market_ok):
                exit_p = max(trailing_sl, float(l[i])) if l[i] <= trailing_sl else float(c[i])
                pnl = POS_USD * ((exit_p - entry_p) / entry_p)
                out = "ناجحة" if pnl > 0 else "خاسرة"
                if entry_t >= cut:
                    trades.append([entry_t.strftime('%Y-%m-%d %H:%M'), coin, "Quant Momentum", f"خرج عند {exit_p:.2f}", out, round(pnl, 2)])
                in_trade = False

    # إذا بقيت الصفقة مفتوحة حتى اللحظة الحالية
    if in_trade and entry_t >= cut:
        curr_pnl = POS_USD * ((float(c[-1]) - entry_p) / entry_p)
        trades.append([entry_t.strftime('%Y-%m-%d %H:%M'), coin, "Quant Momentum", "ملاحقة بالوقف المتحرك", "مفتوحة ⏳", round(curr_pnl, 2)])

df_t = pd.DataFrame(trades, columns=['الوقت (المغرب)', 'العملة', 'الاستراتيجية', 'التفاصيل', 'الحالة', 'الربح ($)'])
if not df_t.empty:
    df_t = df_t.sort_values('الوقت (المغرب)', ascending=False).reset_index(drop=True)
    cl = df_t[df_t['الحالة'] != 'مفتوحة ⏳']
    w, l, op = len(cl[cl['الحالة']=='ناجحة']), len(cl[cl['الحالة']=='خاسرة']), len(df_t[df_t['الحالة']=='مفتوحة ⏳'])
    wr = (w / len(cl) * 100) if len(cl) > 0 else 0.0
    net = cl['الربح ($)'].sum()
else:
    w, l, op, wr, net = 0, 0, 0, 0.0, 0.0

# 4. عرض الإحصائيات والنتائج
st.markdown("---")
c1, c2 = st.columns(2)
c1.metric(f"الربح الصافي سبوت ({period_label} | {tf})", f"{net:.2f} $")
c2.metric("نسبة النجاح (Quant)", f"{wr:.1f}%", f"مغلقة: {w+l} | مفتوحة: {op}")

cw, cl_c, co = st.columns(3)
cw.markdown(f"<div style='background:#00c85326;border:1px solid #00c853;padding:10px;border-radius:8px;text-align:center;color:#00e676;'><b>✅ {w} ناجحة</b></div>", unsafe_allow_html=True)
cl_c.markdown(f"<div style='background:#ff4b4b26;border:1px solid #ff4b4b;padding:10px;border-radius:8px;text-align:center;color:#ff5252;'><b>❌ {l} خاسرة</b></div>", unsafe_allow_html=True)
co.markdown(f"<div style='background:#ffc10726;border:1px solid #ffc107;padding:10px;border-radius:8px;text-align:center;color:#ffd54f;'><b>⏳ {op} مفتوحة</b></div>", unsafe_allow_html=True)

if st.button("🔄 تحديث المسح الكمي الآن", use_container_width=True):
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

# عرض أقوى 3 عملات زخماً في السوق حالياً
st.subheader("🏆 أقوى 3 عملات زخماً في السوق الآن (Momentum Leaders)")
momentum_rank.sort(key=lambda x: x[1], reverse=True)
top3 = [x for x in momentum_rank if x[2] > x[4] and x[2] > x[5]][:3]
if top3 and (not btc_filter or btc_bullish):
    for coin, r_val, pr, a_val, _, _ in top3:
        dec = 4 if pr < 10 else 2
        sl_v = pr - (trail_mult * a_val)
        st.markdown(f"<div style='background:#00c85326;border-right:5px solid #00e676;padding:12px;border-radius:8px;margin-bottom:8px;'><b style='color:#00e676;font-size:1.1rem;'>🚀 {coin} | قوة الزخم: +{r_val:.2f}%</b><br>🔹 السعر الحالي: <code>{pr:.{dec}f}</code> | 🛑 الوقف المتحرك المقترح: <code>{sl_v:.{dec}f}</code></div>", unsafe_allow_html=True)
else:
    st.info("نظام السوق متوقف حالياً (البيتكوين تحت EMA 200 أو لا توجد عملات بزخم صاعد قوي).")

st.subheader(f"📋 سجل صفقات آخر {period_label} (100$ للصفقة)")
if not df_t.empty: st.dataframe(df_t, use_container_width=True)
else: st.info(f"لا توجد صفقات مسجلة في آخر {period_label}.")
