import concurrent.futures as cf

def eval_trade(ltf_rec, ts_arr, entry_time, direction, entry, sl, tp, risk_usd, reward_usd):
    start = int(np.searchsorted(ts_arr, np.datetime64(entry_time), side='right'))
    cur_sl, dist = sl, abs(entry - sl)
    for bar in ltf_rec[start:start + 280]:
        if direction == "BUY":
            if bar['high'] >= entry + dist * 1.1: cur_sl = entry
            if bar['low'] <= cur_sl: return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['high'] >= tp: return "رابحة", reward_usd
        else:
            if bar['low'] <= entry - dist * 1.1: cur_sl = entry
            if bar['high'] >= cur_sl: return ("مؤمّنة (0$)", 0.0) if cur_sl == entry else ("خاسرة", -risk_usd)
            if bar['low'] <= tp: return "رابحة", reward_usd
    return "جارية", 0.0