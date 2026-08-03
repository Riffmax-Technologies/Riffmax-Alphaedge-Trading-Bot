# place_test_trades.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def calculate_atr(df, period=14):
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = np.maximum(df['high'] - df['low'],
                          np.maximum(np.abs(df['high'] - df['prev_close']),
                                     np.abs(df['low'] - df['prev_close'])))
    df['atr'] = df['tr'].rolling(window=period).mean()
    # Fallback to simple high-low range if atr is nan
    df['atr'] = df['atr'].fillna(df['high'] - df['low'])
    return df

def send_test_buy(symbol):
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"Symbol {symbol} not found.")
        return
        
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)
        
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 30)
    if rates is None or len(rates) < 15:
        print(f"Failed to fetch rates for {symbol}")
        return
        
    df = pd.DataFrame(rates)
    df = calculate_atr(df)
    atr = df['atr'].iloc[-1]
    if atr <= 0:
        atr = symbol_info.point * 100
        
    current_price = mt5.symbol_info_tick(symbol).ask
    sl = current_price - 3.0 * atr
    tp = current_price + 5.0 * atr
    volume = symbol_info.volume_min
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": current_price,
        "sl": round(sl, symbol_info.digits),
        "tp": round(tp, symbol_info.digits),
        "comment": "ALPHAEDGE_TRADE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Successfully placed test BUY on {symbol} (Ticket: {result.order}, Lot: {volume}, SL: {sl:.5f}, TP: {tp:.5f})")
    else:
        print(f"Failed to place test BUY on {symbol}: {result.comment if result else 'N/A'} (Retcode: {result.retcode if result else 'N/A'})")

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    print("=== Execution of AlphaEdge Test Trades ===")
    for symbol in ["XAUUSD", "XAGUSD", "ETHUSD", "BTCUSD"]:
        send_test_buy(symbol)
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
