import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Tricks HeLaL — Backtest", layout="centered")

st.markdown("""<style>
.stApp { background-color: #0d0d12; color: #fff; direction: rtl; font-family: Tahoma, sans-serif; }
div[role='radiogroup'] { display: flex; justify-content: space-around; background: #1c1c24; padding: 10px; border-radius: 12px; border: 1px solid #2d2d3a; margin-bottom: 10px; }
div[role='radiogroup'] label { color: #fff !important; font-weight: bold; }
.stCheckbox label { color: #fff !important; font-weight: bold; }
.card { border-radius: 14px; padding: 18px; text-align: center; background: #13131a; margin-bottom: 14px; border: 1.5px solid #2b6cb0; }
.c-purp { border-color: #805ad5; }
.c-grn { border-color: #38a169; }
.c-red { border-color: #e53e3e; }
.card-title { font-size: 15px; color: #cbd5e0; margin-bottom: 8px; }
.card-val { font-size: 32px; font-weight: bold; margin: 0; }
.sig-b { background: #13131a; border: 1px solid #252532; border-right: 4px solid #03ff85; padding: 14px; border-radius: 12px; margin-bottom: 12px; line-height: 1.8; }
.sig-s { background: #13131a; border: 1px solid #252532; border-right: 4px solid #fc0808; padding: 14px; border-radius: 12px; margin-bottom: 12px; line-height: 1.8; }
</style>""", unsafe_allow_html=True)

SYMBOLS = ["XLM", "ZEC", "XRP", "HBAR", "ADA", "LTC", "BTC", "ETH", "PAXG"]
PERIODS = {"24 ساعة": 24, "أسبوع": 168, "شهر": 720}
TIMEFRAMES = {"15 دقيقة": "15m", "30 دقيقة": "30m", "1 ساعة": "1h"}

sel_p = st.radio("المدة:", list(PERIODS.keys()), horizontal=True, label_visibility="collapsed")
hrs = PERIODS[sel_p]

sel_tf = st.radio("الفريم:", list(TIMEFRAMES.keys()), horizontal=True, label_visibility="collapsed")
tf = TIMEFRAMES[sel_tf]
yf_p = "60d"

atr_m = st.number_input("ATR SL:", min_value=0.1, max_value=20.0, value=4.00, step=0.1, format="%.2f")
rr_val = st.number_input("R:R:", min_value=0.5, max_value=20.0, value=3.70, step=0.1, format="%.2f")
sel_coin = st.selectbox("العملة:", ["الكل"] + SYMBOLS)

trade_mode = st.radio("نوع الصفقات:", ["شراء فقط (Spot)", "شراء و بيع (Futures)"])
use_ema = st.checkbox("فلتر الترند (EMA 100)", value=True)

@st.cache_data(ttl=180)
def load_yf(syms, interval, period):
    out = {}
    for c in syms:
        try:
            df = yf.download(f"{c}-USD", period=period, interval=interval, progress=False, auto_adjust=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.reset_index()
                t_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
                df['dt'] = pd.to_datetime(df[t_col], utc=True)
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                out[c] = df.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)
        except Exception:
            pass
    return out
def analyze(data, atr_mult, rr, hours, spot_only, filter_ema):
    sigs, trades = [], []
    depth, backstep, dev, min_bars = 30, 30, 5, 8
    cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=hours)

    for coin, df in data.items():
        if len(df) < 120:
            continue
        pc = df['Close'].shift(1)
        tr = pd.concat([df['High'] - df['Low'], (df['High'] - pc).abs(), (df['Low'] - pc).abs()], axis=1).max(axis=1)
        atrs = tr.rolling(14).mean().bfill().values
        ema100 = df['Close'].ewm(span=100, adjust=False).mean().values

        H, L, C, T = df['High'].values, df['Low'].values, df['Close'].values, df['dt']
        tick = 0.01 if C[-1] >= 100 else (0.0001 if C[-1] >= 1 else 0.00001)

        last_p, last_d, last_b, conf = None, 0, None, []
        for i in range(depth + backstep, len(df)):
            p = i - backstep
            is_ph = H[p] >= np.max(H[p - depth:p]) and H[p] > np.max(H[p + 1:p + backstep + 1])
            is_pl = L[p] <= np.min(L[p - depth:p]) and L[p] < np.min(L[p + 1:p + backstep + 1])
            if is_ph or is_pl:
                sell = is_ph and (not is_pl or H[p] >= L[p])
                px = H[p] if sell else L[p]
                if (last_p is None or abs(px - last_p) >= dev * tick) and (last_b is None or i - last_b >= min_bars):
                    if (sell and last_d != 1) or (not sell and last_d != -1):
                        last_d, last_p, last_b = (1 if sell else -1), px, i
                        side = "SELL" if sell else "BUY"
                        
                        if spot_only and side == "SELL":
                            continue
                        if filter_ema:
                            if side == "BUY" and C[i] <= ema100[i]:
                                continue
                            if side == "SELL" and C[i] >= ema100[i]:
                                continue
                        conf.append((i, side))

        busy = -1
        for idx, side in conf:
            if idx <= busy:
                continue
            ep, sd = C[idx], atrs[idx] * atr_mult
            sl, tp = (ep - sd, ep + sd * rr) if side == "BUY" else (ep + sd, ep - sd * rr)
            for j in range(idx + 1, len(df)):
                hit_sl = L[j] <= sl if side == "BUY" else H[j] >= sl
                hit_tp = H[j] >= tp if side == "BUY" else L[j] <= tp
                if hit_sl or hit_tp:
                    if T.iloc[j] >= cutoff:
                        pnl = 100.0 * (((sl - ep) if hit_sl else (tp - ep)) / ep) * (1 if side == "BUY" else -1)
                        trades.append({"coin": coin, "win": not hit_sl, "pnl": pnl})
                    busy = j
                    break

        if conf:
            idx, side = conf[-1]
            ep, sd = C[idx], atrs[idx] * atr_mult
            sl, tp = (ep - sd, ep + sd * rr) if side == "BUY" else (ep + sd, ep - sd * rr)
            dec = 2 if C[-1] > 10 else 4
            trend_up = C[-1] > ema100[-1]
            sigs.append({
                "coin": coin,
                "buy": side == "BUY",
                "p": round(C[-1], dec),
                "e": round(ep, dec),
                "tp": round(tp, dec),
                "sl": round(sl, dec),
                "ago": len(df) - 1 - idx,
                "trend": "صاعد ↗" if trend_up else "هابط ↘"
            })

    return pd.DataFrame(sigs), pd.DataFrame(trades)

with st.spinner("جاري التحليل..."):
    raw_data = load_yf(SYMBOLS, tf, yf_p)
    spot_only_flag = (trade_mode == "شراء فقط (Spot)")
    df_s, df_t = analyze(raw_data, atr_m, rr_val, hrs, spot_only_flag, use_ema)

if sel_coin != "الكل":
    df_s = df_s[df_s["coin"] == sel_coin] if not df_s.empty else df_s
    df_t = df_t[df_t["coin"] == sel_coin] if not df_t.empty else df_t

tot = len(df_t)
wins = int(df_t["win"].sum()) if tot else 0
loss = tot - wins
rate = round(wins / tot * 100, 2) if tot else 0.0
prof = round(df_t[df_t["pnl"] > 0]["pnl"].sum(), 2) if tot else 0.0
los_usd = round(abs(df_t[df_t["pnl"] < 0]["pnl"].sum()), 2) if tot else 0.0
net = round(prof - los_usd, 2)

ema_txt = " | مع فلتر EMA 100" if use_ema else ""
net_color = "#48bb78" if net >= 0 else "#f56565"
net_sign = "$" if net >= 0 else "-$"
st.markdown(f"""
<div class='card c-purp' style='margin-top: 10px;'>
    <div class='card-title'>✨ صافي الربح ({trade_mode}{ema_txt})</div>
    <div class='card-val' style='color:{net_color};'>{net_sign}{abs(net):,.2f}</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"### 📊 نتائج {sel_p} ({tf})")
st.markdown(f"<div class='card'><div class='card-title'>🤝 الصفقات</div><div class='card-val'>{tot}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-purp'><div class='card-title'>🎯 النجاح</div><div class='card-val'>{rate}%</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-grn'><div class='card-title'>📈 الصفقات الرابحة</div><div class='card-val' style='color:#48bb78;'>{wins}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-red'><div class='card-title'>📉 الصفقات الخاسرة</div><div class='card-val' style='color:#f56565;'>{loss}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-grn'><div class='card-title'>💲 إجمالي الأرباح</div><div class='card-val' style='color:#48bb78;'>+${prof:,.2f}</div></div>", unsafe_allow_html=True)
st.markdown(f"<div class='card c-red'><div class='card-title'>💲 إجمالي الخسائر</div><div class='card-val' style='color:#f56565;'>-${los_usd:,.2f}</div></div>", unsafe_allow_html=True)

st.markdown("### 🧭 أحدث الإشارات")
if not df_s.empty:
    for _, r in df_s.sort_values("ago").iterrows():
        cls = "sig-b" if r["buy"] else "sig-s"
        tag = "شراء" if r["buy"] else "بيع"
        tag_color = "#03ff85" if r["buy"] else "#fc0808"
        st.markdown(
            f"<div class='{cls}'>"
            f"<b>🪙 {r['coin']} (${r['p']}) — <span style='color:{tag_color};'>{tag}</span> (منذ {r['ago']} شمعة | ترند 100: {r['trend']})</b><br>"
            f"🔵 دخول: <b>${r['e']}</b> &nbsp;|&nbsp; 🟢 هدف: <b>${r['tp']}</b> &nbsp;|&nbsp; 🔴 وقف: <b>${r['sl']}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
else:
    st.info("لا توجد إشارات مطابقة للشروط الحالية.")
