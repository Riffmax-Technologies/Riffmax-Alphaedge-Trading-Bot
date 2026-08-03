import MetaTrader5 as mt5

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

if not mt5.initialize(login=MT5_CONFIG["login"], password=MT5_CONFIG["password"], server=MT5_CONFIG["server"]):
    print("Failed to initialize MT5")
    exit(1)

positions = mt5.positions_get()
if positions is not None:
    closed_count = 0
    for pos in positions:
        comment = getattr(pos, 'comment', '')
        if comment.startswith("BASKET_") and not comment.startswith("BASKET_BEST_"):
            ticket = pos.ticket
            symbol = pos.symbol
            volume = pos.volume
            # Close trade
            price = mt5.symbol_info_tick(symbol).ask if pos.type == 1 else mt5.symbol_info_tick(symbol).bid
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": 0,
                "comment": "Manual Close Basket",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"Closed position {ticket} ({symbol}) successfully.")
                closed_count += 1
            else:
                print(f"Failed to close position {ticket} ({symbol}): {result.comment}")
    print(f"Total closed tradenow positions: {closed_count}")
else:
    print("No positions found.")

mt5.shutdown()
