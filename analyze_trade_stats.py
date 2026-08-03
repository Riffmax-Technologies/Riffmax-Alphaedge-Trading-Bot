# analyze_trade_stats.py
"""Parse bot_trade_history.csv and produce a breakdown:
- Overall win/loss/breakeven per symbol
- Win‑rate per symbol (wins / total trades)
- Daily summary (trades per calendar day and win‑rate)
"""

import csv
import os
from collections import defaultdict
from datetime import datetime

CSV_PATH = os.path.join(os.path.dirname(__file__), "bot_trade_history.csv")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"{CSV_PATH} not found")

# Data structures
symbol_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "breakevens": 0, "total": 0})
date_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "breakevens": 0, "total": 0})

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        symbol = row["symbol"]
        result = row["result"].strip().upper()
        # update symbol
        symbol_stats[symbol]["total"] += 1
        if result == "WIN":
            symbol_stats[symbol]["wins"] += 1
        elif result == "LOSS":
            symbol_stats[symbol]["losses"] += 1
        else:
            symbol_stats[symbol]["breakevens"] += 1
        # update date (use date part of timestamp)
        ts = row["timestamp"]
        try:
            dt = datetime.fromisoformat(ts)
            date_key = dt.date().isoformat()
        except Exception:
            continue
        date_stats[date_key]["total"] += 1
        if result == "WIN":
            date_stats[date_key]["wins"] += 1
        elif result == "LOSS":
            date_stats[date_key]["losses"] += 1
        else:
            date_stats[date_key]["breakevens"] += 1

# Print per-symbol table
print("=== Per-symbol performance ===")
print("Symbol | Trades | Wins | Losses | Breakevens | Win-rate %")
print("-------|--------|------|--------|------------|-----------")
for sym, stats in sorted(symbol_stats.items(), key=lambda x: x[0]):
    total = stats["total"]
    wins = stats["wins"]
    losses = stats["losses"]
    breakevens = stats["breakevens"]
    win_rate = (wins / total * 100) if total else 0.0
    print(f"{sym} | {total} | {wins} | {losses} | {breakevens} | {win_rate:.2f}")

print("\n=== Daily performance ===")
print("Date | Trades | Wins | Losses | Breakevens | Win-rate %")
print("----|--------|------|--------|------------|-----------")
for day, stats in sorted(date_stats.items()):
    total = stats["total"]
    wins = stats["wins"]
    losses = stats["losses"]
    breakevens = stats["breakevens"]
    win_rate = (wins / total * 100) if total else 0.0
    print(f"{day} | {total} | {wins} | {losses} | {breakevens} | {win_rate:.2f}")
