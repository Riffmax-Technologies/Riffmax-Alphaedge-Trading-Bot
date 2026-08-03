# read_history_tail.py
import pandas as pd
import os

path = r"C:/Users/DATA ENG. OLA/.gemini/antigravity/brain/86033144-bf85-4d61-ac17-b7e233ed37cb/bot_trade_history.csv"
if os.path.exists(path):
    df = pd.read_csv(path)
    print("=== Last 20 trades in bot_trade_history.csv ===")
    print(df.tail(20).to_string())
else:
    print("bot_trade_history.csv not found")
