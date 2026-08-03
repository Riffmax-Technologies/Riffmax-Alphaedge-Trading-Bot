import MetaTrader5 as mt5
import pandas as pd
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuickMetalsBuy")

def calculate_atr(df, period=7):
    """Calculate Average True Range (ATR)"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=period).mean()
    return df

def get_lot_size(symbol, sl_price=0.0, entry_price=0.0, risk_usd=50.0):
    """Calculates lot size dynamically so that a hit stop loss equals exactly risk_usd"""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return 0.01
        
    min_volume = symbol_info.volume_min
    max_volume = symbol_info.volume_max
    
    if sl_price == 0.0 or entry_price == 0.0:
        return min_volume
        
    sl_distance = abs(entry_price - sl_price)
    if sl_distance == 0:
        return min_volume
        
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size
    
    if tick_value == 0 or tick_size == 0:
        contract_size = symbol_info.trade_contract_size
        lot_size = risk_usd / (sl_distance * contract_size) if contract_size > 0 else min_volume
    else:
        lot_size = risk_usd / (sl_distance * (tick_value / tick_size))
        
    lot_size = max(min_volume, min(max_volume, round(lot_size, 2)))
    return lot_size

def execute_quick_buy():
    if not mt5.initialize():
        logger.error("Failed to initialize MT5")
        return
        
    metals = ["XAUUSD", "XAGUSD"]
    orders = []
    
    for symbol in metals:
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logger.error(f"Symbol {symbol} not found.")
            continue
            
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
            
        # Get M30 ATR
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 20)
        if rates is None or len(rates) < 10:
            logger.error(f"Failed to get rates for {symbol}")
            continue
            
        df = pd.DataFrame(rates)
        df = calculate_atr(df, period=7)
        last_atr = df['atr'].iloc[-1]
        
        # Current Ask price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Failed to get tick for {symbol}")
            continue
            
        entry_price = tick.ask
        
        # Calculate SL/TP
        sl_offset = 1.5 * last_atr
        tp_offset = 3.0 * last_atr
        
        sl = entry_price - sl_offset
        tp = entry_price + tp_offset
        
        # Lot Size (using standard $50 risk dynamic sizing)
        lot_size = get_lot_size(symbol, sl_price=sl, entry_price=entry_price)
        
        orders.append({
            "symbol": symbol,
            "action": mt5.TRADE_ACTION_DEAL,
            "volume": lot_size,
            "type": mt5.ORDER_TYPE_BUY,
            "price": entry_price,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "deviation": 20,
            "magic": 99999,
            "comment": "Manual_Sync",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        })
        
    print("\n=== Sync Buy Confirmation ===")
    for o in orders:
        print(f"{o['symbol']} | Vol: {o['volume']} | Ask: {o['price']:.3f} | SL: {o['sl']:.3f} | TP: {o['tp']:.3f}")
        
    for request in orders:
        logger.info(f"Sending BUY order for {request['symbol']}...")
        result = mt5.order_send(request)
        if result is None:
            logger.error(f"Failed to execute. Raw send returned None.")
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed on {request['symbol']}: {result.comment} (Code: {result.retcode})")
        else:
            logger.info(f"Successfully placed BUY order on {request['symbol']}! Ticket: {result.order}")
            
    mt5.shutdown()

if __name__ == "__main__":
    execute_quick_buy()
