import os
from strategy import SMCStrategy

def run_automated_bot():
    # قراءة المفاتيح من إعدادات GitHub Secrets
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    
    # قراءة الإعدادات (أو استخدام القيم الافتراضية)
    htf = os.environ.get("HTF", "1h")
    ltf = os.environ.get("LTF", "5m")
    rr_ratio = float(os.environ.get("RR_RATIO", "2.0"))
    risk_percent = float(os.environ.get("RISK_PERCENT", "1.0"))
    start_hour = int(os.environ.get("START_HOUR", "7"))
    end_hour = int(os.environ.get("END_HOUR", "21"))
    use_testnet = os.environ.get("USE_TESTNET", "True").lower() == "true"

    bot = SMCStrategy(api_key=api_key, api_secret=api_secret, use_testnet=use_testnet)
    
    print(f"Starting SMC Market Scan ({htf} -> {ltf})...")
    signals = bot.scan_market(
        htf=htf, 
        ltf=ltf, 
        rr_ratio=rr_ratio, 
        start_hour=start_hour, 
        end_hour=end_hour
    )

    if not signals:
        print("No valid SMC setups found in this cycle.")
        return

    # جلب الرصيد الفعلي لحساب حجم الصفقة بدقة
    try:
        balance_info = bot.exchange.fetch_balance()
        usdt_balance = float(balance_info['total'].get('USDT', 1000.0))
    except Exception:
        usdt_balance = 1000.0 # رصيد احتياطي في حال عدم ربط المفاتيح

    for sig in signals:
        qty = bot.calculate_position_size(usdt_balance, risk_percent, sig['entry'], sig['sl'])
        print(f"Signal Detected: {sig['symbol']} | {sig['signal']} | Entry: {sig['entry']} | SL: {sig['sl']} | TP: {sig['tp']} | Qty: {qty}")
        
        if api_key and api_secret and qty > 0:
            res = bot.execute_order(sig['symbol'], sig['signal'], qty, sig['entry'], sig['sl'], sig['tp'])
            print(f"Execution Result for {sig['symbol']}: {res}")

if __name__ == "__main__":
    run_automated_bot()
