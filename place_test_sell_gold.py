# place_test_sell_gold.py
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys, os

scratch_dir = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/scratch"
if scratch_dir not in sys.path:
    sys.path.insert(0, scratch_dir)

from alphaedge import calculate_atr, send_telegram_alert

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def main():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    symbol = "XAUUSD"
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
        
    current_price = mt5.symbol_info_tick(symbol).bid
    sl = current_price + 3.0 * atr
    tp = current_price - 5.0 * atr
    volume = symbol_info.volume_min
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL,
        "price": current_price,
        "sl": round(sl, symbol_info.digits),
        "tp": round(tp, symbol_info.digits),
        "comment": "ALPHAEDGE_TRADE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        ticket = result.order
        print(f"Successfully placed test SELL on {symbol} (Ticket: {ticket}, Lot: {volume}, Entry: {current_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f})")
        # Send Telegram alert
        msg = f"🚀 <b>[AlphaEdge Test SELL Opened]</b>\nSymbol: {symbol}\nAction: SELL\nLot Size: {volume}\nEntry Price: {current_price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}\nTicket: {ticket}"
        send_telegram_alert(msg)
        print("Telegram notification sent.")
    else:
        print(f"Failed to place test SELL on {symbol}: {result.comment if result else 'N/A'} (Retcode: {result.retcode if result else 'N/A'})")
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
