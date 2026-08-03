import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def audit_today():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
        
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Retrieve history deals for today
    deals = mt5.history_deals_get(today, datetime.now())
    if not deals:
        print("No trades found today.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Find all position IDs closed today (deals where entry is 1 (out) or 3 (out by SL/TP))
    exit_deals = df[df['entry'].isin([1, 3])].copy()
    
    if exit_deals.empty:
        print("No completed (closed) trades today yet.")
        mt5.shutdown()
        return
        
    # For each position ID, look up the opening deal (entry == 0) to get the original comment
    bot_tickets = []
    manual_tickets = []
    
    bot_details = []
    manual_details = []
    
    bot_net = 0.0
    manual_net = 0.0
    
    for idx, exit_row in exit_deals.iterrows():
        pos_id = exit_row['position_id']
        pnl = exit_row['profit'] + exit_row['commission'] + exit_row['swap']
        symbol = exit_row['symbol']
        order_type = exit_row['type'] # 0 = buy, 1 = sell
        type_str = "BUY" if order_type == 0 else "SELL"
        
        # Get entry details for this position from history (can be opened yesterday)
        pos_history = mt5.history_deals_get(position=pos_id)
        original_comment = "Manual"
        
        if pos_history:
            for deal in pos_history:
                deal_dict = deal._asdict()
                if deal_dict.get('entry') == 0: # This is the opening deal
                    original_comment = deal_dict.get('comment', 'Manual')
                    break
        
        # Classify group
        is_bot = original_comment in ["ALPHAEDGE_TRADE", "SHERIFNEW_UT"]
        
        trade_info = f"  * {symbol} | {type_str} | P&L: ${pnl:+.2f} | Opening Comment: '{original_comment}' | Exit Comment: '{exit_row['comment']}' | Position ID: {pos_id}"
        
        if is_bot:
            bot_net += pnl
            bot_details.append(trade_info)
        else:
            manual_net += pnl
            manual_details.append(trade_info)
            
    print("\n=======================================================")
    print(f"BOT CLOSED TRADES TODAY ({len(bot_details)} total):")
    for detail in bot_details:
        print(detail)
    print(f"  --> Bot Net P&L: ${bot_net:+.2f}")
    
    print("\n=======================================================")
    print(f"MANUAL CLOSED TRADES TODAY ({len(manual_details)} total):")
    for detail in manual_details:
        print(detail)
    print(f"  --> Manual Net P&L: ${manual_net:+.2f}")
    print("=======================================================")
    
    mt5.shutdown()

if __name__ == "__main__":
    audit_today()
