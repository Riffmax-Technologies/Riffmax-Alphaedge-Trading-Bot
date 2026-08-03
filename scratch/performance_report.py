import csv
import pathlib
from collections import defaultdict
from datetime import datetime

csv_path = pathlib.Path(__file__).parent.parent / 'bot_trade_history.csv'

trades = []
with open(csv_path, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row.get('profit') or not row.get('timestamp'):
            continue
        profit = float(row['profit'])
        timestamp = datetime.fromisoformat(row['timestamp'])
        trades.append({'profit': profit, 'timestamp': timestamp, 'date': timestamp.date()})

# Overall stats
total = len(trades)
wins = sum(1 for t in trades if t['profit'] > 0)
losses = sum(1 for t in trades if t['profit'] < 0)
breakevens = sum(1 for t in trades if t['profit'] == 0)
win_rate = wins / total * 100 if total else 0
pnl = sum(t['profit'] for t in trades)
avg_win = sum(t['profit'] for t in trades if t['profit'] > 0) / wins if wins else 0
avg_loss = sum(t['profit'] for t in trades if t['profit'] < 0) / losses if losses else 0
max_loss = min(t['profit'] for t in trades) if trades else 0

# Daily drawdown: compute daily cumulative P&L and max loss per day
daily = defaultdict(list)
for t in trades:
    daily[t['date']].append(t['profit'])

daily_pnl = {d: sum(p) for d, p in daily.items()}
max_daily_loss = min(daily_pnl.values())  # most negative daily total

print('--- Performance Overview ---')
print(f'Total trades: {total}')
print(f'Wins: {wins}, Losses: {losses}, Breakevens: {breakevens}')
print(f'Win rate: {win_rate:.2f}%')
print(f'Total P&L: {pnl:.2f}')
print(f'Avg win: {avg_win:.2f}, Avg loss: {avg_loss:.2f}, Max loss (single trade): {max_loss:.2f}')
print(f'Max daily loss: {max_daily_loss:.2f}')

# Suggest lot sizing: assume account 10,000, max daily loss 400, max overall loss 800.
# If we limit each trade loss to at most 2% of account (200) we stay safe. But better to limit to 1% (100).
# Compute suggested lot multiplier based on average loss.
max_allowed_loss_per_trade = 100  # 1% of 10k
if avg_loss != 0:
    suggested_lot_factor = max_allowed_loss_per_trade / abs(avg_loss)
else:
    suggested_lot_factor = 1
print('\nSuggested lot scaling factor (relative to current lot sizes):')
print(f'{suggested_lot_factor:.2f}x (i.e., reduce lot size by this factor)')
