# -*- coding: utf-8 -*-
"""
استراتيجية اختراق القمة والسيولة (Momentum Swing Breakout)
تداول فوري Spot - شراء فقط - بدون رافعة مالية
تشغيل:  streamlit run app.py
المتطلبات: pip install streamlit yfinance pandas numpy
"""

import calendar
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# ----------------------------------------------------------------------
# الإعدادات الثابتة
# ----------------------------------------------------------------------
st.set_page_config(page_title="اختراق القمة والسيولة", page_icon="📈", layout="centered")

COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD",
    "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", "XLM-USD", "VET-USD",
    "HBAR-USD", "FIL-USD", "ICP-USD", "APT-USD", "ARB-USD", "OP-USD",
    "RENDER-USD", "GRT-USD", "TIA-USD", "SUI-USD",
]

CAPITAL = 100.0          # رأس مال كل صفقة (ثابت - يعمل في الخلفية فقط)
BE_BUFFER = 0.001        # +0.1% لتغطية العمولة عند التأمين

SECTIONS = [
    "التوصيات الحالية",
    "أداء الأسبوع الحالي",
    "سجل 4 أسابيع للشهر الحالي",
    "تفاصيل الصفقات",
    "الإعدادات",
]

TIMEFRAMES = ["5m", "15m", "30m", "1h"]
PERIODS = {"5m": "30d", "15m": "60d", "30m": "60d", "1h": "180d"}

DEFAULT_CFG = {
    "tf": "15m",
    "use_ema": True,
    "ema_len": 200,
    "lookback": 12,
    "vol_len": 20,
    "vol_mult": 1.3,
    "rr": 2.0,
}

# ----------------------------------------------------------------------
# تنسيق RTL
# ----------------------------------------------------------------------
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
        direction: rtl; text-align: right;
    }
    .block-container {padding-top: 1.2rem; padding-left: .8rem; padding-right: .8rem;}
    div[data-baseweb="select"] > div {direction: rtl;}
    [data-testid="stMetric"] {text-align: right;}
    [data-testid="stDataFrame"] {direction: ltr;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "cfg" not in st.session_state:
    st.session_state["cfg"] = DEFAULT_CFG.copy()
cfg = st.session_state["cfg"]


# ----------------------------------------------------------------------
# جلب البيانات
# ----------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_all(tf: str) -> dict:
    """تحميل بيانات كل العملات مرة واحدة وتوحيد التوقيت."""
    raw = yf.download(
        COINS,
        period=PERIODS[tf],
        interval=tf,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    out = {}
    if raw is None or raw.empty:
        return out
    top = raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex) else []
    for sym in COINS:
        if sym not in top:
            continue
        df = raw[sym][["Open", "High", "Low", "Close", "Volume"]].dropna()
        if df.empty:
            continue
        # توحيد التوقيت: تحويل إلى UTC ثم إزالة معلومات المنطقة الزمنية
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        else:
            df.index = df.index.tz_localize(None)
        # حذف الشمعة الأخيرة لأنها غير مكتملة (ما زالت تتشكل)
        df = df.iloc[:-1]
        if len(df) > 50:
            out[sym] = df
    return out


# ----------------------------------------------------------------------
# منطق الاستراتيجية + المحاكاة
# ----------------------------------------------------------------------
def run_backtest(sym: str, df: pd.DataFrame, cfg: dict) -> list:
    n_look = int(cfg["lookback"])
    vol_len = int(cfg["vol_len"])
    ema_len = int(cfg["ema_len"])

    d = df.copy()
    d["psh"] = d["High"].rolling(n_look).max().shift(1)     # أعلى قمة لآخر N شمعة سابقة
    d["psl"] = d["Low"].rolling(n_look).min().shift(1)      # أدنى قاع لآخر N شمعة سابقة
    d["avgvol"] = d["Volume"].rolling(vol_len).mean().shift(1)
    d["ema"] = d["Close"].ewm(span=ema_len, adjust=False).mean()

    cond = (
        (d["Close"] > d["Open"])
        & (d["Close"] > d["psh"])
        & (d["Volume"] > cfg["vol_mult"] * d["avgvol"])
    )
    if cfg["use_ema"]:
        cond &= d["Close"] > d["ema"]
        cond &= pd.Series(np.arange(len(d)) >= ema_len, index=d.index)  # انتظار اكتمال تسخين EMA
    sig = cond.fillna(False).values

    idx = d.index
    o, h, l, c = d["Open"].values, d["High"].values, d["Low"].values, d["Close"].values
    psl = d["psl"].values
    n = len(d)
    rr = float(cfg["rr"])

    trades = []
    i = 0
    while i < n:
        if not sig[i]:
            i += 1
            continue

        entry = c[i]
        sl0 = psl[i]
        risk = entry - sl0
        if not np.isfinite(risk) or risk <= 0:
            i += 1
            continue

        tp = entry + rr * risk
        be_trigger = entry + 1.0 * risk
        be_price = entry * (1 + BE_BUFFER)
        cur_sl = sl0
        be_on = False
        exit_idx, exit_price, status = None, None, None

        for j in range(i + 1, n):
            if l[j] <= cur_sl:
                exit_price = min(o[j], cur_sl)
                exit_idx = j
                status = "تأمين (Breakeven)" if be_on else "خاسرة"
                break
            if h[j] >= tp:
                exit_price, exit_idx, status = tp, j, "رابحة (TP)"
                break
            if (not be_on) and h[j] >= be_trigger:
                be_on = True
                cur_sl = be_price

        if exit_idx is None:
            exit_price = c[n - 1]
            status = "مفتوحة"
            exit_time = None
        else:
            exit_time = idx[exit_idx]

        pnl_pct = (exit_price / entry - 1) * 100
        trades.append(
            {
                "العملة": sym.replace("-USD", ""),
                "وقت الدخول": idx[i],
                "سعر الدخول": entry,
                "وقف الخسارة الأولي": sl0,
                "الهدف TP": tp,
                "مستوى التأمين 1:1": be_trigger,
                "وقف الخسارة الحالي": cur_sl,
                "التأمين مفعّل": be_on,
                "وقت الخروج": exit_time,
                "سعر الخروج/الحالي": exit_price,
                "الحالة": status,
                "النسبة %": pnl_pct,
                "الربح/الخسارة $": CAPITAL * (exit_price / entry - 1),
            }
        )
        i = (exit_idx + 1) if exit_idx is not None else n
    return trades


@st.cache_data(ttl=300, show_spinner=False)
def compute_trades(tf: str, cfg_items: tuple) -> pd.DataFrame:
    cfg_local = dict(cfg_items)
    data = fetch_all(tf)
    rows = []
    for sym, df in data.items():
        rows.extend(run_backtest(sym, df, cfg_local))
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows)
    t["وقت الدخول"] = pd.to_datetime(t["وقت الدخول"]).dt.tz_localize(None)
    t["وقت الخروج"] = pd.to_datetime(t["وقت الخروج"]).dt.tz_localize(None)
    return t.sort_values("وقت الدخول", ascending=False).reset_index(drop=True)


def stats(t: pd.DataFrame) -> dict:
    closed = t[t["الحالة"] != "مفتوحة"]
    wins = (closed["الحالة"] == "رابحة (TP)").sum()
    be = (closed["الحالة"] == "تأمين (Breakeven)").sum()
    loss = (closed["الحالة"] == "خاسرة").sum()
    total = len(closed)
    return {
        "الصفقات المغلقة": int(total),
        "رابحة": int(wins),
        "تأمين": int(be),
        "خاسرة": int(loss),
        "نسبة النجاح %": round(wins / total * 100, 1) if total else 0.0,
        "مغلق $": round(closed["الربح/الخسارة $"].sum(), 2),
        "عائم $": round(t[t["الحالة"] == "مفتوحة"]["الربح/الخسارة $"].sum(), 2),
        "الإجمالي $": round(t["الربح/الخسارة $"].sum(), 2),
    }


def show_stats(t: pd.DataFrame):
    s = stats(t)
    c1, c2 = st.columns(2)
    c1.metric("الصفقات المغلقة", s["الصفقات المغلقة"])
    c2.metric("نسبة النجاح", f'{s["نسبة النجاح %"]}%')
    c3, c4, c5 = st.columns(3)
    c3.metric("رابحة", s["رابحة"])
    c4.metric("تأمين", s["تأمين"])
    c5.metric("خاسرة", s["خاسرة"])
    c6, c7 = st.columns(2)
    c6.metric("ربح/خسارة مغلقة", f'{s["مغلق $"]:+.2f} $')
    c7.metric("ربح/خسارة عائمة", f'{s["عائم $"]:+.2f} $')
    st.metric("الإجمالي", f'{s["الإجمالي $"]:+.2f} $')


def fmt_table(t: pd.DataFrame, cols: list) -> pd.DataFrame:
    d = t[cols].copy()
    for col in d.columns:
        if d[col].dtype.kind == "f":
            d[col] = d[col].map(lambda x: f"{x:,.6g}" if abs(x) < 1 else f"{x:,.4f}")
    return d


# ----------------------------------------------------------------------
# الواجهة
# ----------------------------------------------------------------------
st.title("📈 اختراق القمة والسيولة")
st.caption(f"Spot - شراء فقط - 22 عملة حلال - الفريم: {cfg['tf']} - رأس مال الصفقة ثابت")

section = st.selectbox("القسم", SECTIONS, key="section_nav")

now = datetime.utcnow()

# ---------------- الإعدادات ----------------
if section == "الإعدادات":
    st.subheader("⚙️ الإعدادات")
    with st.form("settings_form"):
        tf = st.selectbox("الإطار الزمني", TIMEFRAMES, index=TIMEFRAMES.index(cfg["tf"]))
        use_ema = st.checkbox("تفعيل فلتر الاتجاه (EMA)", value=cfg["use_ema"])
        ema_len = st.number_input("رقم المتوسط EMA", min_value=2, max_value=1000, value=int(cfg["ema_len"]), step=1)
        lookback = st.number_input("عدد الشموع للقمة/القاع (PSH/PSL)", min_value=2, max_value=200, value=int(cfg["lookback"]), step=1)
        vol_len = st.number_input("عدد شموع متوسط الحجم", min_value=2, max_value=200, value=int(cfg["vol_len"]), step=1)
        vol_mult = st.number_input("مضاعف الحجم", min_value=0.1, max_value=10.0, value=float(cfg["vol_mult"]), step=0.1, format="%.2f")
        rr = st.number_input("مضاعف المخاطرة/العائد (RR)", min_value=0.5, max_value=10.0, value=float(cfg["rr"]), step=0.5, format="%.2f")
        submitted = st.form_submit_button("💾 حفظ وتطبيق")
    if submitted:
        st.session_state["cfg"] = {
            "tf": tf, "use_ema": use_ema, "ema_len": int(ema_len),
            "lookback": int(lookback), "vol_len": int(vol_len),
            "vol_mult": float(vol_mult), "rr": float(rr),
        }
        st.success("تم حفظ الإعدادات. انتقل إلى أي قسم لرؤية النتائج.")
    if st.button("🔄 تحديث البيانات الآن"):
        st.cache_data.clear()
        st.success("تم مسح الذاكرة المؤقتة.")
    st.stop()

# ---------------- حساب الصفقات ----------------
with st.spinner("جارٍ تحميل البيانات وتحليل العملات..."):
    trades = compute_trades(cfg["tf"], tuple(sorted(cfg.items())))

if trades.empty:
    st.warning("لا توجد صفقات أو تعذر تحميل البيانات حالياً. جرّب تحديث البيانات من قسم الإعدادات.")
    st.stop()

week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
last_day = calendar.monthrange(now.year, now.month)[1]

# ---------------- التوصيات الحالية ----------------
if section == "التوصيات الحالية":
    st.subheader("🎯 التوصيات الحالية (صفقات مفتوحة)")
    open_t = trades[trades["الحالة"] == "مفتوحة"].copy()
    if open_t.empty:
        st.info("لا توجد توصيات نشطة حالياً.")
    else:
        for _, r in open_t.iterrows():
            icon = "🟢" if r["النسبة %"] >= 0 else "🔴"
            with st.container(border=True):
                st.markdown(f"### {icon} {r['العملة']}")
                st.write(f"وقت الدخول: {r['وقت الدخول']:%Y-%m-%d %H:%M} (UTC)")
                a, b = st.columns(2)
                a.metric("سعر الدخول", f"{r['سعر الدخول']:,.6g}")
                b.metric("السعر الحالي", f"{r['سعر الخروج/الحالي']:,.6g}", f"{r['النسبة %']:+.2f}%")
                c1, c2 = st.columns(2)
                c1.metric("🛑 وقف الخسارة", f"{r['وقف الخسارة الحالي']:,.6g}")
                c2.metric("🎯 الهدف", f"{r['الهدف TP']:,.6g}")
                st.caption(
                    f"مستوى التأمين 1:1 عند {r['مستوى التأمين 1:1']:,.6g} - "
                    + ("✅ التأمين مفعّل" if r["التأمين مفعّل"] else "لم يُفعَّل بعد")
                    + f" - الربح/الخسارة العائمة: {r['الربح/الخسارة $']:+.2f} $"
                )

# ---------------- أداء الأسبوع الحالي ----------------
elif section == "أداء الأسبوع الحالي":
    st.subheader("📅 أداء الأسبوع الحالي")
    st.caption(f"من {week_start:%Y-%m-%d} (الاثنين) حتى الآن")
    wk = trades[trades["وقت الدخول"] >= week_start]
    if wk.empty:
        st.info("لا توجد صفقات هذا الأسبوع.")
    else:
        show_stats(wk)
        st.markdown("**حسب العملة**")
        by = wk.groupby("العملة").agg(
            الصفقات=("العملة", "count"),
            الربح_الخسارة=("الربح/الخسارة $", "sum"),
        ).sort_values("الربح_الخسارة", ascending=False).round(2)
        by.columns = ["الصفقات", "الربح/الخسارة $"]
        st.dataframe(by, use_container_width=True)

# ---------------- سجل 4 أسابيع ----------------
elif section == "سجل 4 أسابيع للشهر الحالي":
    st.subheader("🗓️ سجل 4 أسابيع للشهر الحالي")
    st.caption(f"شهر {now:%Y-%m} - الأسابيع: 1-7، 8-14، 15-21، 22-{last_day}")
    bounds = [
        (1, 8, "الأسبوع 1 (1-7)"),
        (8, 15, "الأسبوع 2 (8-14)"),
        (15, 22, "الأسبوع 3 (15-21)"),
        (22, last_day + 1, f"الأسبوع 4 (22-{last_day})"),
    ]
    rows = []
    for d1, d2, label in bounds:
        start = month_start.replace(day=d1)
        end = (month_start.replace(day=d2) if d2 <= last_day
               else (month_start.replace(day=last_day) + timedelta(days=1)))
        part = trades[(trades["وقت الدخول"] >= start) & (trades["وقت الدخول"] < end)]
        closed = part[part["الحالة"] != "مفتوحة"]
        wins = int((closed["الحالة"] == "رابحة (TP)").sum())
        rows.append({
            "الأسبوع": label,
            "الصفقات": len(part),
            "رابحة": wins,
            "تأمين": int((closed["الحالة"] == "تأمين (Breakeven)").sum()),
            "خاسرة": int((closed["الحالة"] == "خاسرة").sum()),
            "نسبة النجاح %": round(wins / len(closed) * 100, 1) if len(closed) else 0.0,
            "الربح/الخسارة $": round(part["الربح/الخسارة $"].sum(), 2),
        })
    log = pd.DataFrame(rows)
    st.dataframe(log, use_container_width=True, hide_index=True)
    st.metric("إجمالي الشهر", f'{log["الربح/الخسارة $"].sum():+.2f} $')
    mt = trades[trades["وقت الدخول"] >= month_start]
    if not mt.empty:
        st.markdown("**ملخص الشهر**")
        show_stats(mt)
    if cfg["tf"] != "1h" and (now - month_start).days > 28:
        st.caption("ملاحظة: بيانات الفريمات الصغيرة محدودة المدة في Yahoo Finance.")

# ---------------- تفاصيل الصفقات ----------------
elif section == "تفاصيل الصفقات":
    st.subheader("📋 تفاصيل الصفقات")
    status_opts = ["الكل", "مفتوحة", "رابحة (TP)", "تأمين (Breakeven)", "خاسرة"]
    status_sel = st.selectbox("تصفية حسب الحالة", status_opts)
    coin_opts = ["الكل"] + sorted(trades["العملة"].unique().tolist())
    coin_sel = st.selectbox("تصفية حسب العملة", coin_opts)
    period_sel = st.selectbox("الفترة", ["الشهر الحالي", "الأسبوع الحالي", "كل البيانات"])

    t = trades.copy()
    if status_sel != "الكل":
        t = t[t["الحالة"] == status_sel]
    if coin_sel != "الكل":
        t = t[t["العملة"] == coin_sel]
    if period_sel == "الشهر الحالي":
        t = t[t["وقت الدخول"] >= month_start]
    elif period_sel == "الأسبوع الحالي":
        t = t[t["وقت الدخول"] >= week_start]

    st.caption(f"عدد الصفقات: {len(t)}")
    if t.empty:
        st.info("لا توجد صفقات مطابقة.")
    else:
        cols = [
            "العملة", "الحالة", "وقت الدخول", "سعر الدخول", "وقف الخسارة الأولي",
            "الهدف TP", "سعر الخروج/الحالي", "النسبة %", "الربح/الخسارة $", "وقت الخروج",
        ]
        d = t[cols].copy()
        d["النسبة %"] = d["النسبة %"].round(2)
        d["الربح/الخسارة $"] = d["الربح/الخسارة $"].round(2)
        st.dataframe(d, use_container_width=True, hide_index=True)

st.divider()
st.caption("⚠️ للأغراض التعليمية فقط وليست نصيحة استثمارية. المحاكاة تفترض الدخول عند إغلاق شمعة الإشارة، "
           "وعند تحقق الوقف والهدف في نفس الشمعة يُفترض الوقف أولاً (تحفظاً).")
