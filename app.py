# -*- coding: utf-8 -*-
"""
استراتيجية تقاطع متوسطين متحركين + وقف خسارة ATR + عائد R:R
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
st.set_page_config(page_title="تقاطع المتوسطين", page_icon="📈", layout="centered")

COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD",
    "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", "XLM-USD", "VET-USD",
    "HBAR-USD", "FIL-USD", "ICP-USD", "APT-USD", "ARB-USD", "OP-USD",
    "RENDER-USD", "GRT-USD", "TIA-USD", "SUI-USD",
]

CAPITAL = 100.0          # رأس مال كل صفقة (ثابت - يعمل في الخلفية فقط)
BE_BUFFER = 0.001        # +0.1% لتغطية العمولة عند التأمين (إن كان مفعّلاً)

SECTIONS = [
    "التوصيات الحالية",
    "أداء الأسبوع الحالي",
    "سجل 4 أسابيع للشهر الحالي",
    "تفاصيل الصفقات",
]

TIMEFRAMES = ["5m", "15m", "30m", "1h"]
MA_TYPES = ["EMA", "SMA"]
PERIODS = {"5m": "30d", "15m": "60d", "30m": "60d", "1h": "180d"}

DEFAULT_CFG = {
    "tf": "15m",
    "ma_type": "EMA",
    "fast": 20,
    "slow": 50,
    "atr_len": 14,
    "atr_mult": 1.5,
    "rr": 2.0,
    "be": False,
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
    .block-container {padding-top: 1rem; padding-left: .8rem; padding-right: .8rem;}
    div[data-baseweb="select"] > div {direction: rtl;}
    [data-testid="stMetric"] {text-align: right;}
    [data-testid="stDataFrame"] {direction: ltr;}
    .net-box {
        text-align: center; border-radius: 18px; padding: 14px 8px 12px 8px;
        margin-bottom: 10px; border: 2px solid;
    }
    .net-label {font-size: 1.05rem; font-weight: 700; opacity: .9; margin-bottom: 2px;}
    .net-value {
        font-size: 3.2rem; font-weight: 900; line-height: 1.15;
        direction: ltr; letter-spacing: 1px;
    }
    .net-sub {font-size: .9rem; opacity: .85; margin-top: 4px;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "cfg" not in st.session_state:
    st.session_state["cfg"] = DEFAULT_CFG.copy()


def sync_cfg():
    """تُستدعى تلقائياً عند أي تعديل في الإعدادات (بدون زر حفظ)."""
    ss = st.session_state
    old = ss["cfg"]
    ss["cfg"] = {
        "tf": ss.get("w_tf", old["tf"]),
        "ma_type": ss.get("w_ma_type", old["ma_type"]),
        "fast": int(ss.get("w_fast", old["fast"])),
        "slow": int(ss.get("w_slow", old["slow"])),
        "atr_len": int(ss.get("w_atr_len", old["atr_len"])),
        "atr_mult": float(ss.get("w_atr_mult", old["atr_mult"])),
        "rr": float(ss.get("w_rr", old["rr"])),
        "be": bool(ss.get("w_be", old["be"])),
    }


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
def moving_average(series: pd.Series, length: int, kind: str) -> pd.Series:
    if kind == "SMA":
        return series.rolling(length).mean()
    return series.ewm(span=length, adjust=False).mean()


def calc_atr(df: pd.DataFrame, length: int) -> pd.Series:
    """ATR بطريقة Wilder."""
    pc = df["Close"].shift(1)
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()


def run_backtest(sym: str, df: pd.DataFrame, cfg: dict) -> list:
    fast_len, slow_len = int(cfg["fast"]), int(cfg["slow"])
    if fast_len >= slow_len:                       # ضمان أن السريع أقصر من البطيء
        fast_len, slow_len = min(fast_len, slow_len), max(fast_len, slow_len) + 1
    atr_len = int(cfg["atr_len"])
    atr_mult = float(cfg["atr_mult"])
    rr = float(cfg["rr"])
    use_be = bool(cfg["be"])

    d = df.copy()
    d["fast"] = moving_average(d["Close"], fast_len, cfg["ma_type"])
    d["slow"] = moving_average(d["Close"], slow_len, cfg["ma_type"])
    d["atr"] = calc_atr(d, atr_len)

    # إشارة الشراء: المتوسط السريع يقطع البطيء صعوداً
    cross_up = (d["fast"] > d["slow"]) & (d["fast"].shift(1) <= d["slow"].shift(1))
    warm = pd.Series(np.arange(len(d)) >= max(slow_len, atr_len) + 1, index=d.index)
    sig = (cross_up & warm).fillna(False).values

    idx = d.index
    o, h, l, c = d["Open"].values, d["High"].values, d["Low"].values, d["Close"].values
    atr = d["atr"].values
    n = len(d)

    trades = []
    i = 0
    while i < n:
        if not sig[i]:
            i += 1
            continue

        entry = c[i]
        risk = atr_mult * atr[i]                   # المخاطرة = ATR × المضاعف
        if not np.isfinite(risk) or risk <= 0 or risk >= entry:
            i += 1
            continue

        sl0 = entry - risk
        tp = entry + rr * risk
        be_trigger = entry + risk                  # 1R
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
            if use_be and (not be_on) and h[j] >= be_trigger:
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


def net_profit_banner(net: float, week_net: float, open_net: float, n_trades: int):
    """عرض الربح الصافي بخط كبير وألوان متغيرة حسب الربح/الخسارة."""
    if net > 0:
        color, bg, icon = "#22c55e", "rgba(34,197,94,0.12)", "▲"
    elif net < 0:
        color, bg, icon = "#ef4444", "rgba(239,68,68,0.12)", "▼"
    else:
        color, bg, icon = "#f59e0b", "rgba(245,158,11,0.12)", "●"

    def c_of(v):
        return "#22c55e" if v > 0 else ("#ef4444" if v < 0 else "#f59e0b")

    st.markdown(
        f"""
        <div class="net-box" style="border-color:{color}; background:{bg};">
            <div class="net-label" style="color:{color};">💰 الربح الصافي - الشهر الحالي</div>
            <div class="net-value" style="color:{color}; text-shadow: 0 0 14px {color}66;">
                {icon} {net:+,.2f} $
            </div>
            <div class="net-sub">
                الأسبوع: <b style="color:{c_of(week_net)}">{week_net:+,.2f} $</b>
                &nbsp;|&nbsp;
                عائم (مفتوحة): <b style="color:{c_of(open_net)}">{open_net:+,.2f} $</b>
                &nbsp;|&nbsp;
                الصفقات: <b>{n_trades}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------
# حساب الصفقات (قبل رسم الواجهة لعرض الربح الصافي في الأعلى)
# ----------------------------------------------------------------------
now = datetime.utcnow()
week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
last_day = calendar.monthrange(now.year, now.month)[1]

with st.spinner("جارٍ تحميل البيانات وتحليل العملات..."):
    trades = compute_trades(cfg["tf"], tuple(sorted(cfg.items())))

# ----------------------------------------------------------------------
# الأعلى: الربح الصافي ثم مربع إظهار/إخفاء الإعدادات
# ----------------------------------------------------------------------
if trades.empty:
    net_profit_banner(0.0, 0.0, 0.0, 0)
else:
    m_tr = trades[trades["وقت الدخول"] >= month_start]
    w_tr = trades[trades["وقت الدخول"] >= week_start]
    net_profit_banner(
        float(m_tr["الربح/الخسارة $"].sum()),
        float(w_tr["الربح/الخسارة $"].sum()),
        float(m_tr[m_tr["الحالة"] == "مفتوحة"]["الربح/الخسارة $"].sum()),
        int(len(m_tr)),
    )

show_settings = st.checkbox("⚙️ إظهار الإعدادات", value=False, key="show_settings")

if show_settings:
    with st.container(border=True):
        st.subheader("⚙️ الإعدادات (تُطبَّق تلقائياً)")

        st.selectbox(
            "الإطار الزمني", TIMEFRAMES, index=TIMEFRAMES.index(cfg["tf"]),
            key="w_tf", on_change=sync_cfg,
        )

        # ---- نافذة المتوسطين ----
        with st.container(border=True):
            st.markdown("**📊 المتوسطان المتحركان**")
            st.selectbox(
                "نوع المتوسط", MA_TYPES, index=MA_TYPES.index(cfg["ma_type"]),
                key="w_ma_type", on_change=sync_cfg,
            )
            st.number_input(
                "المتوسط السريع (MA 1)", min_value=2, max_value=500, value=int(cfg["fast"]),
                step=1, key="w_fast", on_change=sync_cfg,
            )
            st.number_input(
                "المتوسط البطيء (MA 2)", min_value=3, max_value=1000, value=int(cfg["slow"]),
                step=1, key="w_slow", on_change=sync_cfg,
            )
            if int(cfg["fast"]) >= int(cfg["slow"]):
                st.warning("المتوسط السريع يجب أن يكون أقصر من البطيء.")

        # ---- نافذة ATR SL ----
        with st.container(border=True):
            st.markdown("**🛑 ATR SL (وقف الخسارة)**")
            st.number_input(
                "فترة ATR", min_value=1, max_value=200, value=int(cfg["atr_len"]),
                step=1, key="w_atr_len", on_change=sync_cfg,
            )
            st.number_input(
                "مضاعف ATR", min_value=0.1, max_value=20.0, value=float(cfg["atr_mult"]),
                step=0.1, format="%.2f", key="w_atr_mult", on_change=sync_cfg,
            )

        # ---- نافذة العائد R:R ----
        with st.container(border=True):
            st.markdown("**🎯 العائد R:R**")
            st.number_input(
                "R (العائد مقابل 1 مخاطرة)", min_value=0.5, max_value=20.0, value=float(cfg["rr"]),
                step=0.5, format="%.2f", key="w_rr", on_change=sync_cfg,
            )
            st.checkbox(
                "تأمين الصفقة عند 1R (نقل الوقف إلى الدخول +0.1%)", value=bool(cfg["be"]),
                key="w_be", on_change=sync_cfg,
            )

        if st.button("🔄 تحديث البيانات الآن"):
            st.cache_data.clear()
            st.rerun()

st.caption(
    f"Spot - شراء فقط - 22 عملة حلال - الفريم: {cfg['tf']} - "
    f"{cfg['ma_type']} {cfg['fast']}/{cfg['slow']} - ATR {cfg['atr_len']}×{cfg['atr_mult']} - R:R 1:{cfg['rr']:g}"
)

if trades.empty:
    st.warning("لا توجد صفقات أو تعذر تحميل البيانات حالياً. جرّب تحديث البيانات من الإعدادات.")
    st.stop()

section = st.selectbox("القسم", SECTIONS, key="section_nav")

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
                    f"الربح/الخسارة العائمة: {r['الربح/الخسارة $']:+.2f} $"
                    + (" - ✅ التأمين مفعّل" if r["التأمين مفعّل"] else "")
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
    mt = trades[trades["وقت الدخول"] >= month_start]
    if not mt.empty:
        st.markdown("**ملخص الشهر**")
        show_stats(mt)

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
st.caption("⚠️ للأغراض التعليمية فقط وليست نصيحة استثمارية. المحاكاة تفترض الدخول عند إغلاق شمعة التقاطع، "
           "وعند تحقق الوقف والهدف في نفس الشمعة يُفترض الوقف أولاً (تحفظاً).")
