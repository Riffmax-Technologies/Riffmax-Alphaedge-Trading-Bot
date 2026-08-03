# check_today_trades.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, time as dtime

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
    
    # Get deals for today
    deals = mt5.history_deals_get(today_start, now)
    print(f"--- Trades/Deals executed today ({today_start.date()}) ---")
    if not deals:
        print("No deals executed today.")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # Filter for AlphaEdge comments
        df_ae = df[df['comment'].str.contains("ALPHAEDGE", case=False, na=False)]
        if df_ae.empty:
            print("No AlphaEdge deals executed today in history.")
        else:
            cols = ['time', 'symbol', 'type', 'entry', 'volume', 'price', 'profit', 'comment']
            # Convert time
            df_ae['time'] = pd.to_datetime(df_ae['time'], unit='s')
            print(df_ae[cols].to_string(index=False))
            
    # Check open positions
    open_positions = mt5.positions_get()
    print("\n--- Currently Open Positions ---")
    if not open_positions:
        print("No active open positions.")
    else:
        df_pos = pd.DataFrame(list(open_positions), columns=open_positions[0]._asdict().keys())
        df_ae_pos = df_pos[df_pos['comment'].str.contains("ALPHAEDGE", case=False, na=False)]
        if df_ae_pos.empty:
            print("No active AlphaEdge positions.")
        else:
            cols_pos = ['ticket', 'symbol', 'type', 'volume', 'price_open', 'price_current', 'sl', 'tp', 'profit']
            print(df_ae_pos[cols_pos].to_string(index=False))
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
