import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("PerformanceReport")

def generate_performance_report(start_time: datetime, end_time: datetime, report_type: str = "Daily"):
    """
    Generates a performance report (Daily or Weekly) and returns the formatted Telegram message.
    """
    if not mt5.terminal_info():
        # Initialize if not already initialized
        mt5.initialize()

    deals = mt5.history_deals_get(start_time, end_time)
    if not deals:
        return f"📊 <b>AlphaEdge {report_type} Report</b>\n\nNo trades were closed during this period."

    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # We only care about closed trades. A closed trade consists of an entry deal and an exit deal.
    # The exit deal holds the actual realized profit.
    bot_tags = ["ALPHAEDGE_TRADE", "CORE_SYSTEM", "LIQUIDITY_SWEEP", "BREAKOUT"]
    
    # Find all position IDs that were OPENED by the bot
    if 'entry' not in df.columns or 'comment' not in df.columns or 'position_id' not in df.columns:
        return f"📊 <b>AlphaEdge {report_type} Report</b>\n\nNo valid deal data found."

    entries = df[df['entry'] == 0]
    bot_entries = entries[entries['comment'].isin(bot_tags)]
    
    if bot_entries.empty:
         return f"📊 <b>AlphaEdge {report_type} Report</b>\n\nNo autonomous trades were closed during this period."

    bot_position_ids = bot_entries['position_id'].unique()
    
    # Get all exit deals for those positions
    exits = df[(df['entry'] == 1) & (df['position_id'].isin(bot_position_ids))]
    
    if exits.empty:
         return f"📊 <b>AlphaEdge {report_type} Report</b>\n\nNo autonomous trades were closed during this period."

    # Group by position_id to calculate total profit per trade
    trade_profits = exits.groupby('position_id').agg({
        'profit': 'sum',
        'commission': 'sum',
        'swap': 'sum'
    }).reset_index()
    
    trade_profits['net_profit'] = trade_profits['profit'] + trade_profits['commission'] + trade_profits['swap']
    
    # Merge the strategy (comment) from the entry deal
    entry_strategies = bot_entries[['position_id', 'comment', 'symbol']].drop_duplicates('position_id')
    merged = pd.merge(trade_profits, entry_strategies, on='position_id', how='left')
    
    total_pnl = merged['net_profit'].sum()
    total_trades = len(merged)
    total_wins = len(merged[merged['net_profit'] > 0])
    overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

    msg = f"📊 <b>AlphaEdge {report_type} Performance</b>\n"
    msg += f"Period: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}\n\n"
    
    msg += f"<b>Overall Net PnL:</b> ${total_pnl:+.2f}\n"
    msg += f"<b>Total Trades:</b> {total_trades}\n"
    msg += f"<b>Overall Win Rate:</b> {overall_win_rate:.1f}%\n\n"
    
    msg += "<b>--- Strategy Breakdown ---</b>\n"
    
    # Group by Strategy
    strategy_groups = merged.groupby('comment')
    for strategy, group in strategy_groups:
        s_trades = len(group)
        s_wins = len(group[group['net_profit'] > 0])
        s_pnl = group['net_profit'].sum()
        s_win_rate = (s_wins / s_trades * 100) if s_trades > 0 else 0.0
        
        # Clean up strategy name for display
        display_name = strategy.replace("_", " ").title()
        if display_name == "Alphaedge Trade":
            display_name = "Legacy Core"
            
        emoji = "🟢" if s_pnl >= 0 else "🔴"
        
        msg += f"{emoji} <b>{display_name}</b>\n"
        msg += f"PnL: ${s_pnl:+.2f} | Win Rate: {s_win_rate:.1f}%\n"
        msg += f"Trades: {s_trades} ({s_wins}W / {s_trades - s_wins}L)\n\n"
        
    msg += "<i>AlphaEdge Autonomous Quantitative Engine</i>"
    
    return msg

if __name__ == "__main__":
    # Test block to print yesterday's report locally
    mt5.initialize()
    now = datetime.now()
    yesterday_start = datetime(now.year, now.month, now.day) - timedelta(days=1)
    today_start = datetime(now.year, now.month, now.day)
    print(generate_performance_report(yesterday_start, today_start, "Daily"))
    mt5.shutdown()
