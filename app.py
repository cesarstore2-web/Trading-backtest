import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

st.set_page_config(page_title="Tricks HeLaL — Backtest", layout="centered")
st.markdown("""<style>
.stApp { background-color: #0d0d12; color: #fff; direction: rtl; font-family: Tahoma; }
div[role='radiogroup'] { display: flex; justify-content: space-around; background: #1c1c24; padding: 6px; border-radius: 12px; }
div[role='radiogroup'] label { color: #fff !important; }
.card { border-radius: 14px; padding: 15px; text-align: center; background: #16161e; margin-bottom: 12px; border: 1.5px solid #2b6cb0; }
.c-purp { border-color: #805ad5; } .c-grn { border-color: #38a169; } .c-red { border-color: #e53e3e; }
.sig-b { background: #1a1a24; border-right: 4px solid #03ff85; padding: 12px; border-radius: 10px; margin-bottom: 10px; }
.sig-s { background: #1a1a24; border-right: 4px solid #fc0808; padding: 12px; border-radius: 10px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)

SYMBOLS = ["XLM", "ZEC", "XRP", "HBAR", "ADA", "LTC", "BTC", "ETH", "PAXG"]
PERIODS = {"24 ساعة": ("5m", "5d", 24), "أسبوع": ("15m", "1mo", 168), "شهر": ("1h", "3mo", 720)}
sel_p = st.radio("المدة:", list(PERIODS.keys()), horizontal=True, label_visibility="collapsed")
tf, yf_p, hrs = PERIODS[sel_p]

c1, c2, c3 = st.columns(3)
atr_m = c1.number_input("ATR SL:", 0.1, 10.0, 1.5, 0.1)
rr_val = c2.number_input("R : R :", 0.5, 15.0, 2.0, 0.1)
sel_coin = c3.selectbox("العملة:", ["الكل"] + SYMBOLS)

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

def analyze(data, atr_mult, rr, hours):
    sigs, trades = [], []
    depth, backstep, dev, min_bars = 30, 30, 5, 8
    cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=hours)
    for coin, df in data.items():
        if len(df) < depth + backstep + 15:
            continue
        pc = df['Close'].shift(1)
        tr = pd.concat([df['High'] - df['Low'], (df['High'] - pc).abs(), (df['Low'] - pc).abs()], axis=1).max(axis=1)
        atrs = tr.rolling(14).mean().bfill().values
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
                        conf.append((i, "SELL" if sell else "BUY"))
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
                        pnl = 1000.0 * (((sl - ep) if hit_sl else (tp - ep)) / ep) * (1 if side == "BUY" else -1)
                        trades.append({"coin": coin, "win": not hit_sl, "pnl": pnl})
                    busy = j
                    break
        if conf:
            idx, side = conf[-1]
            ep, sd = C[idx], atrs[idx] * atr_mult
            sl, tp = (ep - sd, ep + sd * rr) if side == "BUY" else (ep + sd, ep - sd * rr)
            dec = 2 if C[-1] > 10 else 4
            sigs.append({
                "coin": coin,
                "buy": side == "BUY",
                "p": round(C[-1], dec),
                "e": round(ep, dec),
                "tp": round(tp, dec),
                "sl": round(sl, dec),
                "ago": len(df) - 1 - idx
            })
    return pd.DataFrame(sigs), pd.DataFrame(trades)

with st.spinner("جاري التحليل..."):
    raw_data = load_yf(SYMBOLS, tf, yf_p)
    df_s, df_t = analyze(raw_data, atr_m, rr_val, hrs)

if sel_coin != "الكل":
    df_s = df_s[df_s["coin"] == sel_coin] if not df_s.empty else df_s
    df_t = df_t[df_t["coin"] == sel_coin] if not df_t.empty else df_t

tot = len(df_t)
wins = int(df_t["win"].sum()) if tot else 0
loss = tot - wins
rate = round(wins / tot * 100, 1) if tot else 0.0
prof = round(df_t[df_t["pnl"] > 0]["pnl"].sum(), 2) if tot else 0.0
los_usd = round(abs(df_t[df_t["pnl"] < 0]["pnl"].sum()), 2) if tot else 0.0
net = round(prof - los_usd, 2)

st.markdown(f"### 📊 نتائج {sel_p} ({tf})")
a1, a2 = st.columns(2)
a1.markdown(f"<div class='card'><div>🤝 الصفقات</div><h2>{tot}</h2></div>", unsafe_allow_html=True)
a2.markdown(f"<div class='card c-purp'><div>🎯 النجاح</div><h2>{rate}%</h2></div>", unsafe_allow_html=True)

a3, a4 = st.columns(2)
a3.markdown(f"<div class='card c-grn'><div>📈 رابحة</div><h2>{wins}</h2></div>", unsafe_allow_html=True)
a4.markdown(f"<div class='card c-red'><div>📉 خاسرة</div><h2>{loss}</h2></div>", unsafe_allow_html=True)

a5, a6 = st.columns(2)
a5.markdown(f"<div class='card c-grn'><div>💲 الأرباح</div><h2>+${prof:,.2f}</h2></div>", unsafe_allow_html=True)
a6.markdown(f"<div class='card c-red'><div>💲 الخسائر</div><h2>-${los_usd:,.2f}</h2></div>", unsafe_allow_html=True)

st.markdown(f"<div class='card c-purp'><div>✨ صافي الربح</div><h2 style='color:{'#48bb78' if net >= 0 else '#f56565'}'>${net:,.2f}</h2></div>", unsafe_allow_html=True)

st.markdown("### 🤖 أحدث الإشارات")
for _, r in (df_s.sort_values("ago") if not df_s.empty else df_s).iterrows():
    cls = "sig-b" if r["buy"] else "sig-s"
    tag = "شراء" if r["buy"] else "بيع"
    st.markdown(f"<div class='{cls}'><b>🪙 {r['coin']} (${r['p']}) — {tag} (منذ {r['ago']} شمعة)</b><br>🔵 دخول: ${r['e']} | 🟢 هدف: ${r['tp']} | 🔴 وقف: ${r['sl']}</div>", unsafe_allow_html=True)
