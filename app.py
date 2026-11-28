# app.py  —  LGFP Scalper (Streamlit) — Spot / شراء فقط / بيانات yfinance / توقيت UTC
import calendar
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="LGFP سكالبينج حلال", page_icon="📈", layout="centered")

# ───────────────────────── الإعدادات الثابتة ─────────────────────────
# رموز Yahoo Finance — إذا فشل رمز سيظهر في تحذير بالتطبيق ويمكنك تعديله هنا
COINS = {
    "BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL", "ADA-USD": "ADA",
    "AVAX-USD": "AVAX", "DOT-USD": "DOT", "LINK-USD": "LINK", "ATOM-USD": "ATOM",
    "NEAR-USD": "NEAR", "ALGO-USD": "ALGO", "XLM-USD": "XLM", "VET-USD": "VET",
    "HBAR-USD": "HBAR", "FIL-USD": "FIL", "ICP-USD": "ICP", "APT21794-USD": "APT",
    "ARB11841-USD": "ARB", "OP-USD": "OP", "RENDER-USD": "RENDER", "GRT6719-USD": "GRT",
    "TIA22861-USD": "TIA", "SUI20947-USD": "SUI",
}
ALL_SYMBOLS = tuple(COINS.keys())
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
ZONES_AR = ["تلقائي", "الثلث الأول", "الثلث الأوسط", "الثلث الأخير"]
ZONE_NAME = {0: "الثلث الأول", 1: "الثلث الأوسط", 2: "الثلث الأخير"}
TF_OPTIONS = ["5m", "15m", "30m", "1h"]

DEFAULTS = dict(
    tf="15m",
    coins=list(ALL_SYMBOLS),
    min_vol=0.20,        # أدنى تذبذب ATR% (لتصفية العملات الهادئة)
    capital=100.0,       # $ لكل صفقة
    fee=0.10,            # % لكل جهة
    rev_atr=4.0,         # عتبة انعكاس الموجة (ATR ×)
    min_ret=38.2,        # أدنى تصحيح %
    min_bars=24,         # أدنى طول للموجة الأب
    max_bars=500,        # أقصى طول للموجة الأب
    zone="تلقائي",
    min_corr=0.40,       # أدنى ارتباط شكلي
    min_frac=10.0,       # أدنى حركة للفراكتل % من مدى الموجة الأب
    res=16,              # دقة الشكل (نقاط)
    time_mult=1.618,
    price_mult=1.618,
    hold=24,             # أقصى مدة للصفقة (شموع)
    tp_frac=100,         # الهدف % من المسافة إلى المسار المسقَط
    min_gain=0.60,       # أدنى ربح متوقع % (يجب أن يغطي الرسوم)
    sl_atr=1.5,          # الوقف = ATR ×
    min_rr=1.0,          # أدنى عائد/مخاطرة
    step=1,              # فحص الإشارة كل N شمعة
)

# ───────────────────────── حفظ الإعدادات حتى عند إخفائها ─────────────────────────
SAVED = st.session_state.setdefault("_saved", {})
for _k, _v in DEFAULTS.items():
    if ("w_" + _k) not in st.session_state:
        st.session_state["w_" + _k] = SAVED.get(_k, _v)
cfg = {k: st.session_state["w_" + k] for k in DEFAULTS}

# ───────────────────────── تنسيق (RTL + جوال) ─────────────────────────
st.markdown("""
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {direction: rtl; text-align: right;}
.block-container {padding-top: 1.2rem; max-width: 760px;}
.big-box {border-radius: 18px; padding: 18px 10px; text-align: center; margin-bottom: 10px;}
.big-title {font-size: 15px; opacity: .85; margin-bottom: 4px;}
.big-num {font-size: 46px; font-weight: 800; line-height: 1.1; direction: ltr;}
.big-sub {font-size: 13px; opacity: .85; margin-top: 6px;}
.wk-grid {display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;}
.wk-card {flex: 1 1 30%; min-width: 30%; border-radius: 14px; padding: 10px 6px; text-align: center;}
.wk-t {font-size: 12px; opacity: .85;}
.wk-n {font-size: 20px; font-weight: 700; direction: ltr;}
</style>
""", unsafe_allow_html=True)

GREEN, RED, GREY = "#16a34a", "#dc2626", "#6b7280"


def tone(v, active=True):
    if not active:
        return GREY
    return GREEN if v > 0 else RED if v < 0 else GREY


def money(v):
    return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"


def fmt_price(x):
    return f"{x:.6g}"


# ───────────────────────── جلب البيانات (yfinance، UTC) ─────────────────────────
def _clean(df):
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    need = ["Open", "High", "Low", "Close"]
    if any(c not in df.columns for c in need):
        return None
    df = df[need].dropna()
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx.tz_localize(None)          # UTC بدون منطقة زمنية
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all(symbols, interval):
    data, failed = {}, []
    try:
        raw = yf.download(list(symbols), period="59d", interval=interval,
                          group_by="ticker", auto_adjust=False, progress=False, threads=True)
    except Exception:
        raw = None
    for s in symbols:
        df = None
        try:
            if raw is not None and isinstance(raw.columns, pd.MultiIndex) \
                    and s in raw.columns.get_level_values(0):
                df = _clean(raw[s].copy())
        except Exception:
            df = None
        if df is None or len(df) < 150:
            try:
                df = _clean(yf.Ticker(s).history(period="59d", interval=interval, auto_adjust=False))
            except Exception:
                df = None
        if df is None or len(df) < 150:
            failed.append(s)
        else:
            data[s] = df
    return data, failed


# ───────────────────────── محرك LGFP ─────────────────────────
def atr_arr(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    a = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().values
    a[:n - 1] = np.nan
    return a


def zigzag(h, l, atr, rev, min_ret):
    """الموجة الأب الحية (نفس منطق Pine)."""
    n = len(h)
    dirA = np.zeros(n, dtype=int)
    oI = np.zeros(n, dtype=int)
    eI = np.zeros(n, dtype=int)
    oP = np.zeros(n)
    eP = np.zeros(n)
    d, oi, op, ei, ep = 1, 0, l[0], 0, h[0]
    dirA[0], oI[0], oP[0], eI[0], eP[0] = d, oi, op, ei, ep
    for i in range(1, n):
        a = atr[i]
        if d == 1:
            wave = ep - op
            retr = ep - l[i]
            if h[i] > ep:
                ep, ei = h[i], i
            elif (not np.isnan(a)) and wave > 0 and retr >= rev * a and retr >= min_ret / 100.0 * wave:
                oi, op, d, ep, ei = ei, ep, -1, l[i], i
            elif l[i] < op:
                op, oi, ep, ei = l[i], i, h[i], i
        else:
            wave = op - ep
            retr = h[i] - ep
            if l[i] < ep:
                ep, ei = l[i], i
            elif (not np.isnan(a)) and wave > 0 and retr >= rev * a and retr >= min_ret / 100.0 * wave:
                oi, op, d, ep, ei = ei, ep, 1, h[i], i
            elif h[i] > op:
                op, oi, ep, ei = h[i], i, l[i], i
        dirA[i], oI[i], oP[i], eI[i], eP[i] = d, oi, op, ei, ep
    return dirA, oI, oP, eI, eP


def _detr(a, j):
    return a - (a[:, :1] + (a[:, -1:] - a[:, :1]) * j)


def find_micro(i, c, h, l, idx, zz, p):
    """البحث عن الفراكتل المصغّر في أثلاث الموجة الأب الصاعدة، وإسقاطه."""
    dirA, oI, oP, eI, eP = zz
    if dirA[i] != 1:
        return None
    oi, op, ei, ep = int(oI[i]), oP[i], int(eI[i]), eP[i]
    P = ei - oi
    R = ep - op
    if P < p["min_bars"] or P > p["max_bars"] or R <= 0:
        return None

    M = int(p["res"])
    j = np.arange(M) / (M - 1.0)
    pv = _detr(np.interp(oi + P * j, idx, c)[None, :], j)[0]
    pvc = pv - pv.mean()
    pvn = np.sqrt((pvc ** 2).sum())
    if pvn == 0:
        return None

    pLen = P / 3.0
    zScore = [-2.0, -2.0, -2.0]
    zS = [0, 0, 0]
    zW = [0, 0, 0]
    for z in range(3):
        zr = int(np.floor(oi + pLen * z + 0.5))
        for f in (0.5, 0.65, 0.8, 1.0):
            w = int(np.floor(pLen * f + 0.5))
            if w < 6 or w > pLen + 1.0:
                continue
            step = max(1, int(w / 6))
            nst = max(0, int(np.floor((pLen - w + 1.0) / step)))
            s = np.minimum(zr + np.arange(nst + 1) * step, ei - w)
            s = s[s >= oi]
            if s.size == 0:
                continue
            net = c[s + w] - c[s]
            s = s[(net > 0) & (net >= p["min_frac"] / 100.0 * R)]
            if s.size == 0:
                continue
            pos = s[:, None] + w * j[None, :]
            vals = np.interp(pos.ravel(), idx, c).reshape(pos.shape)
            vals = _detr(vals, j)
            vc = vals - vals.mean(axis=1, keepdims=True)
            den = np.sqrt((vc ** 2).sum(axis=1)) * pvn
            sc = np.where(den > 0, (vc @ pvc) / np.where(den > 0, den, 1.0), 0.0)
            k = int(np.argmax(sc))
            if sc[k] > zScore[z]:
                zScore[z], zS[z], zW[z] = float(sc[k]), int(s[k]), w

    if p["zone"] is None:
        sel = int(np.argmax(zScore))
    else:
        sel = int(p["zone"])
    if zScore[sel] < p["min_corr"]:
        return None

    # التقاط بداية/نهاية الفراكتل عند أقرب قاع/قمة
    s0 = zS[sel]
    e0 = s0 + zW[sel]
    lo1, hi1 = max(oi, s0 - 2), min(ei, s0 + 2)
    cand = lo1 + int(np.argmin(l[lo1:hi1 + 1]))
    sB = s0 if l[s0] <= l[cand] else cand
    lo2, hi2 = max(oi, e0 - 2), min(ei, e0 + 2)
    cand = lo2 + int(np.argmax(h[lo2:hi2 + 1]))
    eB = e0 if h[e0] >= h[cand] else cand
    sPx, ePxM = l[sB], h[eB]
    if eB - sB < 4 or ePxM - sPx <= 0:
        return None

    # إعادة القياس ووضعه عند أصل الموجة الأب
    nM = eB - sB
    tScale = P * p["time_mult"] / nM
    pScale = R * p["price_mult"] / (ePxM - sPx)
    ks = np.arange(nM + 1)
    pr = c[sB + ks].astype(float)
    pr[0], pr[-1] = sPx, ePxM
    xs = oi + np.floor(ks * tScale + 0.5)
    ys = op + (pr - sPx) * pScale
    endX, endY = xs[-1], ys[-1]
    if i >= endX:
        return None
    fp = float(np.interp(min(i + p["hold"], endX), xs, ys))
    return dict(corr=zScore[sel], zone=sel, fp=fp, endY=float(endY), op=float(op))


def make_signal(i, c, h, l, atr, idx, zz, p):
    m = find_micro(i, c, h, l, idx, zz, p)
    if m is None or np.isnan(atr[i]):
        return None
    cl = c[i]
    tp = cl + p["tp_frac"] / 100.0 * (m["fp"] - cl)
    gain = (tp / cl - 1.0) * 100.0
    if gain < p["min_gain"]:
        return None
    sl = max(m["op"], cl - p["sl_atr"] * atr[i])
    if sl >= cl:
        return None
    rr = (tp - cl) / (cl - sl)
    if rr < p["min_rr"]:
        return None
    return dict(tp=float(tp), sl=float(sl), gain=float(gain), rr=float(rr),
                corr=float(m["corr"]), zone=ZONE_NAME[m["zone"]])


# ───────────────────────── الباكتست لعملة واحدة (مخزَّن مؤقتاً) ─────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def run_symbol(sym, interval, params_t, month_iso):
    p = dict(params_t)
    data, _ = fetch_all(ALL_SYMBOLS, interval)
    df = data.get(sym)
    if df is None:
        return [], None, None
    df = df.iloc[:-1]                       # نتجاهل الشمعة التي لم تُغلق بعد
    if len(df) < 120:
        return [], None, None
    times = df.index
    o, h, l, c = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    idx = np.arange(n, dtype=float)
    atr = atr_arr(h, l, c)
    zz = zigzag(h, l, atr, p["rev_atr"], p["min_ret"])

    start = max(int(times.searchsorted(pd.Timestamp(month_iso))), 60)
    cap, fee, hold, step = p["capital"], p["fee"] / 100.0, int(p["hold"]), max(1, int(p["step"]))

    trades, rec = [], None
    i = start
    while i < n:
        if (i - start) % step != 0:
            i += 1
            continue
        sig = make_signal(i, c, h, l, atr, idx, zz, p)
        if sig is None:
            i += 1
            continue
        if i == n - 1:                      # توصية حالية (الدخول عند افتتاح الشمعة القادمة)
            rec = dict(sym=sym, time=times[i], price=float(c[i]), **sig)
            break
        j = i + 1
        entry, tp, sl = float(o[j]), sig["tp"], sig["sl"]
        if entry >= tp or entry <= sl:
            i += 1
            continue
        k, status, ex, reason = j, "open", None, ""
        while k < n:
            if l[k] <= sl:
                ex, reason, status = min(sl, float(o[k])), "وقف", "closed"
                break
            if h[k] >= tp:
                ex, reason, status = tp, "هدف", "closed"
                break
            if k - j >= hold:
                ex, reason, status = float(c[k]), "مدة", "closed"
                break
            k += 1
        if status == "open":
            k = n - 1
            ex, reason = float(c[n - 1]), "مفتوحة"
        qty = cap / entry
        net = qty * (ex - entry) - fee * (cap + qty * ex)
        trades.append(dict(sym=sym, entry_t=times[j], exit_t=times[k], entry=entry, tp=tp, sl=sl,
                           exit=ex, reason=reason, net=float(net), status=status,
                           corr=sig["corr"], zone=sig["zone"]))
        if status == "open":
            break
        i = k + 1
    vol = float(np.nanmean(atr[-200:] / c[-200:] * 100.0))
    return trades, rec, vol


# ───────────────────────── الواجهة ─────────────────────────
now = datetime.now(timezone.utc)
month_start = pd.Timestamp(year=now.year, month=now.month, day=1)
dim = calendar.monthrange(now.year, now.month)[1]
month_label = f"{AR_MONTHS[now.month - 1]} {now.year}"

st.markdown("<h3 style='text-align:center;margin:0 0 8px'>📈 LGFP — سكالبينج العملات الحلال</h3>",
            unsafe_allow_html=True)

# --- حساب الباكتست حسب الإعدادات الحالية ---
params = dict(
    capital=float(cfg["capital"]), fee=float(cfg["fee"]),
    rev_atr=float(cfg["rev_atr"]), min_ret=float(cfg["min_ret"]),
    min_bars=int(cfg["min_bars"]), max_bars=int(cfg["max_bars"]),
    zone={"تلقائي": None, "الثلث الأول": 0, "الثلث الأوسط": 1, "الثلث الأخير": 2}[cfg["zone"]],
    min_corr=float(cfg["min_corr"]), min_frac=float(cfg["min_frac"]), res=int(cfg["res"]),
    time_mult=float(cfg["time_mult"]), price_mult=float(cfg["price_mult"]),
    hold=int(cfg["hold"]), tp_frac=float(cfg["tp_frac"]), min_gain=float(cfg["min_gain"]),
    sl_atr=float(cfg["sl_atr"]), min_rr=float(cfg["min_rr"]), step=int(cfg["step"]),
)
params_t = tuple(sorted((k, -1 if v is None else v) for k, v in params.items()))
params_t = tuple((k, (None if (k == "zone" and v == -1) else v)) for k, v in params_t)

with st.spinner("جاري جلب بيانات yfinance وتشغيل الاستراتيجية…"):
    data, failed = fetch_all(ALL_SYMBOLS, cfg["tf"])

all_trades, recs, vols, skipped = [], [], {}, []
sel_coins = [s for s in cfg["coins"] if s in data]
if sel_coins:
    pb = st.progress(0.0, text="جاري التحليل…")
    for n_i, s in enumerate(sel_coins):
        tr, rc, vl = run_symbol(s, cfg["tf"], params_t, month_start.isoformat())
        if vl is not None:
            vols[s] = vl
        if vl is not None and vl < cfg["min_vol"]:
            skipped.append(COINS[s])
        else:
            all_trades += tr
            if rc:
                recs.append(rc)
        pb.progress((n_i + 1) / len(sel_coins), text=f"تحليل {COINS[s]}…")
    pb.empty()

tdf = pd.DataFrame(all_trades)
if tdf.empty:
    tdf = pd.DataFrame(columns=["sym", "entry_t", "exit_t", "entry", "tp", "sl", "exit",
                                "reason", "net", "status", "corr", "zone"])
closed = tdf[tdf["status"] == "closed"]
opened = tdf[tdf["status"] == "open"]
month_net = float(closed["net"].sum()) if len(closed) else 0.0
floating = float(opened["net"].sum()) if len(opened) else 0.0
n_tr = len(closed)
wins = int((closed["net"] > 0).sum()) if n_tr else 0
winrate = (wins / n_tr * 100.0) if n_tr else 0.0

# --- 1) صافي ربح الشهر (أعلى الصفحة) ---
col = tone(month_net)
st.markdown(f"""
<div class="big-box" style="background:{col}22;border:2px solid {col}">
  <div class="big-title">صافي ربح شهر {month_label} (UTC)</div>
  <div class="big-num" style="color:{col}">{money(month_net)}</div>
  <div class="big-sub">{n_tr} صفقة مغلقة · نسبة النجاح {winrate:.0f}% · عائم على المفتوحة: {money(floating)}</div>
</div>
""", unsafe_allow_html=True)

# --- 2) صافي ربح كل أسبوع من الشهر ---
blocks = [(1, 7), (8, 14), (15, 21), (22, 28)] + ([(29, dim)] if dim > 28 else [])
cards = ""
for n_w, (d1, d2) in enumerate(blocks, 1):
    if len(closed):
        days = closed["exit_t"].dt.day
        v = float(closed.loc[(days >= d1) & (days <= d2), "net"].sum())
    else:
        v = 0.0
    started = now.day >= d1
    c_ = tone(v, started)
    cards += (f'<div class="wk-card" style="background:{c_}22;border:1px solid {c_}">'
              f'<div class="wk-t">الأسبوع {n_w} ({d1}–{d2})</div>'
              f'<div class="wk-n" style="color:{c_}">{money(v) if started else "—"}</div></div>')
st.markdown(f'<div class="wk-grid">{cards}</div>', unsafe_allow_html=True)

# --- 3) مربع إظهار/إخفاء الإعدادات ---
show = st.checkbox("⚙️ إظهار الإعدادات", value=False, key="show_settings")
if show:
    with st.container(border=True):
        st.caption("تُطبَّق التغييرات تلقائياً بدون زر حفظ.")
        c1, c2 = st.columns(2)
        c1.selectbox("الإطار الزمني", TF_OPTIONS, key="w_tf")
        c2.number_input("رأس المال لكل صفقة ($)", min_value=10.0, max_value=100000.0, step=10.0, key="w_capital")
        st.multiselect("العملات (حلال)", list(ALL_SYMBOLS), format_func=lambda s: COINS[s], key="w_coins")
        c1, c2, c3 = st.columns(3)
        c1.number_input("أدنى تذبذب ATR %", min_value=0.0, max_value=10.0, step=0.05, key="w_min_vol")
        c2.number_input("الرسوم % لكل جهة", min_value=0.0, max_value=1.0, step=0.01, key="w_fee")
        c3.number_input("فحص كل N شمعة", min_value=1, max_value=20, step=1, key="w_step")

        st.markdown("**الموجة الأب**")
        c1, c2 = st.columns(2)
        c1.number_input("عتبة الانعكاس (ATR ×)", min_value=0.5, max_value=20.0, step=0.5, key="w_rev_atr")
        c2.number_input("أدنى تصحيح %", min_value=10.0, max_value=100.0, step=1.0, key="w_min_ret")
        c1.number_input("أدنى طول (شموع)", min_value=12, max_value=500, step=1, key="w_min_bars")
        c2.number_input("أقصى طول (شموع)", min_value=50, max_value=900, step=10, key="w_max_bars")

        st.markdown("**الفراكتل المصغّر**")
        c1, c2 = st.columns(2)
        c1.selectbox("منطقة البحث", ZONES_AR, key="w_zone")
        c2.number_input("أدنى ارتباط شكلي", min_value=-1.0, max_value=1.0, step=0.05, key="w_min_corr")
        c1.number_input("أدنى حركة % من مدى الموجة", min_value=1.0, max_value=80.0, step=1.0, key="w_min_frac")
        c2.number_input("دقة الشكل (نقاط)", min_value=8, max_value=40, step=1, key="w_res")

        st.markdown("**الإسقاط**")
        c1, c2 = st.columns(2)
        c1.number_input("مقياس الزمن ×", min_value=0.1, max_value=5.0, step=0.001, format="%.3f", key="w_time_mult")
        c2.number_input("مقياس السعر ×", min_value=0.1, max_value=5.0, step=0.001, format="%.3f", key="w_price_mult")

        st.markdown("**إدارة الصفقة**")
        c1, c2 = st.columns(2)
        c1.number_input("أقصى مدة (شموع)", min_value=3, max_value=200, step=1, key="w_hold")
        c2.number_input("الهدف % من المسار المسقَط", min_value=10, max_value=200, step=5, key="w_tp_frac")
        c1.number_input("أدنى ربح متوقع %", min_value=0.0, max_value=10.0, step=0.05, key="w_min_gain")
        c2.number_input("الوقف (ATR ×)", min_value=0.3, max_value=10.0, step=0.1, key="w_sl_atr")
        c1.number_input("أدنى عائد/مخاطرة", min_value=0.3, max_value=10.0, step=0.1, key="w_min_rr")
        if c2.button("🔄 تحديث البيانات"):
            st.cache_data.clear()
            st.rerun()

# حفظ القيم (لتبقى سارية حتى بعد إخفاء الإعدادات)
for _k in DEFAULTS:
    SAVED[_k] = st.session_state["w_" + _k]

# تنبيهات
if failed:
    st.warning("تعذّر جلب: " + "، ".join(COINS[s] for s in failed) + " (تحقق من رمز Yahoo في COINS).")
if skipped:
    st.info("استُبعدت لقلّة التذبذب: " + "، ".join(skipped))
if data:
    last_t = max(df.index[-2] for df in data.values() if len(df) > 2)
    st.caption(f"آخر شمعة مغلقة: {last_t:%Y-%m-%d %H:%M} UTC · بيانات yfinance · تتجدد كل 5 دقائق")

# --- 4) الأقسام ---
view = st.selectbox("القسم", ["التوصيات الحالية", "تفاصيل الصفقات", "ملخص العملات"])

if view == "التوصيات الحالية":
    if not recs:
        st.info("لا توجد إشارة شراء الآن على آخر شمعة مغلقة.")
    else:
        rd = pd.DataFrame([{
            "العملة": COINS[r["sym"]],
            "وقت الإشارة (UTC)": f"{r['time']:%m-%d %H:%M}",
            "السعر": fmt_price(r["price"]),
            "الهدف": fmt_price(r["tp"]),
            "الوقف": fmt_price(r["sl"]),
            "ربح متوقع %": round(r["gain"], 2),
            "R:R": round(r["rr"], 2),
            "الارتباط": round(r["corr"], 2),
            "المنطقة": r["zone"],
            "ATR %": round(vols.get(r["sym"], 0.0), 2),
        } for r in recs]).sort_values("الارتباط", ascending=False)
        st.dataframe(rd, hide_index=True, use_container_width=True)
        st.caption("الدخول المقترح عند افتتاح الشمعة التالية، شراء سبوت فقط.")

elif view == "تفاصيل الصفقات":
    if tdf.empty:
        st.info("لا توجد صفقات هذا الشهر بالإعدادات الحالية.")
    else:
        td = tdf.sort_values("exit_t", ascending=False)
        out = pd.DataFrame({
            "العملة": td["sym"].map(COINS),
            "الدخول (UTC)": td["entry_t"].dt.strftime("%m-%d %H:%M"),
            "الخروج (UTC)": td["exit_t"].dt.strftime("%m-%d %H:%M"),
            "سعر الدخول": td["entry"].map(fmt_price),
            "الهدف": td["tp"].map(fmt_price),
            "الوقف": td["sl"].map(fmt_price),
            "سعر الخروج": td["exit"].map(fmt_price),
            "السبب": td["reason"],
            "صافي $": td["net"].round(2),
        })
        st.dataframe(out, hide_index=True, use_container_width=True)

else:
    if closed.empty:
        st.info("لا توجد صفقات مغلقة هذا الشهر.")
    else:
        g = closed.groupby("sym").agg(trades=("net", "size"),
                                      wins=("net", lambda x: int((x > 0).sum())),
                                      net=("net", "sum")).reset_index()
        sm = pd.DataFrame({
            "العملة": g["sym"].map(COINS),
            "الصفقات": g["trades"],
            "نسبة النجاح %": (g["wins"] / g["trades"] * 100).round(0),
            "صافي $": g["net"].round(2),
            "ATR %": g["sym"].map(lambda s: round(vols.get(s, 0.0), 2)),
        }).sort_values("صافي $", ascending=False)
        st.dataframe(sm, hide_index=True, use_container_width=True)

st.caption("⚠️ باكتست تاريخي وتعليمي، وليس نصيحة مالية. الأداء السابق لا يضمن المستقبل.")