import MetaTrader5 as mt5
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UpdateManualSLTP")

def update_sltp():
    if not mt5.initialize():
        logger.error("Failed to initialize MT5")
        return
        
    positions = mt5.positions_get()
    if not positions:
        logger.info("No open positions found.")
        mt5.shutdown()
        return
        
    # SL/TP targets from the active bot positions
    targets = {
        "XAUUSD": {"sl": 4006.86, "tp": 4063.87},
        "XAGUSD": {"sl": 58.38, "tp": 59.87}
    }
    
    for pos in positions:
        # Match only manual trades (empty comment or 'Manual')
        if pos.symbol in targets and pos.comment in ["", "Manual"]:
            symbol = pos.symbol
            sl = targets[symbol]["sl"]
            tp = targets[symbol]["tp"]
            
            logger.info(f"Updating position {pos.ticket} ({symbol}) with SL: {sl}, TP: {tp}...")
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": symbol,
                "sl": sl,
                "tp": tp
            }
            
            result = mt5.order_send(request)
            if result is None:
                logger.error(f"Failed to update. Raw send returned None.")
            elif result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Failed to update. Retcode: {result.retcode}, Comment: {result.comment}")
            else:
                logger.info(f"Successfully updated position {pos.ticket}!")
                
    mt5.shutdown()

if __name__ == "__main__":
    update_sltp()
