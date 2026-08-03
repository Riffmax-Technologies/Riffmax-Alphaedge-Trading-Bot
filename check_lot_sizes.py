# check_lot_sizes.py
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
    two_days_ago = now - timedelta(days=2)
    
    # Fetch history deals for last 2 days
    deals = mt5.history_deals_get(two_days_ago, now)
    if not deals:
        print("No deals found in the last 2 days.")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Sort by time descending
        df = df.sort_values(by='time', ascending=False)
        
        # Filter for entries (DEAL_ENTRY_IN) to see original position sizes
        df_entries = df[df['entry'] == 0].copy()
        
        print("=== Last 10 Position Entries ===")
        cols = ['time', 'position_id', 'symbol', 'type', 'volume', 'price', 'profit', 'comment']
        print(df_entries[cols].head(10).to_string(index=False))
        
        print("\n=== Last 10 Position Exits (Closes) ===")
        df_exits = df[df['entry'].isin([1, 2, 3])].copy()
        print(df_exits[cols].head(10).to_string(index=False))
        
    mt5.shutdown()

if __name__ == "__main__":
    main()
