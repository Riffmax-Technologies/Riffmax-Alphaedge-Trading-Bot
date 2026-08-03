# audit_bot_trades_weekly.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

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
        
    now = datetime.now()
    # Go back to Monday, July 6 (start of the week)
    week_start = datetime(2026, 7, 6, 0, 0, 0)
    
    deals = mt5.history_deals_get(week_start, now)
    if not deals:
        print("No deals found for this week.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for bot comments
    bot_df = df[df['comment'].str.contains("ALPHAEDGE|SHERIFNEW", case=False, na=False)].copy()
    if bot_df.empty:
        print("No bot trades found in history this week.")
        mt5.shutdown()
        return
        
    bot_df['time'] = pd.to_datetime(bot_df['time'], unit='s')
    
    # Map entry types
    entry_map = {0: "IN", 1: "OUT", 2: "IN/OUT", 3: "OUT (SL/TP)"}
    bot_df['type_desc'] = bot_df['entry'].map(entry_map)
    
    # Group by ticket/position to see full cycle of trades (in and out)
    print("=== Bot Exits (Out Trades) Details ===")
    exits = bot_df[bot_df['entry'].isin([1, 3])].copy()
    if exits.empty:
        print("No exits (closed trades) found. All trades might still be open.")
    else:
        print(exits[['time', 'symbol', 'volume', 'price', 'profit', 'comment']].to_string(index=False))
        
    print("\n=== Bot Active Open Positions ===")
    open_pos = mt5.positions_get()
    if not open_pos:
        print("No open positions.")
    else:
        pos_df = pd.DataFrame(list(open_pos), columns=open_pos[0]._asdict().keys())
        bot_open = pos_df[pos_df['comment'].str.contains("ALPHAEDGE|SHERIFNEW", case=False, na=False)].copy()
        if bot_open.empty:
            print("No active bot positions open.")
        else:
            print(bot_open[['symbol', 'type', 'volume', 'price_open', 'price_current', 'sl', 'tp', 'profit', 'comment']].to_string(index=False))
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
