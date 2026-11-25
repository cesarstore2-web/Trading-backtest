from datetime import datetime
from io import StringIO
from github import Github
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="EMA2 x WMA20 + Optimized Fib", page_icon="📈", layout="wide"
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


def save_trades(df, sha=None, msg="Update Optimized Fib trades"):
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


# --- 3. حساب المؤشرات ومستويات فيبوناتشي ---
def calculate_indicators(df):
    df["EMA_2"] = df["Close"].ewm(span=2, adjust=False).mean()
    weights = np.arange(1, 21)
    df["WMA_20"] = (
        df["Close"]
        .rolling(20)
        .apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)
    )
    df["Swing_High"] = df["High"].rolling(20).max()
    df["Swing_Low"] = df["Low"].rolling(20).min()
    return df


# --- 4. اختبار تاريخي محسن (SL -0.27 | TP 0.786 | فلتر R:R >= 0.8) ---
def run_optimized_backtest(coins_map, interval, trade_size=100.0):
    total_pnl = 0.0
    wins = 0
    losses = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        df = fetch_data(yf_ticker, interval, period="5d")
        df_1m = fetch_1m_data(yf_ticker)

        if len(df) < 25 or df_1m.empty:
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
                            "النوع": "شراء (Fib Opt)",
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
                            "النوع": "شراء (Fib Opt)",
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
                            "النوع": "بيع (Fib Opt)",
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
                            "النوع": "بيع (Fib Opt)",
                            "الحالة": "خاسرة",
                            "الربح/الخسارة ($)": round(pnl, 2),
                        })
            else:
                s_high = float(prev["Swing_High"])
                s_low = float(prev["Swing_Low"])
                fib_range = s_high - s_low
                if pd.isna(fib_range) or fib_range <= 0:
                    continue

                sub_1m = df_1m[df_1m.index >= curr_time]
                if sub_1m.empty:
                    continue
                confirm_1m_close = float(sub_1m["Close"].iloc[0])
                wma_level = float(row["WMA_20"])

                # تقاطع شراء + إغلاق 1m فوق التقاطع
                if (
                    prev["EMA_2"] <= prev["WMA_20"]
                    and row["EMA_2"] > row["WMA_20"]
                ):
                    if confirm_1m_close > wma_level:
                        target_786 = s_low + (0.786 * fib_range)
                        stop_027 = s_low - (0.27 * fib_range)
                        reward = target_786 - confirm_1m_close
                        risk = confirm_1m_close - stop_027
                        # فلتر الأمان: رفض الصفقة إذا كانت متأخرة (R:R < 0.8)
                        if risk > 0 and (reward / risk) >= 0.8:
                            in_trade = True
                            trade_type = "BUY"
                            entry_p = confirm_1m_close
                            sl_p = stop_027
                            tp_p = target_786
                            entry_time = sub_1m.index[0]

                # تقاطع بيع + إغلاق 1m تحت التقاطع
                elif (
                    prev["EMA_2"] >= prev["WMA_20"]
                    and row["EMA_2"] < row["WMA_20"]
                ):
                    if confirm_1m_close < wma_level:
                        target_786 = s_high - (0.786 * fib_range)
                        stop_027 = s_high + (0.27 * fib_range)
                        reward = confirm_1m_close - target_786
                        risk = stop_027 - confirm_1m_close
                        if risk > 0 and (reward / risk) >= 0.8:
                            in_trade = True
                            trade_type = "SELL"
                            entry_p = confirm_1m_close
                            sl_p = stop_027
                            tp_p = target_786
                            entry_time = sub_1m.index[0]

    return round(total_pnl, 2), wins, losses, pd.DataFrame(history_list)
# --- 5. فحص الإشارات اللحظية المحسنة ---
def scan_coin_optimized(yf_ticker, display_name, interval):
    df = fetch_data(yf_ticker, interval, period="5d")
    df_1m = fetch_1m_data(yf_ticker)

    if len(df) < 25 or df_1m.empty:
        return None

    df = calculate_indicators(df)
    prev_ema = df["EMA_2"].iloc[-3]
    prev_wma = df["WMA_20"].iloc[-3]
    curr_ema = df["EMA_2"].iloc[-2]
    curr_wma = df["WMA_20"].iloc[-2]

    s_high = float(df["Swing_High"].iloc[-2])
    s_low = float(df["Swing_Low"].iloc[-2])
    fib_range = s_high - s_low

    last_1m_close = float(df_1m["Close"].iloc[-2])
    current_price = float(df["Close"].iloc[-1])

    signal = "انتظار / لا يوجد تقاطع"
    sl_price = 0.0
    tp_price = 0.0

    if prev_ema <= prev_wma and curr_ema > curr_wma:
        target_786 = s_low + (0.786 * fib_range)
        stop_027 = s_low - (0.27 * fib_range)
        reward = target_786 - last_1m_close
        risk = last_1m_close - stop_027
        if last_1m_close > curr_wma and risk > 0 and (reward / risk) >= 0.8:
            signal = "شراء مؤكد (BUY Opt)"
            sl_price = stop_027
            tp_price = target_786
        else:
            signal = "تقاطع شراء (مرفوض - R:R ضعيف)"

    elif prev_ema >= prev_wma and curr_ema < curr_wma:
        target_786 = s_high - (0.786 * fib_range)
        stop_027 = s_high + (0.27 * fib_range)
        reward = last_1m_close - target_786
        risk = stop_027 - last_1m_close
        if last_1m_close < curr_wma and risk > 0 and (reward / risk) >= 0.8:
            signal = "بيع مؤكد (SELL Opt)"
            sl_price = stop_027
            tp_price = target_786
        else:
            signal = "تقاطع بيع (مرفوض - R:R ضعيف)"

    return {
        "العملة": display_name,
        "السعر الحالي": round(current_price, 5),
        "إغلاق 1m": round(last_1m_close, 5),
        "الإشارة": signal,
        "وقف الخسارة (-0.27)": round(sl_price, 5) if sl_price > 0 else "-",
        "الهدف (0.786)": round(tp_price, 5) if tp_price > 0 else "-",
    }


# --- 6. واجهة التطبيق ---
st.title("📊 ماسح EMA 2 × WMA 20 (نسخة فيبوناتشي المحسنة)")
st.caption("التأكيد: 1m | الوقف: Fib -0.27 | الهدف: Fib 0.786 | فلتر R:R >= 0.8")

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

col_tf, col_cap = st.columns(2)
with col_tf:
    selected_tf = st.selectbox(
        "اختر الإطار الزمني الأساسي:", ["5m", "15m", "30m"], index=0
    )
with col_cap:
    trade_amount = st.number_input(
        "حجم الصفقة بالدولار ($):", min_value=10, value=100, step=10
    )

with st.spinner("جاري حساب الأداء بالمعادلة المحسنة..."):
    net_pnl, w_count, l_count, bt_df = run_optimized_backtest(
        COINS_MAP, selected_tf, trade_amount
    )
    total_t = w_count + l_count
    win_rate = round((w_count / total_t) * 100, 1) if total_t > 0 else 0.0

c1, c2, c3 = st.columns(3)
c1.metric(f"الربح الصافي (آخر 5 أيام - {selected_tf})", f"{net_pnl} $")
c2.metric("نسبة النجاح المحسنة", f"{win_rate}%", f"إجمالي الصفقات: {total_t}")
c3.metric("توزيع الصفقات", f"{w_count} ناجحة", f"-{l_count} خاسرة")

st.divider()

if st.button("فحص الفرص المؤكدة الآن 🔄", use_container_width=True):
    df_history, file_sha = load_trades()
    scan_results = []
    new_added = 0

    for display_name, yf_ticker in COINS_MAP.items():
        res = scan_coin_optimized(yf_ticker, display_name, selected_tf)
        if res:
            scan_results.append(res)
            if "مؤكد" in res["الإشارة"]:
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Coin": display_name,
                    "Timeframe": selected_tf,
                    "Type": res["الإشارة"],
                    "Entry_Price": res["إغلاق 1m"],
                    "Stop_Loss": res["وقف الخسارة (-0.27)"],
                    "Take_Profit": res["الهدف (0.786)"],
                    "Status": "مفتوحة",
                    "PnL": 0.0,
                }])
                df_history = pd.concat(
                    [df_history, new_row], ignore_index=True
                )
                new_added += 1

    if new_added > 0:
        save_trades(df_history, file_sha, f"Add {new_added} Opt-Fib signals")
        st.success(f"تم رصد وحفظ {new_added} فرصة مؤكدة في GitHub!")

    st.subheader("الأسعار والإشارات اللحظية الآن:")
    st.dataframe(pd.DataFrame(scan_results), use_container_width=True)

if not bt_df.empty:
    st.divider()
    st.subheader(
        f"📋 سجل الصفقات المحسنة (آخر 5 أيام على فريم {selected_tf} + 1m)"
    )
    st.dataframe(
        bt_df.sort_values(by="الوقت", ascending=False), use_container_width=True
    )
