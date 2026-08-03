import csv
import pathlib
from collections import defaultdict

# Path to the trade history CSV (two levels up from this script)
csv_path = pathlib.Path(__file__).parent.parent / 'bot_trade_history.csv'

symbol_stats = defaultdict(lambda: {'total': 0, 'wins': 0, 'losses': 0, 'breakevens': 0, 'pnl': 0.0})

with open(csv_path, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        symbol = row['symbol']
        result = row['result'].strip().upper()
        profit = float(row['profit'])
        stats = symbol_stats[symbol]
        stats['total'] += 1
        stats['pnl'] += profit
        if result == 'WIN':
            stats['wins'] += 1
        elif result == 'LOSS':
            stats['losses'] += 1
        elif result == 'BREAKEVEN':
            stats['breakevens'] += 1

# Print CSV‑style summary
print('Symbol,Total,Wins,Losses,Breakevens,WinRate%,PnL')
for sym, s in sorted(symbol_stats.items(), key=lambda kv: kv[1]['total'], reverse=True):
    win_rate = (s['wins'] / s['total'] * 100) if s['total'] else 0
    print(f"{sym},{s['total']},{s['wins']},{s['losses']},{s['breakevens']},{win_rate:.2f},{s['pnl']:.2f}")
