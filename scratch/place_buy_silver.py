import MetaTrader5 as mt5
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManualTrade")

def place_manual_buy_silver():
    if not mt5.initialize():
        logger.error("Failed to initialize MT5")
        return
        
    symbol = "XAGUSD"
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"Symbol {symbol} not found.")
        mt5.shutdown()
        return
        
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)
        
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logger.error(f"Failed to get tick for {symbol}")
        mt5.shutdown()
        return
        
    price = tick.ask
    volume = 0.01
    
    logger.info(f"Placing manual BUY order on {symbol} at {price} for {volume} lots...")
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "deviation": 20,
        "magic": 99999,
        "comment": "Manual",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result is None:
        logger.error(f"Order failed. Raw send returned None. Last error: {mt5.last_error()}")
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Order failed. Retcode: {result.retcode}, Comment: {result.comment}")
    else:
        logger.info(f"Successfully placed BUY order on {symbol}! Ticket: {result.order}")
        
    mt5.shutdown()

if __name__ == "__main__":
    place_manual_buy_silver()
