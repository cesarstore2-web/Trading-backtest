import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="متتبع التداول الفوري - التنبؤ بالفراكتل", layout="centered")

css = (
    "<style>"
    ".main { direction: rtl; text-align: right; }"
    "div[data-testid='stCheckbox'] { direction: rtl; text-align: right; }"
    "div[data-testid='stSelectbox'], div[data-testid='stNumberInput'] { direction: rtl; text-align: right; }"
    ".profit-box-green { background-color: #0d3b1e; border: 2px solid #28a745; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-box-red { background-color: #3b0d0d; border: 2px solid #dc3545; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 20px; }"
    ".profit-title { color: #e0e0e0; font-size: 18px; margin-bottom: 5px; }"
    ".profit-amount-green { color: #2ecc71; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".profit-amount-red { color: #ff6b6b; font-size: 36px; font-weight: bold; direction: ltr; }"
    ".info-bar { color: #aaaaaa; font-size: 13px; text-align: center; margin: 15px 0; padding: 8px; background-color: #1e1e1e; border-radius: 8px; }"
    ".alert-box { background-color: #162436; border: 1px solid #2b4c7e; border-radius: 10px; padding: 15px; text-align: center; color: #90caf9; }"
    "</style>"
)
st.markdown(css, unsafe_allow_html=True)

COINS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "ATOM-USD", "NEAR-USD", "ALGO-USD", 
    "XLM-USD", "VET-USD", "HBAR-USD", "FIL-USD", "ICP-USD", 
    "APT-USD", "ARB-USD", "OP-USD", "RENDER-USD", "GRT-USD", 
    "TIA-USD", "SUI-USD"
]

if 'fractal_len' not in st.session_state:
    st.session_state.fractal_len = 15
if 'forecast_len' not in st.session_state:
    st.session_state.forecast_len = 12
if 'min_corr' not in st.session_state:
    st.session_state.min_corr = 0.82
if 'tp_pct' not in st.session_state:
    st.session_state.tp_pct = 2.5
if 'sl_pct' not in st.session_state:
    st.session_state.sl_pct = 1.5
if 'use_sl' not in st.session_state:
    st.session_state.use_sl = True
if 'trade_amount' not in st.session_state:
    st.session_state.trade_amount = 100.0

TIMEFRAME_OPTIONS = {
    "5 دقائق (5m)": ("5m", "7d"),
    "15 دقيقة (15m)": ("15m", "14d"),
    "30 دقيقة (30m)": ("30m", "30d"),
    "1 ساعة (1h)": ("1h", "45d"),
    "4 ساعات (4h)": ("4h", "60d"),
    "يومي (1d)": ("1d", "180d")
}

selected_tf_label = st.selectbox(
    "⏱️ اختر الإطار الزمني للتداول:",
    options=list(TIMEFRAME_OPTIONS.keys()),
    index=0
)
TIMEFRAME, DATA_PERIOD = TIMEFRAME_OPTIONS[selected_tf_label]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_coin_data(symbol, period_str, timeframe):
    return yf.Ticker(symbol).history(period=period_str, interval=timeframe)

def find_best_fractal_match(closes, current_idx, f_len, proj_len):
    target_pattern = closes[current_idx - f_len + 1 : current_idx + 1]
    t_std = np.std(target_pattern)
    if t_std == 0:
        return None

    t_norm = (target_pattern - np.mean(target_pattern)) / t_std
    best_corr = -1.0
    best_idx = -1

    # البحث في التاريخ السابق مع ترك مسافة كافية للتنبؤ وعدم التداخل
    search_end = current_idx - f_len - proj_len
    if search_end < f_len:
        return None

    # تسريع البحث بالخطوة 2 في البيانات الطويلة
    step = 2 if search_end > 400 else 1
    for j in range(f_len, search_end, step):
        cand = closes[j - f_len + 1 : j + 1]
        c_std = np.std(cand)
        if c_std == 0:
            continue
        c_norm = (cand - np.mean(cand)) / c_std
        corr = float(np.dot(t_norm, c_norm) / f_len)
        if corr > best_corr:
            best_corr = corr
            best_idx = j

    if best_idx == -1:
        return None

    # استخراج المسار المستقبلي للفراكتل وتكبيره ليتطابق مع السعر الحالي
    hist_base_price = closes[best_idx]
    curr_base_price = closes[current_idx]
    hist_future = closes[best_idx + 1 : best_idx + 1 + proj_len]

    # نسبة التغير التاريخية وتطبيقها على السعر الحالي (Scaling)
    scale_factor = curr_base_price / hist_base_price
    projected_prices = hist_future * scale_factor

    return best_corr, projected_prices

def run_fractal_scanner(timeframe, period_str, f_len, proj_len, min_corr, tp_pct, sl_pct, use_sl, trade_amount):
    trades_history = []
    current_opportunities = []
    forecasts_dict = {}

    progress_bar = st.progress(0)
    status_text = st.empty()

    tp_dec = tp_pct / 100.0
    sl_dec = sl_pct / 100.0

    for idx_coin, symbol in enumerate(COINS):
        coin_name = symbol.replace("-USD", "")
        status_text.caption(f"🧬 جاري استخراج الفراكتل لـ {coin_name} ({idx_coin + 1}/{len(COINS)})...")
        progress_bar.progress((idx_coin + 1) / len(COINS))

        try:
            df = fetch_coin_data(symbol, period_str, timeframe)
            if df is None or df.empty or len(df) < (f_len * 3 + proj_len):
                continue

            highs = df['High'].to_numpy(dtype=float)
            lows = df['Low'].to_numpy(dtype=float)
            closes = df['Close'].to_numpy(dtype=float)
            times = df.index

            in_position = False
            buy_price = 0.0
            tp_price = 0.0
            sl_price = 0.0
            buy_time = None

            # محاكاة الصفقات على آخر 300 شمعة لضمان السرعة والدقة
            start_sim = max(f_len * 2 + proj_len, len(df) - 300)

            for i in range(start_sim, len(df) - 1):
                curr_high = highs[i]
                curr_low = lows[i]
                curr_close = closes[i]
                curr_time = times[i]

                if in_position:
                    sell_reason = None
                    sell_price = 0.0

                    if use_sl and curr_low <= sl_price:
                        sell_price = sl_price
                        sell_reason = f"وقف خسارة (-{sl_pct}%)"
                    elif curr_high >= tp_price:
                        sell_price = tp_price
                        sell_reason = f"هدف الفراكتل (+{tp_pct}%)"

                    if sell_reason:
                        profit_pct = (sell_price - buy_price) / buy_price
                        profit_usd = trade_amount * profit_pct
                        trades_history.append({
                            "العملة": coin_name,
                            "تاريخ الشراء": str(buy_time)[:16],
                            "سعر الشراء": round(buy_price, 4),
                            "تاريخ البيع": str(curr_time)[:16],
                            "سعر البيع": round(sell_price, 4),
                            "سبب الإغلاق": sell_reason,
                            "الربح ($)": round(profit_usd, 2),
                            "النسبة (%)": round(profit_pct * 100, 2)
                        })
                        in_position = False
                    continue

                match = find_best_fractal_match(closes, i, f_len, proj_len)
                if match is not None:
                    corr, proj_prices = match
                    max_proj = float(np.max(proj_prices))
                    min_proj = float(np.min(proj_prices))
                    expected_gain = (max_proj - curr_close) / curr_close
                    expected_drawdown = (curr_close - min_proj) / curr_close

                    # شرط الدخول: تطابق فراكتل عالي + توقع صعود يتجاوز الهدف قبل الهبوط
                    if corr >= min_corr and expected_gain >= tp_dec and expected_drawdown < sl_dec:
                        in_position = True
                        buy_price = curr_close
                        tp_price = buy_price * (1 + tp_dec)
                        sl_price = buy_price * (1 - sl_dec)
                        buy_time = curr_time

            # التنبؤ بالمستقبل للشمعة الحالية (آخر شمعة)
            last_idx = len(df) - 1
            live_match = find_best_fractal_match(closes, last_idx, f_len, proj_len)
            if live_match is not None:
                corr, proj_prices = live_match
                curr_price = closes[last_idx]
                max_proj = float(np.max(proj_prices))
                expected_gain_pct = ((max_proj - curr_price) / curr_price) * 100.0

                if corr >= min_corr and expected_gain_pct >= tp_pct:
                    current_opportunities.append({
                        "العملة": coin_name,
                        "نسبة التطابق": f"{round(corr * 100, 1)}%",
                        "السعر الحالي": round(curr_price, 4),
                        "السعر المتوقع (المكبر)": round(max_proj, 4),
                        "الربح المتوقع (%)": f"+{round(expected_gain_pct, 2)}%",
                        "هدف البيع": round(curr_price * (1 + tp_dec), 4),
                        "الوقت": str(times[last_idx])[:16]
                    })
                    # حفظ مسار الرسم البياني للتنبؤ
                    hist_segment = closes[last_idx - f_len + 1 : last_idx + 1]
                    forecasts_dict[coin_name] = (hist_segment, proj_prices)

        except Exception:
            continue

    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(trades_history), pd.DataFrame(current_opportunities), forecasts_dict

trades_df, opps_df, forecasts_dict = run_fractal_scanner(
    TIMEFRAME,
    DATA_PERIOD,
    st.session_state.fractal_len,
    st.session_state.forecast_len,
    st.session_state.min_corr,
    st.session_state.tp_pct,
    st.session_state.sl_pct,
    st.session_state.use_sl,
    st.session_state.trade_amount
)

weekly_profit = 0.0
weekly_trades = pd.DataFrame()
current_month_trades = pd.DataFrame()

if not trades_df.empty:
    trades_df['تاريخ البيع_dt'] = pd.to_datetime(trades_df['تاريخ البيع'])
    now = pd.Timestamp.now(tz=trades_df['تاريخ البيع_dt'].dt.tz)
    
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
