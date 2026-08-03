# check_today_performance.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

MT5_CONFIG = {
    "login": 81627783,
    "password": "Iamgreat@2030",
    "server": "Exness-MT5Trial10"
}

def check():
    if not mt5.initialize(
        login=MT5_CONFIG["login"],
        password=MT5_CONFIG["password"],
        server=MT5_CONFIG["server"]
    ):
        print("Failed to initialize MT5")
        return
        
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    
    # Get all deals for today
    deals = mt5.history_deals_get(today_start, now)
    if not deals:
        print("No trades found closed today.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Exits only (entry == 1 or entry == 3)
    exits = df[df['entry'].isin([1, 3])]
    if exits.empty:
        print("No exit deals (closed trades) found today.")
        mt5.shutdown()
        return
        
    # Group by comment
    print("=== Today's Performance Breakdown (July 6, 2026) ===")
    for comment in ["ALPHAEDGE_TRADE", "SHERIFNEW_UT"]:
        bot_deals = exits[exits['comment'] == comment]
        if bot_deals.empty:
            print(f"\nBot: {comment} - No completed trades today.")
            continue
            
        total_trades = len(bot_deals)
        wins = len(bot_deals[bot_deals['profit'] > 0])
        losses = len(bot_deals[bot_deals['profit'] <= 0])
        total_pnl = bot_deals['profit'].sum() + bot_deals['commission'].sum() + bot_deals['swap'].sum()
        win_rate = (wins / total_trades) * 100
        
        print(f"\nBot: {comment}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Wins: {wins} | Losses: {losses}")
        print(f"  Win Rate: {win_rate:.2f}%")
        print(f"  Total Net Profit/Loss: ${total_pnl:+.2f} USD")
        
    mt5.shutdown()

if __name__ == "__main__":
    check()
