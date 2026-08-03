# get_alphaedge_trades_today.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

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
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    
    # Get all deals today
    deals = mt5.history_deals_get(today_start, now)
    if not deals:
        print("No deals found today.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for comment containing "ALPHAEDGE"
    ae_deals = df[df['comment'].str.contains("ALPHAEDGE", case=False, na=False)]
    if ae_deals.empty:
        print("No AlphaEdge deals found today.")
    else:
        # Convert timestamp to human readable
        ae_deals['time'] = pd.to_datetime(ae_deals['time'], unit='s')
        # Map entry type (0=in, 1=out, 2=in/out, 3=out by sl/tp)
        entry_map = {0: "IN", 1: "OUT", 2: "IN/OUT", 3: "OUT (SL/TP)"}
        ae_deals['type_desc'] = ae_deals['entry'].map(entry_map)
        
        print("=== AlphaEdge Trades Today (July 6, 2026) ===")
        print(ae_deals[['time', 'ticket', 'symbol', 'type_desc', 'volume', 'price', 'profit', 'comment']].to_string(index=False))
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
