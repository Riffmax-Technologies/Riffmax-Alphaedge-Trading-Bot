import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def show_all():
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
        print("No closed deals found today.")
        mt5.shutdown()
        return

    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    exits = df[df['entry'].isin([1, 3])]
    if exits.empty:
        print("No closed trades found today.")
        mt5.shutdown()
        return

    all_trades = []
    for idx, row in exits.iterrows():
        pos_id = row['position_id']
        symbol = row['symbol']
        profit = row['profit'] + row['commission'] + row['swap']
        
        pos_deals = mt5.history_deals_get(position=pos_id)
        if pos_deals:
            df_pos = pd.DataFrame(list(pos_deals), columns=pos_deals[0]._asdict().keys())
            entry_deals = df_pos[df_pos['entry'] == 0]
            if not entry_deals.empty:
                entry_row = entry_deals.iloc[0]
                comment = entry_row['comment']
                all_trades.append({
                    "Symbol": symbol,
                    "Type": "BUY" if entry_row['type'] == 0 else "SELL",
                    "Profit": profit,
                    "Comment": comment if comment else "Manual"
                })

    df_all = pd.DataFrame(all_trades)
    df_all = df_all.drop_duplicates()
    
    print(f"Total Closed: {len(df_all)}")
    print(f"Net Profit: {df_all['Profit'].sum():.2f}")
    print("\n--- Trade Detail ---")
    for _, t in df_all.iterrows():
        print(f"{t['Symbol']} | {t['Type']} | Profit: ${t['Profit']:.2f} | Comment: {t['Comment']}")
        
    mt5.shutdown()

if __name__ == "__main__":
    show_all()
