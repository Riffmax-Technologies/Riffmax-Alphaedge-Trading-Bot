import csv
import pathlib

csv_path = pathlib.Path(__file__).parent.parent / 'bot_trade_history.csv'

total = 0
wins = 0
losses = 0
breakevens = 0
pnl = 0.0

with open(csv_path, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row.get('result'):
            continue
        total += 1
        result = row['result'].strip().upper()
        profit = float(row['profit']) if row['profit'] else 0.0
        pnl += profit
        if result == 'WIN':
            wins += 1
        elif result == 'LOSS':
            losses += 1
        elif result == 'BREAKEVEN':
            breakevens += 1

win_rate = (wins / total * 100) if total else 0
print(f"Total trades: {total}\nWins: {wins}\nLosses: {losses}\nBreakeven: {breakevens}\nWin rate: {win_rate:.2f}%\nTotal P&L: {pnl:.2f}")
