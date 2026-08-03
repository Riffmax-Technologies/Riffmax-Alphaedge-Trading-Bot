# dump_mt5_history.py
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
    # Go back 10 days
    start_date = now - timedelta(days=10)
    
    deals = mt5.history_deals_get(start_date, now)
    if not deals:
        print("No deals found in last 10 days.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"Total deals in history: {len(df)}")
    # Print last 50 closed trades regardless of comment to see what has happened
    print(df[['time', 'symbol', 'entry', 'volume', 'price', 'profit', 'comment']].tail(50).to_string(index=False))
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
