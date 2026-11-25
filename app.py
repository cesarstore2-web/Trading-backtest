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


@st.cache_data(ttl=60)
def fetch_data(ticker, interval):
    df = yf.download(
        tickers=ticker, period="5d", interval=interval, progress=False
    )
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.tail(100).copy()


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


def scan_coin(yf_ticker, display_name, interval):
    df = fetch_data(yf_ticker, interval)
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
        "EMA 2": round(curr_ema, 5),
        "WMA 20": round(curr_wma, 5),
        "الإشارة": signal,
        "وقف الخسارة (2.3 ATR)": round(sl_price, 5) if sl_price > 0 else "-",
        "الهدف (0.9 R:R)": round(tp_price, 5) if tp_price > 0 else "-",
    }


def update_open_trades(df_trades, coins_map):
    if df_trades.empty:
        return df_trades, False
    updated = False
    trade_size = 100.0
    for idx, row in df_trades.iterrows():
        if row["Status"] == "مفتوحة":
            yf_ticker = coins_map.get(row["Coin"])
            if not yf_ticker:
                continue
            df_live = fetch_data(yf_ticker, row["Timeframe"])
            if df_live.empty:
                continue
            last_high = float(df_live["High"].iloc[-1])
            last_low = float(df_live["Low"].iloc[-1])
            entry = float(row["Entry_Price"])
            sl = float(row["Stop_Loss"])
            tp = float(row["Take_Profit"])
            if "BUY" in row["Type"]:
                if last_high >= tp:
                    df_trades.at[idx, "Status"] = "ناجحة"
                    pnl_pct = (tp - entry) / entry
                    df_trades.at[idx, "PnL"] = round(trade_size * pnl_pct, 2)
                    updated = True
                elif last_low <= sl:
                    df_trades.at[idx, "Status"] = "خاسرة"
                    pnl_pct = (sl - entry) / entry
                    df_trades.at[idx, "PnL"] = round(trade_size * pnl_pct, 2)
                    updated = True
            elif "SELL" in row["Type"]:
                if last_low <= tp:
                    df_trades.at[idx, "Status"] = "ناجحة"
                    pnl_pct = (entry - tp) / entry
                    df_trades.at[idx, "PnL"] = round(trade_size * pnl_pct, 2)
                    updated = True
                elif last_high >= sl:
                    df_trades.at[idx, "Status"] = "خاسرة"
                    pnl_pct = (entry - sl) / entry
                    df_trades.at[idx, "PnL"] = round(trade_size * pnl_pct, 2)
                    updated = True
    return df_trades, updated


st.title("📊 ماسح تقاطع EMA 2 × WMA 20 (بيانات حقيقية)")
st.caption(
    "الإعدادات: تقاطع EMA 2 مع WMA 20 | وقف الخسارة: 2.30 ATR | الهدف: 0.9 R:R"
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

selected_tf = st.selectbox("اختر الإطار الزمني:", ["5m", "15m", "30m"], index=2)

df_history, file_sha = load_trades()
df_history, was_updated = update_open_trades(df_history, COINS_MAP)
if was_updated:
    save_trades(df_history, file_sha, "Auto-update closed trades status")
    df_history, file_sha = load_trades()

if not df_history.empty:
    df_history["Date_dt"] = pd.to_datetime(df_history["Date"])
    now = datetime.now()

    def calc_stats(days_count):
        sub = df_history[
            (df_history["Date_dt"] >= now - timedelta(days=days_count))
            & (df_history["Status"].isin(["ناجحة", "خاسرة"]))
        ]
        wins = len(sub[sub["Status"] == "ناجحة"])
        losses = len(sub[sub["Status"] == "خاسرة"])
        total = wins + losses
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0
        net_pnl = round(sub["PnL"].sum(), 2)
        return wins, losses, win_rate, net_pnl

    col1, col2, col3 = st.columns(3)
    stats_config = [
        (col1, "أداء 1 يوم", 1),
        (col2, "أداء 1 أسبوع", 7),
        (col3, "أداء 1 شهر", 30),
    ]
    for col, title, days_val in stats_config:
        w, l, wr, pnl = calc_stats(days_val)
        with col:
            st.metric(
                label=f"{title} ({selected_tf})",
                value=f"{pnl} $",
                delta=f"نسبة النجاح: {wr}% (ناجحة: {w} | خاسرة: {l})",
            )

st.divider()

if st.button("فحص العملات الآن 🔄", use_container_width=True):
    scan_results = []
    new_trades_added = 0
    with st.spinner(
        f"جاري فحص العملات الـ 9 على فريم {selected_tf} من Yahoo Finance..."
    ):
        for display_name, yf_ticker in COINS_MAP.items():
            res = scan_coin(yf_ticker, display_name, selected_tf)
            if res:
                scan_results.append(res)
                if "BUY" in res["الإشارة"] or "SELL" in res["الإشارة"]:
                    already_open = False
                    if not df_history.empty:
                        open_same = df_history[
                            (df_history["Coin"] == display_name)
                            & (df_history["Timeframe"] == selected_tf)
                            & (df_history["Status"] == "مفتوحة")
                        ]
                        if not open_same.empty:
                            already_open = True
                    if not already_open:
                        new_row = pd.DataFrame([{
                            "Date": datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "Coin": display_name,
                            "Timeframe": selected_tf,
                            "Type": res["الإشارة"],
                            "Entry_Price": res["السعر الحالي"],
                            "Stop_Loss": res["وقف الخسارة (2.3 ATR)"],
                            "Take_Profit": res["الهدف (0.9 R:R)"],
                            "Status": "مفتوحة",
                            "PnL": 0.0,
                        }])
                        df_history = pd.concat(
                            [df_history, new_row], ignore_index=True
                        )
                        new_trades_added += 1
    if new_trades_added > 0:
        save_trades(
            df_history,
            file_sha,
            f"Add {new_trades_added} new signals on {selected_tf}",
        )
        st.success(f"تم رصد وحفظ {new_trades_added} صفقة جديدة في GitHub!")
    st.subheader(f"نتائج الفحص المباشر ({selected_tf})")
    st.dataframe(pd.DataFrame(scan_results), use_container_width=True)

st.divider()
st.subheader("📑 سجل الصفقات المحفوظ في GitHub")
if not df_history.empty:
    display_df = df_history.drop(columns=["Date_dt"], errors="ignore")
    st.dataframe(
        display_df.sort_values(by="Date", ascending=False),
        use_container_width=True,
    )
else:
    st.info("لا توجد صفقات مسجلة حتى الآن. اضغط على 'فحص العملات الآن' للبدء.")
