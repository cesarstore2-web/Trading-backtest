# app.py — موجات إليوت + فلتر العرض والطلب + الدعم والمقاومة
# Streamlit / سبوت شراء فقط / بيانات yfinance / توقيت UTC / 100$ لكل صفقة (ثابت في الخلفية)
import calendar
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="إليوت سبوت حلال", page_icon="📈", layout="centered")

CAPITAL = 100.0   # رأس مال كل صفقة (ثابت في الخلفية، بدون خانة إدخال)

# ───────────────────────── العملات (رموز Yahoo Finance) ─────────────────────────
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
TF_OPTIONS = ["5m", "15m", "30m", "1h"]
MODES = ["الاثنان", "موجة 3 فقط", "موجة 5 فقط"]

DEFAULTS = dict(
    tf="15m",
    coins=list(ALL_SYMBOLS),
    min_vol=0.20,      # أدنى تذبذب ATR %
    fee=0.10,          # % لكل جهة
    # ── قواعد إليوت ──
    mode="الاثنان",
    rev_atr=3.0,       # حساسية الموجات (انعكاس ATR ×)
    w1_min=3.0,        # أدنى حجم للموجة 1 (ATR ×)
    w2_min=38.2, w2_max=78.6,   # تصحيح الموجة 2 %
    w3_min=1.0,        # الموجة 3 ≥ الموجة 1 ×
    w4_min=23.6, w4_max=50.0,   # تصحيح الموجة 4 %
    ext3=1.618,        # هدف الموجة 3 = قاع 2 + ext3 × الموجة 1
    ext5=1.0,          # هدف الموجة 5 = قاع 4 + ext5 × الموجة 1
    sl_buf=0.3,        # الوقف تحت قاع الموجة (ATR ×)
    hold=48,           # أقصى مدة (شموع)
    min_gain=0.8,      # أدنى ربح متوقع %
    min_rr=1.2,        # أدنى عائد/مخاطرة
    # ── فلتر العرض والطلب ──
    sd_on=True, sd_require=True, sd_cap=True,
    zone_imp=3.0,      # قوة الاندفاع لتكوين المنطقة (ATR ×)
    d_tol=0.5,         # هامش لمس منطقة الطلب (ATR ×)
    zone_age=400,      # أقصى عمر للمنطقة (شموع)
    # ── الدعم والمقاومة ──
    sr_on=True, sr_require=False, sr_cap=True,
    sr_lookback=40,    # عدد القمم/القيعان المستخدمة
    sr_touches=2,      # أدنى عدد لمسات للمستوى
    sr_tol=0.6,        # هامش تجميع المستوى (ATR ×)
    sr_buf=0.2,        # مسافة الأمان تحت المقاومة (ATR ×)
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


# ───────────────────────── محرك إليوت ─────────────────────────
def atr_arr(h, l, c, n=14):
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    a = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy(dtype=float, copy=True)
    a[:n - 1] = np.nan
    return a


def swings(h, l, atr, rev):
    """قمم/قيعان مؤكدة (ZigZag بـ ATR). كل عنصر: (فهرس القمة/القاع، السعر، النوع +1/-1، شمعة التأكيد)."""
    n = len(h)
    piv = []
    d, hi, hi_i, lo, lo_i = 0, h[0], 0, l[0], 0
    for i in range(1, n):
        a = atr[i]
        ok = not np.isnan(a)
        if d == 0:
            if ok:
                if h[i] - lo >= rev * a:
                    piv.append((lo_i, float(lo), -1, i))
                    d, hi, hi_i = 1, h[i], i
                    continue
                if hi - l[i] >= rev * a:
                    piv.append((hi_i, float(hi), 1, i))
                    d, lo, lo_i = -1, l[i], i
                    continue
            if h[i] > hi:
                hi, hi_i = h[i], i
            if l[i] < lo:
                lo, lo_i = l[i], i
        elif d == 1:
            if h[i] > hi:
                hi, hi_i = h[i], i
            elif ok and hi - l[i] >= rev * a:
                piv.append((hi_i, float(hi), 1, i))
                d, lo, lo_i = -1, l[i], i
        else:
            if l[i] < lo:
                lo, lo_i = l[i], i
            elif ok and h[i] - lo >= rev * a:
                piv.append((lo_i, float(lo), -1, i))
                d, hi, hi_i = 1, h[i], i
    return piv


def build_zones(piv, o, h, l, c, atr, p):
    """مناطق الطلب (D) من القيعان والعرض (S) من القمم بعد اندفاع قوي. المنطقة تُفعَّل عند تأكيد الاندفاع."""
    n = len(c)
    zones = []
    for k in range(len(piv) - 1):
        idx, pr, typ, _ = piv[k]
        _, npr, _, nconf = piv[k + 1]
        a = atr[nconf]
        if np.isnan(a) or abs(npr - pr) < p["zone_imp"] * a:
            continue
        if typ == -1:
            lo_z = float(l[idx])
            hi_z = float(max(max(o[idx], c[idx]), lo_z + 0.2 * a))
            kind = "D"
        else:
            hi_z = float(h[idx])
            lo_z = float(min(min(o[idx], c[idx]), hi_z - 0.2 * a))
            kind = "S"
        brk = n + 10 ** 6
        if nconf + 1 < n:
            seg = c[nconf + 1:]
            hit = np.nonzero(seg < lo_z)[0] if kind == "D" else np.nonzero(seg > hi_z)[0]
            if hit.size:
                brk = nconf + 1 + int(hit[0])
        zones.append(dict(kind=kind, lo=lo_z, hi=hi_z, idx=idx, act=nconf, brk=brk))
    return zones


def sr_levels(piv, k_last, atr_i, p, exclude_last=False):
    end = k_last - 1 if exclude_last else k_last
    start = max(0, k_last - int(p["sr_lookback"]) + 1)
    if end < start:
        return []
    prices = sorted(piv[m][1] for m in range(start, end + 1))
    tol = p["sr_tol"] * atr_i
    levels, cur = [], [prices[0]]
    for x in prices[1:]:
        if x - cur[-1] <= tol:
            cur.append(x)
        else:
            if len(cur) >= p["sr_touches"]:
                levels.append(float(np.mean(cur)))
            cur = [x]
    if len(cur) >= p["sr_touches"]:
        levels.append(float(np.mean(cur)))
    return levels


def elliott_pattern(k, piv, atr, p):
    """نمط إليوت عند تأكيد القاع k: دخول الموجة 3 (نهاية الموجة 2) أو الموجة 5 (نهاية الموجة 4)."""
    conf = piv[k][3]
    a = atr[conf]
    if np.isnan(a) or piv[k][2] != -1:
        return None
    mode = p["mode"]

    def wave2_ok(L0, H1, L2):
        w1 = H1 - L0
        if w1 <= 0 or w1 < p["w1_min"] * a or L2 <= L0:
            return None
        retr = (H1 - L2) / w1 * 100.0
        if not (p["w2_min"] <= retr <= p["w2_max"]):
            return None
        return w1

    if mode in ("الاثنان", "موجة 5 فقط") and k >= 4:
        L0, H1, L2, H3, L4 = (piv[k - 4][1], piv[k - 3][1], piv[k - 2][1], piv[k - 1][1], piv[k][1])
        w1 = wave2_ok(L0, H1, L2)
        if w1 is not None and H3 > H1:
            w3 = H3 - L2
            retr4 = (H3 - L4) / w3 * 100.0 if w3 > 0 else -1
            if w3 >= p["w3_min"] * w1 and p["w4_min"] <= retr4 <= p["w4_max"] and L4 > H1:
                return dict(kind="موجة 5", low=L4, low_idx=piv[k][0],
                            sl=L4 - p["sl_buf"] * a, tp=L4 + p["ext5"] * w1)
    if mode in ("الاثنان", "موجة 3 فقط") and k >= 2:
        L0, H1, L2 = piv[k - 2][1], piv[k - 1][1], piv[k][1]
        w1 = wave2_ok(L0, H1, L2)
        if w1 is not None:
            return dict(kind="موجة 3", low=L2, low_idx=piv[k][0],
                        sl=L2 - p["sl_buf"] * a, tp=L2 + p["ext3"] * w1)
    return None


def evaluate(k, piv, zones, c, atr, p):
    base = elliott_pattern(k, piv, atr, p)
    if base is None:
        return None
    conf = piv[k][3]
    a = atr[conf]
    ref = float(c[conf])
    low, low_idx = base["low"], base["low_idx"]
    sl, tp = base["sl"], base["tp"]
    dem_flag = sr_flag = False

    # فلتر العرض والطلب
    if p["sd_on"]:
        tol = p["d_tol"] * a
        dem_flag = any(z["kind"] == "D" and z["idx"] < low_idx and z["act"] <= low_idx
                       and z["brk"] > conf and conf - z["act"] <= p["zone_age"]
                       and z["lo"] - tol <= low <= z["hi"] + tol for z in zones)
        if p["sd_require"] and not dem_flag:
            return None
        if p["sd_cap"]:
            sup = [z["lo"] for z in zones if z["kind"] == "S" and z["act"] <= conf < z["brk"]
                   and conf - z["act"] <= p["zone_age"] and z["lo"] > ref]
            if sup:
                tp = min(tp, min(sup))

    # الدعم والمقاومة
    if p["sr_on"]:
        sup_lv = sr_levels(piv, k, a, p, exclude_last=True)
        sr_flag = any(abs(lv - low) <= p["sr_tol"] * a for lv in sup_lv)
        if p["sr_require"] and not sr_flag:
            return None
        if p["sr_cap"]:
            res = [lv for lv in sr_levels(piv, k, a, p) if lv > ref]
            if res:
                tp = min(tp, min(res) - p["sr_buf"] * a)

    if sl >= ref or tp <= ref:
        return None
    gain = (tp / ref - 1.0) * 100.0
    rr = (tp - ref) / (ref - sl)
    if gain < p["min_gain"] or rr < p["min_rr"]:
        return None
    return dict(kind=base["kind"], tp=float(tp), sl=float(sl), gain=float(gain), rr=float(rr),
                dem=bool(dem_flag), sr=bool(sr_flag), ref=ref)


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
    o, h, l, c = (np.array(df[k].to_numpy(), dtype=float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    atr = atr_arr(h, l, c)
    piv = swings(h, l, atr, p["rev_atr"])
    zones = build_zones(piv, o, h, l, c, atr, p)

    start = int(times.searchsorted(pd.Timestamp(month_iso)))
    fee, hold = p["fee"] / 100.0, int(p["hold"])
    trades, rec, busy = [], None, -1

    for k in range(2, len(piv)):
        if piv[k][2] != -1:
            continue
        conf = piv[k][3]
        if conf < start or conf < busy:
            continue
        sig = evaluate(k, piv, zones, c, atr, p)
        if sig is None:
            continue
        if conf == n - 1:                   # توصية حالية: الدخول عند افتتاح الشمعة القادمة
            rec = dict(sym=sym, time=times[conf], price=sig["ref"], tp=sig["tp"], sl=sig["sl"],
                       gain=sig["gain"], rr=sig["rr"], kind=sig["kind"], dem=sig["dem"], sr=sig["sr"])
            continue
        j = conf + 1
        entry, tp, sl = float(o[j]), sig["tp"], sig["sl"]
        if entry >= tp or entry <= sl:
            continue
        m, status, ex, reason = j, "open", None, ""
        while m < n:
            if l[m] <= sl:
                ex, reason, status = min(sl, float(o[m])), "وقف", "closed"
                break
            if h[m] >= tp:
                ex, reason, status = tp, "هدف", "closed"
                break
            if m - j >= hold:
                ex, reason, status = float(c[m]), "مدة", "closed"
                break
            m += 1
        if status == "open":
            m = n - 1
            ex, reason = float(c[n - 1]), "مفتوحة"
        qty = CAPITAL / entry
        net = qty * (ex - entry) - fee * (CAPITAL + qty * ex)
        trades.append(dict(sym=sym, entry_t=times[j], exit_t=times[m], entry=entry, tp=tp, sl=sl,
                           exit=ex, reason=reason, net=float(net), status=status,
                           kind=sig["kind"], dem=sig["dem"], sr=sig["sr"]))
        busy = m if status == "closed" else n + 1
    vol = float(np.nanmean(atr[-200:] / c[-200:] * 100.0))
    return trades, rec, vol


# ───────────────────────── الواجهة ─────────────────────────
now = datetime.now(timezone.utc)
month_start = pd.Timestamp(year=now.year, month=now.month, day=1)
dim = calendar.monthrange(now.year, now.month)[1]
month_label = f"{AR_MONTHS[now.month - 1]} {now.year}"

st.markdown("<h3 style='text-align:center;margin:0 0 8px'>📈 موجات إليوت — سبوت العملات الحلال</h3>",
            unsafe_allow_html=True)

PARAM_KEYS = [k for k in DEFAULTS if k not in ("tf", "coins", "min_vol")]
params = {k: cfg[k] for k in PARAM_KEYS}
params_t = tuple(sorted(params.items(), key=lambda kv: kv[0]))

with st.spinner("جاري جلب بيانات yfinance وتحليل موجات إليوت…"):
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
                                "reason", "net", "status", "kind", "dem", "sr"])
else:
    tdf["entry_t"] = pd.to_datetime(tdf["entry_t"])
    tdf["exit_t"] = pd.to_datetime(tdf["exit_t"])
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
    st.caption("تُطبَّق التغييرات تلقائياً بدون زر حفظ.")
    with st.container(border=True):
        st.markdown("**عام**")
        c1, c2, c3 = st.columns(3)
        c1.selectbox("الإطار الزمني", TF_OPTIONS, key="w_tf")
        c2.number_input("أدنى تذبذب ATR %", min_value=0.0, max_value=10.0, step=0.05, key="w_min_vol")
        c3.number_input("الرسوم % لكل جهة", min_value=0.0, max_value=1.0, step=0.01, key="w_fee")
        st.multiselect("العملات", list(ALL_SYMBOLS), format_func=lambda s: COINS[s], key="w_coins")

    with st.container(border=True):
        st.markdown("**موجات إليوت**")
        c1, c2 = st.columns(2)
        c1.selectbox("نوع الدخول", MODES, key="w_mode")
        c2.number_input("حساسية الموجات (ATR ×)", min_value=1.0, max_value=15.0, step=0.5, key="w_rev_atr")
        c1.number_input("أدنى حجم للموجة 1 (ATR ×)", min_value=0.5, max_value=20.0, step=0.5, key="w_w1_min")
        c2.number_input("الموجة 3 ≥ الموجة 1 ×", min_value=0.5, max_value=5.0, step=0.1, key="w_w3_min")
        c1.number_input("تصحيح الموجة 2 — أدنى %", min_value=10.0, max_value=100.0, step=1.0, key="w_w2_min")
        c2.number_input("تصحيح الموجة 2 — أقصى %", min_value=10.0, max_value=100.0, step=1.0, key="w_w2_max")
        c1.number_input("تصحيح الموجة 4 — أدنى %", min_value=5.0, max_value=100.0, step=1.0, key="w_w4_min")
        c2.number_input("تصحيح الموجة 4 — أقصى %", min_value=5.0, max_value=100.0, step=1.0, key="w_w4_max")
        c1.number_input("هدف الموجة 3 (× الموجة 1)", min_value=0.5, max_value=5.0, step=0.001, format="%.3f", key="w_ext3")
        c2.number_input("هدف الموجة 5 (× الموجة 1)", min_value=0.3, max_value=5.0, step=0.1, key="w_ext5")
        c1.number_input("الوقف تحت القاع (ATR ×)", min_value=0.0, max_value=5.0, step=0.1, key="w_sl_buf")
        c2.number_input("أقصى مدة (شموع)", min_value=3, max_value=300, step=1, key="w_hold")
        c1.number_input("أدنى ربح متوقع %", min_value=0.0, max_value=20.0, step=0.1, key="w_min_gain")
        c2.number_input("أدنى عائد/مخاطرة", min_value=0.3, max_value=10.0, step=0.1, key="w_min_rr")

    with st.container(border=True):
        st.markdown("**فلتر العرض والطلب**")
        st.checkbox("تفعيل الفلتر", key="w_sd_on")
        st.checkbox("اشتراط أن يلمس قاع الموجة منطقة طلب", key="w_sd_require")
        st.checkbox("حصر الهدف عند أول منطقة عرض فوق السعر", key="w_sd_cap")
        c1, c2, c3 = st.columns(3)
        c1.number_input("قوة الاندفاع (ATR ×)", min_value=1.0, max_value=15.0, step=0.5, key="w_zone_imp")
        c2.number_input("هامش اللمس (ATR ×)", min_value=0.0, max_value=3.0, step=0.1, key="w_d_tol")
        c3.number_input("عمر المنطقة (شموع)", min_value=20, max_value=2000, step=20, key="w_zone_age")

    with st.container(border=True):
        st.markdown("**الدعم والمقاومة**")
        st.checkbox("تفعيل الدعم والمقاومة", key="w_sr_on")
        st.checkbox("اشتراط وجود دعم عند قاع الموجة", key="w_sr_require")
        st.checkbox("حصر الهدف تحت أقرب مقاومة", key="w_sr_cap")
        c1, c2 = st.columns(2)
        c1.number_input("عدد القمم/القيعان المستخدمة", min_value=10, max_value=200, step=5, key="w_sr_lookback")
        c2.number_input("أدنى عدد لمسات", min_value=2, max_value=6, step=1, key="w_sr_touches")
        c1.number_input("هامش التجميع (ATR ×)", min_value=0.1, max_value=3.0, step=0.1, key="w_sr_tol")
        c2.number_input("مسافة الأمان تحت المقاومة (ATR ×)", min_value=0.0, max_value=3.0, step=0.1, key="w_sr_buf")

    if st.button("🔄 تحديث البيانات"):
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
yn = lambda b: "✓" if b else "—"

if view == "التوصيات الحالية":
    if not recs:
        st.info("لا توجد إشارة شراء الآن على آخر شمعة مغلقة.")
    else:
        rd = pd.DataFrame([{
            "العملة": COINS[r["sym"]],
            "الموجة": r["kind"],
            "وقت الإشارة (UTC)": f"{r['time']:%m-%d %H:%M}",
            "السعر": fmt_price(r["price"]),
            "الهدف": fmt_price(r["tp"]),
            "الوقف": fmt_price(r["sl"]),
            "ربح متوقع %": round(r["gain"], 2),
            "R:R": round(r["rr"], 2),
            "طلب": yn(r["dem"]),
            "دعم": yn(r["sr"]),
            "ATR %": round(vols.get(r["sym"], 0.0), 2),
        } for r in recs]).sort_values("R:R", ascending=False)
        st.dataframe(rd, hide_index=True, use_container_width=True)
        st.caption("الدخول المقترح عند افتتاح الشمعة التالية، شراء سبوت فقط.")

elif view == "تفاصيل الصفقات":
    if tdf.empty:
        st.info("لا توجد صفقات هذا الشهر بالإعدادات الحالية.")
    else:
        td = tdf.sort_values("exit_t", ascending=False)
        out = pd.DataFrame({
            "العملة": td["sym"].map(COINS),
            "الموجة": td["kind"],
            "الدخول (UTC)": td["entry_t"].dt.strftime("%m-%d %H:%M"),
            "الخروج (UTC)": td["exit_t"].dt.strftime("%m-%d %H:%M"),
            "سعر الدخول": td["entry"].map(fmt_price),
            "الهدف": td["tp"].map(fmt_price),
            "الوقف": td["sl"].map(fmt_price),
            "سعر الخروج": td["exit"].map(fmt_price),
            "السبب": td["reason"],
            "طلب": td["dem"].map(yn),
            "دعم": td["sr"].map(yn),
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