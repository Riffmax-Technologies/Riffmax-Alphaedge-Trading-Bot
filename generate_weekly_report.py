import pandas as pd
import os
from datetime import datetime, timedelta

log_path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/trade_log.xlsx"
if not os.path.exists(log_path):
    print("No trade log found.")
    exit(0)

df = pd.read_excel(log_path, engine='openpyxl')
# Convert timestamp to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])
# Filter last 7 days
now = datetime.utcnow()
week_ago = now - timedelta(days=7)
week_df = df[df['timestamp'] >= week_ago]

if week_df.empty:
    print("No trades in the last week.")
    exit(0)

# Summary stats
total_trades = len(week_df)
win_trades = week_df[week_df['profit'] > 0]
loss_trades = week_df[week_df['profit'] < 0]
win_rate = len(win_trades) / total_trades * 100 if total_trades > 0 else 0
total_profit = week_df['profit'].sum()
avg_profit = week_df['profit'].mean()
max_profit = week_df['profit'].max()
min_profit = week_df['profit'].min()

report = f"# Weekly Trading Report ({week_ago.date()} to {now.date()})\n\n"
report += f"**Total trades:** {total_trades}\n"
report += f"**Winning trades:** {len(win_trades)} ({win_rate:.2f}% win rate)\n"
report += f"**Losing trades:** {len(loss_trades)}\n"
report += f"**Total profit:** {total_profit:.4f}\n"
report += f"**Average profit per trade:** {avg_profit:.4f}\n"
report += f"**Maximum profit:** {max_profit:.4f}\n"
report += f"**Maximum loss:** {min_profit:.4f}\n\n"
report += "## Trades Detail\n"
report += week_df[['timestamp','symbol','action','entry_price','sl','tp','profit','comment']].to_markdown(index=False)
print(report)
