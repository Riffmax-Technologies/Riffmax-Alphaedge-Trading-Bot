import pandas as pd
import sys
csv_path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/scratch/backtest_results.csv"

df = pd.read_csv(csv_path)
# Ensure pnl column exists
total = len(df)
wins = (df['pnl'] > 0).sum()
win_rate = wins / total * 100 if total > 0 else 0
print(f"Total trades: {total}")
print(f"Winning trades: {wins}")
print(f"Win rate: {win_rate:.2f}%")
