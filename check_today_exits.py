# check_today_exits.py
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
    
    deals = mt5.history_deals_get(today_start, now)
    if not deals:
        print("No deals executed today.")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # Filter for AlphaEdge comments or positions that were entered via AlphaEdge
        # Let's find all unique position IDs that have ALPHAEDGE in the comment
        ae_pos_ids = df[df['comment'].str.contains("ALPHAEDGE", case=False, na=False)]['position_id'].unique()
        
        if len(ae_pos_ids) == 0:
            print("No AlphaEdge positions found today.")
        else:
            # Get all deals matching these position IDs
            df_ae = df[df['position_id'].isin(ae_pos_ids)].copy()
            df_ae['time'] = pd.to_datetime(df_ae['time'], unit='s')
            
            # Sort by position ID and time
            df_ae = df_ae.sort_values(by=['position_id', 'time'])
            
            cols = ['position_id', 'time', 'symbol', 'type', 'entry', 'volume', 'price', 'profit', 'comment']
            print("--- Detailed Deals for AlphaEdge Positions today ---")
            print(df_ae[cols].to_string(index=False))
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
