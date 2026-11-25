from datetime import datetime, timedelta
from io import StringIO
from github import Github
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="EMA2 x WMA20 Scanner", page_icon="📈", layout="wide"
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


def save_trades(df, sha=None, msg="Update trades"):
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


# --- 3. حساب المؤشرات ---
def calculate_indicators(df):
    df["EMA_2"] = df["Close"].ewm(span=2, adjust=False).mean()
    weights = np.arange(1, 21)
    df["WMA_20"] = (
        df["Close"]
        .rolling(20)
        .apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)
    )
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    return df


# --- 4. اختبار تاريخي حقيقي (Backtest) لآخر 5 أيام لحساب الربح الصافي بالدولار ---
def run_real_backtest(coins_map, interval, trade_size=100.0):
    total_pnl = 0.0
    wins = 0
    losses = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        df = fetch_data(yf_ticker, interval, period="5d")
        if len(df) < 30:
            continue
        df = calculate_indicators(df)

        in_trade = False
        trade_type = ""
        entry_p = 0.0
        sl_p = 0.0
        tp_p = 0.0
        entry_time = ""

        for i in range(21, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]

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
                            "النوع": "شراء",
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
                            "النوع": "شراء",
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
                            "النوع": "بيع",
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
                            "النوع": "بيع",
                            "الحالة": "خاسرة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
            else:
                atr = prev["ATR"]
                if pd.isna(atr) or atr == 0:
                    continue
                sl_dist = 2.30 * atr
                tp_dist = sl_dist * 0.9

                if (
                    prev["EMA_2"] <= prev["WMA_20"]
                    and row["EMA_2"] > row["WMA_20"]
                ):
                    in_trade = True
                    trade_type = "BUY"
                    entry_p = float(row["Close"])
                    sl_p = entry_p - sl_dist
                    tp_p = entry_p + tp_dist
                    entry_time = df.index[i]
                elif (
                    prev["EMA_2"] >= prev["WMA_20"]
                    and row["EMA_2"] < row["WMA_20"]
                ):
                    in_trade = True
                    trade_type = "SELL"
                    entry_p = float(row["Close"])
                    sl_p = entry_p + sl_dist
                    tp_p = entry_p - tp_dist
                    entry_time = df.index[i]

    return round(total_pnl, 2), wins, losses, pd.DataFrame(history_list)


# --- 5. فحص الإشارات اللحظية ---
def scan_coin(yf_ticker, display_name, interval):
    df = fetch_data(yf_ticker, interval, period="5d")
    if len(df) < 25:
        return None
    df = calculate_indicators(df)
    prev_ema = df["EMA_2"].iloc[-3]
    prev_wma = df["WMA_20"].iloc[-3]
    curr_ema = df["EMA_2"].iloc[-2]
    curr_wma = df["WMA_20"].iloc[-2]
    current_price = float(df["Close"].iloc[-1])
    atr = float(df["ATR"].iloc[-2])
    sl_dist = 2.30 * atr
    tp_dist = sl_dist * 0.9
    signal = "لا يوجد تقاطع"
    sl_price = 0.0
    tp_price = 0.0
    if prev_ema <= prev_wma and curr_ema > curr_wma:
        signal = "شراء (BUY)"
        sl_price = current_price - sl_dist
        tp_price = current_price + tp_dist
    elif prev_ema >= prev_wma and curr_ema < curr_wma:
        signal = "بيع (SELL)"
        sl_price = current_price + sl_dist
        tp_price = current_price - tp_dist
    return {
        "العملة": display_name,
        "السعر الحالي": round(current_price, 5),
        "الإشارة": signal,
        "وقف الخسارة": round(sl_price, 5) if sl_price > 0 else "-",
        "الهدف": round(tp_price, 5) if tp_price > 0 else "-",
    }


# --- 6. واجهة التطبيق ---
st.title("📊 ماسح تقاطع EMA 2 × WMA 20")
st.caption(
    "حجم الصفقة الافتراضي: 100$ | وقف الخسارة: 2.30 ATR | الهدف: 0.9 R:R"
)

COINS_MAP = {
    "XRPUSDT": "XRP-USD",
    "XLMUSDT": "XLM-USD",
    "ZECUSDT": "ZEC-USD",
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "ADAUSDT": "ADA-USD",
    "LTCUSDT": "LTC-USD",
    "HBARUSDT": "HBAR-USD",
    "PAXGUSDT": "PAXG-USD",
}

col_tf, col_cap = st.columns(2)
with col_tf:
    selected_tf = st.selectbox(
        "اختر الإطار الزمني:", ["5m", "15m", "30m"], index=1
    )
with col_cap:
    trade_amount = st.number_input(
        "حجم الصفقة بالدولار ($):", min_value=10, value=100, step=10
    )

# --- حساب وعرض الربح الصافي الحقيقي لآخر 5 أيام فوراً ---
with st.spinner("جاري حساب الربح الصافي الحقيقي من بيانات السوق..."):
    net_pnl, w_count, l_count, bt_df = run_real_backtest(
        COINS_MAP, selected_tf, trade_amount
    )
    total_t = w_count + l_count
    win_rate = round((w_count / total_t) * 100, 1) if total_t > 0 else 0.0

c1, c2, c3 = st.columns(3)
c1.metric(f"الربح الصافي (آخر 5 أيام - {selected_tf})", f"{net_pnl} $")
c2.metric("نسبة النجاح الحقيقية", f"{win_rate}%", f"إجمالي الصفقات: {total_t}")
c3.metric("توزيع الصفقات", f"{w_count} ناجحة", f"-{l_count} خاسرة")

st.divider()

# --- زر الفحص اللحظي والحفظ في GitHub ---
if st.button("فحص الفرص اللحظية الآن 🔄", use_container_width=True):
    df_history, file_sha = load_trades()
    scan_results = []
    new_added = 0

    for display_name, yf_ticker in COINS_MAP.items():
        res = scan_coin(yf_ticker, display_name, selected_tf)
        if res:
            scan_results.append(res)
            if "BUY" in res["الإشارة"] or "SELL" in res["الإشارة"]:
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Coin": display_name,
                    "Timeframe": selected_tf,
                    "Type": res["الإشارة"],
                    "Entry_Price": res["السعر الحالي"],
                    "Stop_Loss": res["وقف الخسارة"],
                    "Take_Profit": res["الهدف"],
                    "Status": "مفتوحة",
                    "PnL": 0.0,
                }])
                df_history = pd.concat(
                    [df_history, new_row], ignore_index=True
                )
                new_added += 1

