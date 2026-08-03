import MetaTrader5 as mt5
import pandas as pd
import time

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

SYMBOLS = ["GBPJPY", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD"]

def get_market_trend_advanced(symbol: str) -> str:
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 50)
        if rates is None or len(rates) < 21:
            return "BUY (Fallback - No Data)"
            
        df = pd.DataFrame(rates)
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        last_ema9 = df['ema9'].iloc[-1]
        last_ema21 = df['ema21'].iloc[-1]
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        last_rsi = df['rsi'].iloc[-1]
        
        if last_ema9 > last_ema21 and last_rsi > 50:
            trend = "BUY"
            reason = f"EMA9 ({last_ema9:.5f}) > EMA21 ({last_ema21:.5f}) & RSI ({last_rsi:.1f}) > 50"
        elif last_ema9 < last_ema21 and last_rsi < 50:
            trend = "SELL"
            reason = f"EMA9 ({last_ema9:.5f}) < EMA21 ({last_ema21:.5f}) & RSI ({last_rsi:.1f}) < 50"
        else:
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-4] if len(df) >= 4 else df['open'].iloc[-1]
            trend = "BUY" if last_close > prev_close else "SELL"
            reason = f"Neutral Indicators. Fallback to last 3 M5 candles: {prev_close:.5f} -> {last_close:.5f}"
            
        return trend, reason
    except Exception as e:
        return "BUY", f"Error: {e}"

def get_sltp_levels(symbol: str, action: str, entry_price: float):
    symbol_upper = symbol.upper()
    action_upper = action.upper()
    
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point if symbol_info else 0.00001
    
    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        offset_sl = 5.0
        offset_tp = 10.0
    elif "BTC" in symbol_upper:
        offset_sl = 300.0
        offset_tp = 600.0
    else:
        offset_sl = 30 * 10 * point
        offset_tp = 60 * 10 * point
        
    if action_upper == "BUY":
        sl = entry_price - offset_sl
        tp = entry_price + offset_tp
    else:
        sl = entry_price + offset_sl
        tp = entry_price - offset_tp
        
    return round(sl, 5), round(tp, 5)

if not mt5.initialize(login=MT5_CONFIG["login"], password=MT5_CONFIG["password"], server=MT5_CONFIG["server"]):
    print("Failed to initialize MT5")
    exit(1)

print("\n--- DRY RUN TREND AND SL/TP LEVELS ---")
for s in SYMBOLS:
    mt5.symbol_select(s, True)
    tick = mt5.symbol_info_tick(s)
    if tick is None:
        print(f"{s}: Failed to fetch tick")
        continue
    trend, reason = get_market_trend_advanced(s)
    price = tick.ask if trend == "BUY" else tick.bid
    sl, tp = get_sltp_levels(s, trend, price)
    print(f"Symbol: {s}")
    print(f"  Current Price: {price:.5f}")
    print(f"  Trend Decision: {trend} ({reason})")
    print(f"  Computed SL: {sl:.5f}")
    print(f"  Computed TP: {tp:.5f}")
    print("-" * 40)

mt5.shutdown()
