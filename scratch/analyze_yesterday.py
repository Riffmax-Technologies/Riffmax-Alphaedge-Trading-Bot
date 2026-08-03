import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def analyze_yesterday():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("MT5 initialization failed.")
        return

    # Fetch history for June 29, 2026
    start_date = datetime(2026, 6, 29, 0, 0, 0)
    end_date = datetime(2026, 6, 29, 23, 59, 59)
    
    deals = mt5.history_deals_get(start_date, end_date)
    if not deals:
        print("No closed deals found for yesterday.")
        mt5.shutdown()
        return

    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter exit deals (entry == 1 or entry == 3)
    exits = df[df['entry'].isin([1, 3])]
    if exits.empty:
        print("No closed trades found for yesterday.")
        mt5.shutdown()
        return
        
    bot_trades = []
    
    for idx, row in exits.iterrows():
        pos_id = row['position_id']
        symbol = row['symbol']
        
        # Exclude Silver (XAGUSD)
        if symbol.upper() == "XAGUSD":
            continue
            
        pos_deals = mt5.history_deals_get(position=pos_id)
        if pos_deals:
            df_pos = pd.DataFrame(list(pos_deals), columns=pos_deals[0]._asdict().keys())
            entry_deals = df_pos[df_pos['entry'] == 0]
            if not entry_deals.empty:
                entry_row = entry_deals.iloc[0]
                comment = entry_row['comment']
                
                # Filter only bot comments
                if comment in ["ALPHAEDGE_TRADE", "SHERIFNEW_UT"]:
                    profit = row['profit'] + row['commission'] + row['swap']
                    entry_time = datetime.fromtimestamp(entry_row['time'])
                    exit_time = datetime.fromtimestamp(row['time'])
                    duration = exit_time - entry_time
                    
                    bot_trades.append({
                        "Symbol": symbol,
                        "Type": "BUY" if entry_row['type'] == 0 else "SELL",
                        "Entry Time": entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "Exit Time": exit_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "Entry Price": entry_row['price'],
                        "Exit Price": row['price'],
                        "Profit": profit,
                        "Comment": comment,
                        "Duration": str(duration).split('.')[0]
                    })

    if not bot_trades:
        print("No bot-only closed trades found for yesterday (excluding Silver and manual trades).")
        mt5.shutdown()
        return

    df_bot = pd.DataFrame(bot_trades)
    df_bot = df_bot.drop_duplicates(subset=["Symbol", "Entry Time", "Exit Time"])
    
    total_trades = len(df_bot)
    wins = df_bot[df_bot['Profit'] > 0]
    losses = df_bot[df_bot['Profit'] <= 0]
    
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    gross_profit = wins['Profit'].sum() if not wins.empty else 0.0
    gross_loss = losses['Profit'].sum() if not losses.empty else 0.0
    net_profit = df_bot['Profit'].sum()
    
    print(f"Total Closed: {total_trades}")
    print(f"Wins: {len(wins)}")
    print(f"Losses: {len(losses)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Gross Profit: {gross_profit:.2f}")
    print(f"Gross Loss: {gross_loss:.2f}")
    print(f"Net Profit: {net_profit:.2f}")
    print("\n--- TRADE LIST ---")
    for _, t in df_bot.iterrows():
        print(f"{t['Symbol']}|{t['Type']}|{t['Entry Time']}|{t['Exit Time']}|{t['Profit']:.2f}|{t['Comment']}")
        
    mt5.shutdown()

if __name__ == "__main__":
    analyze_yesterday()
