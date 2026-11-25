from datetime import datetime
from io import StringIO
from github import Github
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="AMD + FVG Pro Scanner", page_icon="🎯", layout="wide"
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


def save_trades(df, sha=None, msg="Update Pro AMD-FVG trades"):
    repo = get_github_repo()
    file_path = st.secrets["FILE_PATH"]
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    content = csv_buffer.getvalue()
    if sha:
        repo.update_file(file_path, msg, content, sha)
    else:
        repo.create_file(file_path, msg, content)


# --- 2. جلب البيانات بسرعة فائقة دفعة واحدة ---
@st.cache_data(ttl=120)
def fetch_all_data(tickers_list, interval, period="10d"):
    data = yf.download(
        tickers=tickers_list,
        period=period,
        interval=interval,
        group_by="ticker",
        progress=False,
    )
    return data


# --- 3. حساب المؤشرات ---
def calculate_indicators(df, atr_period=14):
    df = df.dropna().copy()
    if len(df) < 205:
        return pd.DataFrame()
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(atr_period).mean()
    df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df


# --- 4. اختبار تاريخي محسن ---
def run_pro_amd_backtest(
    coins_map, all_data, atr_mult, rr_ratio, use_ema200=True, use_be=True
):
    trade_size = 100.0
    total_pnl = 0.0
    wins = 0
    losses = 0
    breakevens = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        if yf_ticker not in all_data.columns.get_level_values(0):
            continue
        df = calculate_indicators(all_data[yf_ticker])
        if df.empty:
            continue

        start_idx = max(200, len(df) - 480)
        in_trade = False
        trade_type = ""
        entry_p = 0.0
        sl_p = 0.0
        tp_p = 0.0
        be_target = 0.0
        be_secured = False
        entry_time = ""

        fvg_active = False
        fvg_dir = ""
        fvg_top = 0.0
        fvg_bottom = 0.0
        fvg_age = 0

        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            curr_time = df.index[i]
            atr = float(df["ATR"].iloc[i - 1])
            ema200 = float(df["EMA_200"].iloc[i - 1])
            if pd.isna(atr) or atr <= 0:
                continue

            if in_trade:
                if trade_type == "BUY":
                    if use_be and not be_secured and row["High"] >= be_target:
                        sl_p = entry_p
                        be_secured = True
                    if row["High"] >= tp_p:
                        pnl = trade_size * ((tp_p - entry_p) / entry_p)
                        total_pnl += pnl
                        wins += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "شراء (Pro AMD)",
                            "الحالة": "ناجحة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                    elif row["Low"] <= sl_p:
                        pnl = trade_size * ((sl_p - entry_p) / entry_p)
                        total_pnl += pnl
                        if be_secured:
                            breakevens += 1
                            status_lbl = "تعادل (مؤمّنة)"
                        else:
                            losses += 1
                            status_lbl = "خاسرة"
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "شراء (Pro AMD)",
                            "الحالة": status_lbl,
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                elif trade_type == "SELL":
                    if use_be and not be_secured and row["Low"] <= be_target:
                        sl_p = entry_p
                        be_secured = True
                    if row["Low"] <= tp_p:
                        pnl = trade_size * ((entry_p - tp_p) / entry_p)
                        total_pnl += pnl
                        wins += 1
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "بيع (Pro AMD)",
                            "الحالة": "ناجحة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
                    elif row["High"] >= sl_p:
                        pnl = trade_size * ((entry_p - sl_p) / entry_p)
                        total_pnl += pnl
                        if be_secured:
                            breakevens += 1
                            status_lbl = "تعادل (مؤمّنة)"
                        else:
                            losses += 1
                            status_lbl = "خاسرة"
                        in_trade = False
                        history_list.append({
                            "الوقت": str(entry_time)[:16],
                            "العملة": display_name,
                            "النوع": "بيع (Pro AMD)",
                            "الحالة": status_lbl,
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
            else:
                if fvg_active:
                    fvg_age += 1
                    if fvg_age > 10:
                        fvg_active = False
                    elif (
                        fvg_dir == "BUY"
                        and row["Low"] <= fvg_top
                        and row["Close"] > fvg_bottom
                    ):
                        if not use_ema200 or float(row["Close"]) > ema200:
                            in_trade = True
                            trade_type = "BUY"
                            entry_p = float(row["Close"])
                            sl_dist = atr_mult * atr
                            sl_p = entry_p - sl_dist
                            tp_p = entry_p + (sl_dist * rr_ratio)
                            be_target = entry_p + (
                                sl_dist * min(1.5, rr_ratio * 0.5)
                            )
                            be_secured = False
                            entry_time = curr_time
                        fvg_active = False
                        continue
                    elif (
                        fvg_dir == "SELL"
                        and row["High"] >= fvg_bottom
                        and row["Close"] < fvg_top
                    ):
                        if not use_ema200 or float(row["Close"]) < ema200:
                            in_trade = True
                            trade_type = "SELL"
                            entry_p = float(row["Close"])
                            sl_dist = atr_mult * atr
                            sl_p = entry_p + sl_dist
                            tp_p = entry_p - (sl_dist * rr_ratio)
                            be_target = entry_p - (
                                sl_dist * min(1.5, rr_ratio * 0.5)
                            )
                            be_secured = False
                            entry_time = curr_time
                        fvg_active = False
                        continue

                acc_window = df.iloc[i - 16 : i - 4]
                acc_high = float(acc_window["High"].max())
                acc_low = float(acc_window["Low"].min())
                c1 = df.iloc[i - 3]
                c2 = df.iloc[i - 2]
                c3 = df.iloc[i - 1]

                manip_low = min(float(c1["Low"]), float(c2["Low"]))
                gap_buy = float(c3["Low"]) - float(c1["High"])
                if manip_low < acc_low and gap_buy > (0.25 * atr):
                    fvg_active = True
                    fvg_dir = "BUY"
                    fvg_top = float(c3["Low"])
                    fvg_bottom = float(c1["High"])
                    fvg_age = 0

                manip_high = max(float(c1["High"]), float(c2["High"]))
                gap_sell = float(c1["Low"]) - float(c3["High"])
                if manip_high > acc_high and gap_sell > (0.25 * atr):
                    fvg_active = True
                    fvg_dir = "SELL"
                    fvg_top = float(c1["Low"])
                    fvg_bottom = float(c3["High"])
                    fvg_age = 0

    return (
        round(total_pnl, 2),
        wins,
        losses,
        breakevens,
        pd.DataFrame(history_list),
    )
# --- 5. فحص الإشارات اللحظية ---
def scan_pro_amd_live(
    yf_ticker, display_name, all_data, atr_mult, rr_ratio, use_ema200
):
    if yf_ticker not in all_data.columns.get_level_values(0):
        return None
    df = calculate_indicators(all_data[yf_ticker])
    if df.empty:
        return None

    atr = float(df["ATR"].iloc[-2])
    ema200 = float(df["EMA_200"].iloc[-2])
    current_price = float(df["Close"].iloc[-1])
    trend_lbl = "صاعد 🟢" if current_price > ema200 else "هابط 🔴"

    acc_window = df.iloc[-17:-5]
    acc_high = float(acc_window["High"].max())
    acc_low = float(acc_window["Low"].min())
    c1 = df.iloc[-4]
    c2 = df.iloc[-3]
    c3 = df.iloc[-2]
    last_candle = df.iloc[-1]

    signal = "مراقبة التجميع"
    fvg_zone = "-"
    sl_price = 0.0
    tp_price = 0.0

    manip_low = min(float(c1["Low"]), float(c2["Low"]))
    gap_buy = float(c3["Low"]) - float(c1["High"])
    if manip_low < acc_low and gap_buy > (0.25 * atr):
        fvg_top = float(c3["Low"])
        fvg_bottom = float(c1["High"])
        fvg_zone = f"{round(fvg_bottom, 5)} - {round(fvg_top, 5)}"
        if float(last_candle["Low"]) <= fvg_top and current_price > fvg_bottom:
            if not use_ema200 or current_price > ema200:
                signal = "شراء مؤكد (Pro AMD)"
                sl_dist = atr_mult * atr
                sl_price = current_price - sl_dist
                tp_price = current_price + (sl_dist * rr_ratio)
            else:
                signal = "شراء مرفوض (عكس EMA 200)"
        else:
            signal = "تلاعب شراء + FVG قوي (انتظار)"

    manip_high = max(float(c1["High"]), float(c2["High"]))
    gap_sell = float(c1["Low"]) - float(c3["High"])
    if manip_high > acc_high and gap_sell > (0.25 * atr):
        fvg_top = float(c1["Low"])
        fvg_bottom = float(c3["High"])
        fvg_zone = f"{round(fvg_bottom, 5)} - {round(fvg_top, 5)}"
        if float(last_candle["High"]) >= fvg_bottom and current_price < fvg_top:
            if not use_ema200 or current_price < ema200:
                signal = "بيع مؤكد (Pro AMD)"
                sl_dist = atr_mult * atr
                sl_price = current_price + sl_dist
                tp_price = current_price - (sl_dist * rr_ratio)
            else:
                signal = "بيع مرفوض (عكس EMA 200)"
        else:
            signal = "تلاعب بيع + FVG قوي (انتظار)"

    return {
        "العملة": display_name,
        "الاتجاه (EMA 200)": trend_lbl,
        "السعر الحالي": round(current_price, 5),
        "منطقة FVG": fvg_zone,
        "الإشارة": signal,
        f"الوقف ({atr_mult} ATR)": round(sl_price, 5) if sl_price > 0 else "-",
        f"الهدف ({rr_ratio} R:R)": round(tp_price, 5) if tp_price > 0 else "-",
    }


# --- 6. واجهة التطبيق ---
st.title("🎯 ماسح Smart Money المطور (AMD + FVG Pro)")

COINS_MAP = {
    "XLMUSDT": "XLM-USD",
    "ZECUSDT": "ZEC-USD",
    "XRPUSDT": "XRP-USD",
    "HBARUSDT": "HBAR-USD",
    "ADAUSDT": "ADA-USD",
    "LTCUSDT": "LTC-USD",
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "NEARUSDT": "NEAR-USD",
    "LINKUSDT": "LINK-USD",
}

with st.expander("⚙️ ضبط الفريم ووقف الخسارة والعائد والفلاتر", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_tf = st.selectbox(
            "الإطار الزمني:", ["5m", "15m", "30m"], index=1
        )
    with col2:
        atr_sl_input = st.number_input(
            "وقف الخسارة (ATR SL):",
            min_value=0.5,
            max_value=5.0,
            value=2.5,
            step=0.1,
            format="%.1f",
        )
    with col3:
        rr_input = st.number_input(
            "نسبة العائد (R:R):",
            min_value=0.5,
            max_value=5.0,
            value=3.1,
            step=0.1,
            format="%.1f",
        )

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        use_ema200_chk = st.checkbox(
            "تفعيل فلتر الاتجاه العام (EMA 200)", value=True
        )
    with f_col2:
        use_be_chk = st.checkbox(
            "تأمين الصفقة عند 1.5 R:R (Break-Even)", value=True
        )

with st.spinner("جاري تحميل البيانات وحساب النتائج بسرعة..."):
    all_market_data = fetch_all_data(
        list(COINS_MAP.values()), selected_tf, period="10d"
    )
    net_pnl, w_count, l_count, be_count, bt_df = run_pro_amd_backtest(
        COINS_MAP,
        all_market_data,
        atr_sl_input,
        rr_input,
        use_ema200_chk,
        use_be_chk,
    )
    total_t = w_count + l_count + be_count
    win_rate = round((w_count / total_t) * 100, 1) if total_t > 0 else 0.0

c1, c2, c3 = st.columns(3)
c1.metric(f"الربح الصافي (آخر 5 أيام - {selected_tf})", f"{net_pnl} $")
c2.metric("نسبة النجاح (Pro AMD)", f"{win_rate}%", f"إجمالي الصفقات: {total_t}")
c3.metric(
    "توزيع الصفقات",
    f"{w_count} ناجحة | {be_count} تعادل",
    f"-{l_count} خاسرة",
)

st.divider()

if st.button("فحص الفرص اللحظية الآن 🔄", use_container_width=True):
    df_history, file_sha = load_trades()
    scan_results = []
    new_added = 0

    for display_name, yf_ticker in COINS_MAP.items():
        res = scan_pro_amd_live(
            yf_ticker,
            display_name,
            all_market_data,
            atr_sl_input,
            rr_input,
            use_ema200_chk,
        )
        if res:
            scan_results.append(res)
            if "مؤكد" in res["الإشارة"]:
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Coin": display_name,
                    "Timeframe": selected_tf,
                    "Type": res["الإشارة"],
                    "Entry_Price": res["السعر الحالي"],
                    "Stop_Loss": res[f"الوقف ({atr_sl_input} ATR)"],
                    "Take_Profit": res[f"الهدف ({rr_input} R:R)"],
                    "Status": "مفتوحة",
                    "PnL": 0.0,
                }])
                df_history = pd.concat(
                    [df_history, new_row], ignore_index=True
                )
                new_added += 1

    if new_added > 0:
        save_trades(df_history, file_sha, f"Add {new_added} Pro-AMD signals")
        st.success(f"تم رصد وحفظ {new_added} فرصة مؤكدة في GitHub!")

    st.subheader("حالة العملات الـ 12 ومناطق FVG اللحظية:")
    st.dataframe(pd.DataFrame(scan_results), use_container_width=True)

if not bt_df.empty:
    st.divider()
    st.subheader(
        f"📋 سجل الصفقات المحسوبة (SL: {atr_sl_input} ATR | R:R: 1:{rr_input})"
    )
    st.dataframe(
        bt_df.sort_values(by="الوقت", ascending=False), use_container_width=True
    )
