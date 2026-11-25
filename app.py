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


# --- 2. جلب البيانات الحقيقية (10 أيام لحساب EMA 200 بدقة) ---
@st.cache_data(ttl=60)
def fetch_data(ticker, interval, period="10d"):
    df = yf.download(
        tickers=ticker, period=period, interval=interval, progress=False
    )
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.copy()


# --- 3. حساب مؤشر ATR وفلتر الاتجاه العام EMA 200 ---
def calculate_indicators(df, atr_period=14):
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(atr_period).mean()
    df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df


# --- 4. اختبار تاريخي محسن (EMA 200 + قوة FVG + تأمين الدخول عند 1.5 R:R) ---
def run_pro_amd_backtest(
    coins_map, interval, atr_mult, rr_ratio, use_ema200=True, use_be=True
):
    trade_size = 100.0  # 100 دولار لكل صفقة في الخفاء
    total_pnl = 0.0
    wins = 0
    losses = 0
    breakevens = 0
    history_list = []

    for display_name, yf_ticker in coins_map.items():
        df = fetch_data(yf_ticker, interval, period="10d")
        if len(df) < 210:
            continue

        df = calculate_indicators(df)

        # التركيز على آخر 5 أيام في حساب الأرباح بعد استقرار EMA 200
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
                    # تأمين نقطة الدخول (Break-Even) عند الوصول إلى 1.5 R:R
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
                        # فلتر الاتجاه العام EMA 200 للشراء
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
                        # فلتر الاتجاه العام EMA 200 للبيع
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

                # سيناريو الشراء + فلتر قوة الفجوة (> 0.25 ATR)
                manip_low = min(float(c1["Low"]), float(c2["Low"]))
                gap_buy = float(c3["Low"]) - float(c1["High"])
                if manip_low < acc_low and gap_buy > (0.25 * atr):
                    fvg_active = True
                    fvg_dir = "BUY"
                    fvg_top = float(c3["Low"])
                    fvg_bottom = float(c1["High"])
                    fvg_age = 0

                # سيناريو البيع + فلتر قوة الفجوة (> 0.25 ATR)
                manip_high = max(float(c1["High"]), float(c2["High"]))
                gap_sell = float(c1["Low"]) - float(c3["High"])
                if manip_high > acc_high and gap_sell > (0.25 * atr):
                    fvg_active = True
                    fvg_dir = "SELL"
