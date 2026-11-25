from datetime import datetime
from io import StringIO
from github import Github
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="AMD + FVG Smart Money Scanner", page_icon="🎯", layout="wide"
)


# --- 1. دوال الاتصال بـ GitHub ---
def get_github_repo():
    g = Github(st.secrets["GITHUB_TOKEN"])
    return g.get_repo(st.secrets["REPO_NAME"])


def load_trades():
    repo = get_github_repo()
    file_path = st.secrets["FILE_PATH"]
    try:
        file_content = repo.get_contents(file_path)
        csv_data = file_content.decoded_content.decode("utf-8")
        return pd.read_csv(StringIO(csv_data)), file_content.sha
    except Exception:
        columns = [
            "Date",
            "Coin",
            "Timeframe",
            "Type",
            "Entry_Price",
            "Stop_Loss",
            "Take_Profit",
            "Status",
            "PnL",
        ]
        return pd.DataFrame(columns=columns), None


def save_trades(df, sha=None, msg="Update AMD-FVG trades"):
    repo = get_github_repo()
    file_path = st.secrets["FILE_PATH"]
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    content = csv_buffer.getvalue()
    if sha:
        repo.update_file(file_path, msg, content, sha)
    else:
        repo.create_file(file_path, msg, content)


# --- 2. جلب البيانات الحقيقية ---
@st.cache_data(ttl=60)
def fetch_data(ticker, interval, period="5d"):
    df = yf.download(
        tickers=ticker, period=period, interval=interval, progress=False
    )
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.copy()


# --- 3. حساب مؤشر ATR ---
def calculate_atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(period).mean()
    return df


# --- 4. اختبار تاريخي لنموذج AMD (تجميع + تلاعب + FVG) برأس مال 100$ ثابت ---
def run_amd_fvg_backtest(coins_map, interval, atr_mult, rr_ratio):
    trade_size = 100.0  # 100 دولار لكل صفقة في الخفاء
    total_pnl = 0.0
    wins = 0
    losses = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        df = fetch_data(yf_ticker, interval, period="5d")
        if len(df) < 35:
            continue

        df = calculate_atr(df)

        in_trade = False
        trade_type = ""
        entry_p = 0.0
        sl_p = 0.0
        tp_p = 0.0
        entry_time = ""

        # متغيرات تتبع نموذج AMD و FVG
        fvg_active = False
        fvg_dir = ""
        fvg_top = 0.0
        fvg_bottom = 0.0
        fvg_age = 0

        for i in range(20, len(df)):
            row = df.iloc[i]
            curr_time = df.index[i]
            atr = float(df["ATR"].iloc[i - 1])
            if pd.isna(atr) or atr <= 0:
                continue

            if in_trade:
                if trade_type == "BUY":
                    if row["High"] >= tp_p:
                        pnl = trade_size * ((tp_p - entry_p) / entry_p)
                        total_pnl += pnl
                        wins += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "شراء (AMD + FVG)",
                            "الحالة": "ناجحة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                    elif row["Low"] <= sl_p:
                        pnl = trade_size * ((sl_p - entry_p) / entry_p)
                        total_pnl += pnl
                        losses += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "شراء (AMD + FVG)",
                            "الحالة": "خاسرة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                elif trade_type == "SELL":
                    if row["Low"] <= tp_p:
                        pnl = trade_size * ((entry_p - tp_p) / entry_p)
                        total_pnl += pnl
                        wins += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "بيع (AMD + FVG)",
                            "الحالة": "ناجحة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                    elif row["High"] >= sl_p:
                        pnl = trade_size * ((entry_p - sl_p) / entry_p)
                        total_pnl += pnl
                        losses += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "بيع (AMD + FVG)",
                            "الحالة": "خاسرة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
            else:
                # 1. التحقق من دخول صفقة عند إعادة اختبار منطقة FVG النشطة
                if fvg_active:
                    fvg_age += 1
                    if fvg_age > 10:  # انتهاء صلاحية الفجوة إذا لم يختبرها السعر خلال 10 شموع
                        fvg_active = False
                    elif (
                        fvg_dir == "BUY"
                        and row["Low"] <= fvg_top
                        and row["Close"] > fvg_bottom
                    ):
                        in_trade = True
                        trade_type = "BUY"
                        entry_p = float(row["Close"])
                        sl_dist = atr_mult * atr
                        sl_p = entry_p - sl_dist
                        tp_p = entry_p + (sl_dist * rr_ratio)
                        entry_time = curr_time
                        fvg_active = False
                        continue
                    elif (
                        fvg_dir == "SELL"
                        and row["High"] >= fvg_bottom
                        and row["Close"] < fvg_top
                    ):
                        in_trade = True
                        trade_type = "SELL"
                        entry_p = float(row["Close"])
                        sl_dist = atr_mult * atr
                        sl_p = entry_p + sl_dist
                        tp_p = entry_p - (sl_dist * rr_ratio)
                        entry_time = curr_time
                        fvg_active = False
                        continue

                # 2. البحث عن نموذج التجميع (Accumulation) -> التلاعب (Manipulation) -> الفجوة (FVG)
                # نافذة التجميع (12 شمعة قبل حركة التلاعب والاندفاع)
                acc_window = df.iloc[i - 16 : i - 4]
                acc_high = float(acc_window["High"].max())
                acc_low = float(acc_window["Low"].min())

                # الشموع الثلاث الأخيرة لتشكيل التلاعب وفجوة FVG
                c1 = df.iloc[i - 3]
                c2 = df.iloc[i - 2]
                c3 = df.iloc[i - 1]

                # سيناريو الشراء (الصورة الأولى): كسر قاع التجميع ثم فجوة FVG صاعدة
                manip_low = min(float(c1["Low"]), float(c2["Low"]))
                if manip_low < acc_low and float(c3["Low"]) > float(c1["High"]):
                    fvg_active = True
                    fvg_dir = "BUY"
                    fvg_top = float(c3["Low"])
                    fvg_bottom = float(c1["High"])
                    fvg_age = 0

                # سيناريو البيع (الصورة الثانية): كسر قمة التجميع ثم فجوة FVG هابطة
                manip_high = max(float(c1["High"]), float(c2["High"]))
                if manip_high > acc_high and float(c3["High"]) < float(
                    c1["Low"]
                ):
                    fvg_active = True
                    fvg_dir = "SELL"
                    fvg_top = float(c1["Low"])
                    fvg_bottom = float(c3["High"])
                    fvg_age = 0

    return round(total_pnl, 2), wins, losses, pd.DataFrame(history_list)
# --- 5. فحص الإشارات اللحظية لنموذج AMD + FVG ---
def scan_amd_fvg_live(yf_ticker, display_name, interval, atr_mult, rr_ratio):
    df = fetch_data(yf_ticker, interval, period="5d")
    if len(df) < 25:
        return None

    df = calculate_atr(df)
    atr = float(df["ATR"].iloc[-2])
    current_price = float(df["Close"].iloc[-1])

    # فحص آخر 16 شمعة للبحث عن تجميع وتلاعب وفجوة FVG حديثة
    acc_window = df.iloc[-17:-5]
    acc_high = float(acc_window["High"].max())
    acc_low = float(acc_window["Low"].min())

    c1 = df.iloc[-4]
    c2 = df.iloc[-3]
    c3 = df.iloc[-2]
    last_candle = df.iloc[-1]

    signal = "مراقبة التجميع (Accumulation)"
    fvg_zone = "-"
    sl_price = 0.0
    tp_price = 0.0

    # فحص نموذج الشراء (كسر قاع التجميع + FVG صاعد + إعادة اختبار)
    manip_low = min(float(c1["Low"]), float(c2["Low"]))
    if manip_low < acc_low and float(c3["Low"]) > float(c1["High"]):
        fvg_top = float(c3["Low"])
        fvg_bottom = float(c1["High"])
        fvg_zone = f"{round(fvg_bottom, 5)} - {round(fvg_top, 5)}"
        if float(last_candle["Low"]) <= fvg_top and current_price > fvg_bottom:
            signal = "شراء مؤكد (AMD + FVG)"
            sl_dist = atr_mult * atr
            sl_price = current_price - sl_dist
            tp_price = current_price + (sl_dist * rr_ratio)
        else:
            signal = "تلاعب شراء + FVG (بانتظار إعادة الاختبار)"

    # فحص نموذج البيع (كسر قمة التجميع + FVG هابط + إعادة اختبار)
    manip_high = max(float(c1["High"]), float(c2["High"]))
    if manip_high > acc_high and float(c3["High"]) < float(c1["Low"]):
        fvg_top = float(c1["Low"])
        fvg_bottom = float(c3["High"])
        fvg_zone = f"{round(fvg_bottom, 5)} - {round(fvg_top, 5)}"
        if float(last_candle["High"]) >= fvg_bottom and current_price < fvg_top:
            signal = "بيع مؤكد (AMD + FVG)"
            sl_dist = atr_mult * atr
            sl_price = current_price + sl_dist
            tp_price = current_price - (sl_dist * rr_ratio)
        else:
            signal = "تلاعب بيع + FVG (بانتظار إعادة الاختبار)"

    return {
        "العملة": display_name,
        "السعر الحالي": round(current_price, 5),
        "منطقة FVG": fvg_zone,
        "الحالة / الإشارة": signal,
        f"وقف الخسارة ({atr_mult} ATR)": (
            round(sl_price, 5) if sl_price > 0 else "-"
        ),
        f"الهدف ({rr_ratio} R:R)": round(tp_price, 5) if tp_price > 0 else "-",
    }


# --- 6. واجهة التطبيق ---
st.title("🎯 ماسح Smart Money (نموذج AMD + FVG)")
st.caption(
    "التجميع (Accumulation) ➔ التلاعب (Manipulation) ➔ الدخول من الفجوة (FVG) نحو التوزيع (Distribution)"
)

COINS_MAP = {
    "XLMUSDT": "XLM-USD",
    "ZECUSDT": "ZEC-USD",
    "XRPUSDT": "XRP-USD",
    "HBARUSDT": "HBAR-USD",
    "ADAUSDT": "ADA-USD",
    "LTCUSDT": "LTC-USD",
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "PAXGUSDT": "PAXG-USD",
}

# --- لوحة التحكم المباشرة (الفريم + ATR SL + العائد R:R) ---
with st.expander("⚙️ ضبط الإطار الزمني ووقف الخسارة والعائد", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_tf = st.selectbox(
            "الإطار الزمني:", ["5m", "15m", "30m"], index=1
        )
    with col2:
        atr_sl_input = st.number_input(
            "معامل وقف الخسارة (ATR SL):",
            min_value=0.5,
            max_value=5.0,
            value=1.5,
            step=0.1,
            format="%.1f",
        )
    with col3:
        rr_input = st.number_input(
            "نسبة العائد للمخاطرة (R:R):",
            min_value=0.5,
            max_value=5.0,
            value=2.0,
            step=0.1,
            format="%.1f",
        )

with st.spinner("جاري مسح نماذج التجميع والتلاعب وفجوات FVG..."):
    net_pnl, w_count, l_count, bt_df = run_amd_fvg_backtest(
        COINS_MAP, selected_tf, atr_sl_input, rr_input
    )
    total_t = w_count + l_count
    win_rate = round((w_count / total_t) * 100, 1) if total_t > 0 else 0.0

c1, c2, c3 = st.columns(3)
c1.metric(f"الربح الصافي (آخر 5 أيام - {selected_tf})", f"{net_pnl} $")
c2.metric("نسبة النجاح (AMD + FVG)", f"{win_rate}%", f"إجمالي الصفقات: {total_t}")
c3.metric("توزيع الصفقات", f"{w_count} ناجحة", f"-{l_count} خاسرة")

st.divider()

if st.button("فحص نماذج AMD + FVG اللحظية 🔄", use_container_width=True):
    df_history, file_sha = load_trades()
    scan_results = []
    new_added = 0

    for display_name, yf_ticker in COINS_MAP.items():
        res = scan_amd_fvg_live(
            yf_ticker, display_name, selected_tf, atr_sl_input, rr_input
        )
        if res:
            scan_results.append(res)
            if "مؤكد" in res["الحالة / الإشارة"]:
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Coin": display_name,
                    "Timeframe": selected_tf,
                    "Type": res["الحالة / الإشارة"],
                    "Entry_Price": res["السعر الحالي"],
                    "Stop_Loss": res[f"وقف الخسارة ({atr_sl_input} ATR)"],
                    "Take_Profit": res[f"الهدف ({rr_input} R:R)"],
                    "Status": "مفتوحة",
                    "PnL": 0.0,
                }])
                df_history = pd.concat(
                    [df_history, new_row], ignore_index=True
                )
                new_added += 1

    if new_added > 0:
        save_trades(df_history, file_sha, f"Add {new_added} AMD-FVG signals")
        st.success(f"تم رصد وحفظ {new_added} فرصة AMD + FVG مؤكدة في GitHub!")

    st.subheader("حالة العملات ومناطق FVG اللحظية:")
    st.dataframe(pd.DataFrame(scan_results), use_container_width=True)

if not bt_df.empty:
    st.divider()
    st.subheader(
        f"📋 سجل صفقات AMD + FVG المحسوبة (SL: {atr_sl_input} ATR | R:R: 1:{rr_input})"
    )
    st.dataframe(
        bt_df.sort_values(by="الوقت", ascending=False), use_container_width=True
    )
