import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone

class SMCStrategy:
    def __init__(self, api_key="", api_secret="", use_testnet=True):
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        })
        if use_testnet:
            self.exchange.set_sandbox_mode(True)
            
        self.symbols = [
            "XLM/USDT", "ZEC/USDT", "XRP/USDT", "HBAR/USDT", 
            "ADA/USDT", "LTC/USDT", "BTC/USDT", "ETH/USDT", 
            "PAXG/USDT", "XAU/USDT"
        ]

    def fetch_ohlcv(self, symbol, timeframe, limit=150):
        try:
            bars = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            return pd.DataFrame()

    def is_within_trading_hours(self, start_hour, end_hour):
        current_hour = datetime.now(timezone.utc).hour
        if start_hour <= end_hour:
            return start_hour <= current_hour <= end_hour
        else:
            return current_hour >= start_hour or current_hour <= end_hour

    def find_swings(self, df, window=5):
        df['swing_high'] = df['high'][(df['high'].shift(window) < df['high']) & 
                                      (df['high'].shift(-window) < df['high'])]
        df['swing_low'] = df['low'][(df['low'].shift(window) > df['low']) & 
                                    (df['low'].shift(-window) > df['low'])]
        
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max():
                df.loc[df.index[i], 'swing_high'] = df['high'].iloc[i]
            if df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min():
                df.loc[df.index[i], 'swing_low'] = df['low'].iloc[i]
        return df

    def detect_liquidity_sweep(self, htf_df, window=5):
        htf_df = self.find_swings(htf_df, window)
        valid_highs = htf_df['swing_high'].dropna()
        valid_lows = htf_df['swing_low'].dropna()
        
        if valid_highs.empty or valid_lows.empty:
            return None, None, None

        last_swing_high = valid_highs.iloc[-1]
        last_swing_low = valid_lows.iloc[-1]
        
        # فحص آخر شمعتين مكتملتين على الفريم الكبير للكسر الكاذب
        recent_candles = htf_df.iloc[-3:-1]
        
        for _, candle in recent_candles.iterrows():
            # مصيدة سيولة شرائية (كسر القاع للأسفل وإغلاق فوقه)
            if candle['low'] < last_swing_low and candle['close'] > last_swing_low:
                return "BUY_SWEEP", last_swing_low, candle['low']
            
            # مصيدة سيولة بيعية (اختراق القمة للأعلى وإغلاق أسفلها)
            if candle['high'] > last_swing_high and candle['close'] < last_swing_high:
                return "SELL_SWEEP", last_swing_high, candle['high']
                
        return None, None, None

    def check_ltf_choch_and_ob(self, ltf_df, sweep_type, sweep_extreme, rr_ratio=2.0):
        ltf_df = self.find_swings(ltf_df, window=3)
        current_close = ltf_df['close'].iloc[-2] # آخر شمعة مغلقة
        
        if sweep_type == "BUY_SWEEP":
            valid_highs = ltf_df['swing_high'].dropna()
            if valid_highs.empty:
                return None
            last_ltf_high = valid_highs.iloc[-1]
            
            # شرط CHoCH: إغلاق شمعة الفريم الصغير فوق آخر قمة فرعية هابطة
            if current_close > last_ltf_high:
                # البحث عن آخر شمعة هابطة كـ Order Block قبل الانطلاق
                bearish_candles = ltf_df.iloc[-15:-2][ltf_df['close'] < ltf_df['open']]
                if not bearish_candles.empty:
                    ob_candle = bearish_candles.iloc[-1]
                    entry_price = ob_candle['high']
                    stop_loss = sweep_extreme * 0.999 # أسفل ذيل الكسر الكاذب بقليل
                    risk = abs(entry_price - stop_loss)
                    take_profit = entry_price + (risk * rr_ratio)
                    
                    return {
                        "signal": "BUY",
                        "entry": round(entry_price, 5),
                        "sl": round(stop_loss, 5),
                        "tp": round(take_profit, 5),
                        "choch_level": round(last_ltf_high, 5)
                    }

        elif sweep_type == "SELL_SWEEP":
            valid_lows = ltf_df['swing_low'].dropna()
            if valid_lows.empty:
                return None
            last_ltf_low = valid_lows.iloc[-1]
            
            # شرط CHoCH: إغلاق شمعة الفريم الصغير تحت آخر قاع فرعي صاعد
            if current_close < last_ltf_low:
                # البحث عن آخر شمعة صاعدة كـ Bearish Order Block
                bullish_candles = ltf_df.iloc[-15:-2][ltf_df['close'] > ltf_df['open']]
                if not bullish_candles.empty:
                    ob_candle = bullish_candles.iloc[-1]
                    entry_price = ob_candle['low']
                    stop_loss = sweep_extreme * 1.001 # أعلى ذيل الكسر الكاذب بقليل
                    risk = abs(stop_loss - entry_price)
                    take_profit = entry_price - (risk * rr_ratio)
                    
                    return {
                        "signal": "SELL",
                        "entry": round(entry_price, 5),
                        "sl": round(stop_loss, 5),
                        "tp": round(take_profit, 5),
                        "choch_level": round(last_ltf_low, 5)
                    }
        return None

    def calculate_position_size(self, balance, risk_percent, entry, sl):
        risk_amount = balance * (risk_percent / 100.0)
        price_diff = abs(entry - sl)
        if price_diff == 0:
            return 0
        position_size = risk_amount / price_diff
        return round(position_size, 3)

    def scan_market(self, htf="1h", ltf="5m", rr_ratio=2.0, start_hour=0, end_hour=23):
        if not self.is_within_trading_hours(start_hour, end_hour):
            return []

        signals = []
        for symbol in self.symbols:
            htf_df = self.fetch_ohlcv(symbol, htf, limit=100)
            if htf_df.empty:
                continue
                
            sweep_type, level, extreme = self.detect_liquidity_sweep(htf_df)
            if sweep_type:
                ltf_df = self.fetch_ohlcv(symbol, ltf, limit=100)
                if ltf_df.empty:
                    continue
                    
                setup = self.check_ltf_choch_and_ob(ltf_df, sweep_type, extreme, rr_ratio)
                if setup:
                    setup['symbol'] = symbol
                    setup['htf_level'] = round(level, 5)
                    setup['time'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                    signals.append(setup)
                    
        return signals

    def execute_order(self, symbol, side, amount, entry_price, sl, tp):
        try:
            order_side = 'buy' if side == 'BUY' else 'sell'
            # وضع أمر معلق (Limit Order) عند منطقة الـ Order Block
            order = self.exchange.create_limit_order(symbol, order_side, amount, entry_price)
            return {"status": "success", "order_id": order['id']}
        except Exception as e:
            return {"status": "error", "message": str(e)}
