from datetime import datetime
from io import StringIO
from github import Github
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Pure Fibonacci 0.23 Scanner", page_icon="📐", layout="wide"
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


def save_trades(df, sha=None, msg="Update Pure Fib 0.23 trades"):
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


@st.cache_data(ttl=60)
def fetch_1m_data(ticker):
    df_1m = yf.download(
        tickers=ticker, period="5d", interval="1m", progress=False
    )
    if df_1m.empty:
        return pd.DataFrame()
    if isinstance(df_1m.columns, pd.MultiIndex):
        df_1m.columns = df_1m.columns.get_level_values(0)
    return df_1m.copy()


# --- 3. اختبار تاريخي خالص لفيبوناتشي (الدخول عند 0.23 + تأكيد 1m) ---
def run_pure_fib_backtest(
    coins_map, interval, trade_size, fib_entry, fib_sl, fib_tp
):
    total_pnl = 0.0
    wins = 0
    losses = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        df = fetch_data(yf_ticker, interval, period="5d")
        df_1m = fetch_1m_data(yf_ticker)

        if len(df) < 25 or df_1m.empty:
            continue

        in_trade = False
        trade_type = ""
        entry_p = 0.0
        sl_p = 0.0
        tp_p = 0.0
        entry_time = ""

        for i in range(21, len(df)):
            row = df.iloc[i]
            curr_time = df.index[i]

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
                            "النوع": f"شراء (Fib {fib_entry})",
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
                            "النوع": f"شراء (Fib {fib_entry})",
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
                            "النوع": f"بيع (Fib {fib_entry})",
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
                            "النوع": f"بيع (Fib {fib_entry})",
                            "الحالة": "خاسرة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
            else:
                # نافذة آخر 20 شمعة مغلقة لتحديد القمة والقاع واتجاه الموجة
                window = df.iloc[i - 20 : i]
                s_high = float(window["High"].max())
                s_low = float(window["Low"].min())
                fib_range = s_high - s_low
                if fib_range <= 0:
                    continue

                idx_high = window["High"].idxmax()
                idx_low = window["Low"].idxmin()

                sub_1m = df_1m[df_1m.index >= curr_time]
                if sub_1m.empty:
                    continue
                confirm_1m_close = float(sub_1m["Close"].iloc[0])

                # 1. موجة صاعدة (القاع قبل القمة) -> تصحيح عند مستوى 0.23 من القمة
                if idx_low < idx_high:
                    entry_level = s_high - (fib_entry * fib_range)
                    # ملامسة مستوى 0.23 وإغلاق شمعة 1m فوقه
                    if (
                        row["Low"] <= entry_level
                        and confirm_1m_close > entry_level
                    ):
                        target_val = s_low + (fib_tp * fib_range)
                        stop_val = s_low + (fib_sl * fib_range)
                        if confirm_1m_close < target_val:
                            in_trade = True
                            trade_type = "BUY"
                            entry_p = confirm_1m_close
                            sl_p = stop_val
                            tp_p = target_val
                            entry_time = sub_1m.index[0]

                # 2. موجة هابطة (القمة قبل القاع) -> ارتداد عند مستوى 0.23 من القاع
                elif idx_high < idx_low:
                    entry_level = s_low + (fib_entry * fib_range)
                    # ملامسة مستوى 0.23 وإغلاق شمعة 1m تحته
                    if (
                        row["High"] >= entry_level
                        and confirm_1m_close < entry_level
                    ):
                        target_val = s_high - (fib_tp * fib_range)
                        stop_val = s_high - (fib_sl * fib_range)
                        if confirm_1m_close > target_val:
                            in_trade = True
                            trade_type = "SELL"
                            entry_p = confirm_1m_close
                            sl_p = stop_val
                            tp_p = target_val
                            entry_time = sub_1m.index[0]

    return round(total_pnl, 2), wins, losses, pd.DataFrame(history_list)
# --- 5. فحص الإشارات اللحظية لفيبوناتشي 0.23 ---
def scan_pure_fib(
    yf_ticker, display_name, interval, fib_entry, fib_sl, fib_tp
):
    df = fetch_data(yf_ticker, interval, period="5d")
    df_1m = fetch_1m_data(yf_ticker)

    if len(df) < 25 or df_1m.empty:
        return None

    window = df.iloc[-21:-1]
    s_high = float(window["High"].max())
    s_low = float(window["Low"].min())
    fib_range = s_high - s_low

    idx_high = window["High"].idxmax()
    idx_low = window["Low"].idxmin()

    last_candle = df.iloc[-2]
    last_1m_close = float(df_1m["Close"].iloc[-2])
    current_price = float(df["Close"].iloc[-1])

    signal = "انتظار السعر عند 0.23"
    entry_lvl_display = 0.0
    sl_price = 0.0
    tp_price = 0.0

    # موجة صاعدة -> البحث عن شراء عند 0.23
    if idx_low < idx_high and fib_range > 0:
        entry_lvl = s_high - (fib_entry * fib_range)
        entry_lvl_display = entry_lvl
        target_val = s_low + (fib_tp * fib_range)
        stop_val = s_low + (fib_sl * fib_range)
        if (
            last_candle["Low"] <= entry_lvl
            and last_1m_close > entry_lvl
            and last_1m_close < target_val
        ):
            signal = f"شراء مؤكد (BUY {fib_entry})"
            sl_price = stop_val
            tp_price = target_val
        else:
            signal = "موجة صاعدة (مراقبة 0.23)"

    # موجة هابطة -> البحث عن بيع عند 0.23
    elif idx_high < idx_low and fib_range > 0:
        entry_lvl = s_low + (fib_entry * fib_range)
        entry_lvl_display = entry_lvl
        target_val = s_high - (fib_tp * fib_range)
        stop_val = s_high - (fib_sl * fib_range)
        if (
            last_candle["High"] >= entry_lvl
            and last_1m_close < entry_lvl
            and last_1m_close > target_val
        ):
            signal = f"بيع مؤكد (SELL {fib_entry})"
            sl_price = stop_val
            tp_price = target_val
        else:
            signal = "موجة هابطة (مراقبة 0.23)"

    return {
        "العملة": display_name,
        "السعر الحالي": round(current_price, 5),
        f"مستوى الدخول ({fib_entry})": round(entry_lvl_display, 5),
        "الإشارة": signal,
        f"وقف الخسارة ({fib_sl})": round(sl_price, 5) if sl_price > 0 else "-",
        f"الهدف ({fib_tp})": round(tp_price, 5) if tp_price > 0 else "-",
    }


# --- 6. واجهة التطبيق ---
st.title("📐 ماسح الفيبوناتشي الخالص (دخول مستوى 0.23)")
st.caption(
    "بدون متوسطات متحركة | الدخول: ارتداد 0.23 + إغلاق 1m | إدارة الصفقة: مستويات فيبوناتشي"
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

with st.expander("⚙️ ضبط مستويات الفيبوناتشي والفريم ورأس المال", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        selected_tf = st.selectbox(
            "الإطار الزمني الأساسي:", ["5m", "15m", "30m"], index=0
        )
        fib_entry_input = st.number_input(
            "مستوى الدخول (Fib Entry):",
            min_value=0.10,
            max_value=0.786,
            value=0.23,
            step=0.01,
            format="%.2f",
        )
        fib_sl_input = st.number_input(
            "مستوى وقف الخسارة (Fib SL):",
            min_value=-1.00,
            max_value=0.20,
            value=-0.24,
            step=0.01,
            format="%.2f",
        )
    with col2:
        trade_amount = st.number_input(
            "حجم الصفقة بالدولار ($):", min_value=10, value=100, step=10
        )
        fib_tp_input = st.number_input(
            "مستوى الهدف (Fib Target):",
            min_value=0.20,
            max_value=2.00,
            value=0.50,
            step=0.01,
            format="%.2f",
        )

with st.spinner("جاري فحص ارتدادات فيبوناتشي 0.23 على البيانات الحقيقية..."):
    net_pnl, w_count, l_count, bt_df = run_pure_fib_backtest(
        COINS_MAP,
        selected_tf,
        trade_amount,
        fib_entry_input,
        fib_sl_input,
        fib_tp_input,
    )
    total_t = w_count + l_count
    win_rate = round((w_count / total_t) * 100, 1) if total_t > 0 else 0.0

c1, c2, c3 = st.columns(3)
c1.metric(f"الربح الصافي (آخر 5 أيام - {selected_tf})", f"{net_pnl} $")
c2.metric(
    f"نسبة النجاح (Fib {fib_entry_input})",
    f"{win_rate}%",
    f"إجمالي الصفقات: {total_t}",
)
c3.metric("توزيع الصفقات", f"{w_count} ناجحة", f"-{l_count} خاسرة")

st.divider()

if st.button("فحص فرص 0.23 المؤكدة الآن 🔄", use_container_width=True):
    df_history, file_sha = load_trades()
    scan_results = []
    new_added = 0

    for display_name, yf_ticker in COINS_MAP.items():
        res = scan_pure_fib(
            yf_ticker,
            display_name,
            selected_tf,
            fib_entry_input,
            fib_sl_input,
            fib_tp_input,
        )
        if res:
            scan_results.append(res)
            if "مؤكد" in res["الإشارة"]:
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Coin": display_name,
                    "Timeframe": selected_tf,
                    "Type": res["الإشارة"],
                    "Entry_Price": res[f"مستوى الدخول ({fib_entry_input})"],
                    "Stop_Loss": res[f"وقف الخسارة ({fib_sl_input})"],
                    "Take_Profit": res[f"الهدف ({fib_tp_input})"],
                    "Status": "مفتوحة",
                    "PnL": 0.0,
                }])
                df_history = pd.concat(
                    [df_history, new_row], ignore_index=True
                )
                new_added += 1

    if new_added > 0:
        save_trades(
            df_history,
            file_sha,
            f"Add {new_added} Pure-Fib {fib_entry_input} signals",
        )
        st.success(f"تم رصد وحفظ {new_added} فرصة فيبوناتشي مؤكدة في GitHub!")

    st.subheader("الأسعار ومستويات 0.23 اللحظية:")
    st.dataframe(pd.DataFrame(scan_results), use_container_width=True)

if not bt_df.empty:
    st.divider()
    st.subheader(
        f"📋 سجل الصفقات المحسوبة (Entry: {fib_entry_input} | SL: {fib_sl_input} | TP: {fib_tp_input})"
    )
    st.dataframe(
        bt_df.sort_values(by="الوقت", ascending=False), use_container_width=True
    )
